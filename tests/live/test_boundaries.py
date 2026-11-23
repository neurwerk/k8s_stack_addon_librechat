"""Offline checks for consequential cleanup boundaries and policy readiness."""

import contextlib
import hashlib
import io
import json
import subprocess
import unittest
import urllib.error
from unittest.mock import patch

from cleanup import PREFIX, candidates, cleanup, eligible
from policy import discover

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
ACTIVE = "/api/convos?limit=100&isArchived=false"
ARCHIVED = "/api/convos?limit=100&isArchived=true"


def row(identifier=A, **changes):
    return {"conversationId": identifier, "user": "owner", "title": PREFIX + "test", **changes}


def page(rows, cursor=None):
    return {"conversations": rows, "nextCursor": cursor}


class ScriptedSession:
    user_id = "owner"

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def json(self, path, *, method="GET", payload=None):
        self.calls.append((method, path, payload))
        expected_method, expected_path, result = self.steps.pop(0)
        if (method, path) != (expected_method, expected_path):
            raise AssertionError("Unexpected request sequence")
        if isinstance(result, Exception):
            raise result
        return result


def confirm(prompt):
    return prompt.removeprefix("Type ").removesuffix(" to delete these chats: ")


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_exact_prefix_and_owner(self):
        self.assertTrue(eligible(row(), "owner"))
        for changes in (
            {"title": " " + PREFIX},
            {"title": PREFIX.lower()},
            {"title": "chat " + PREFIX},
            {"title": None},
            {"user": "someone-else"},
        ):
            self.assertFalse(eligible(row(**changes), "owner"))
        self.assertFalse(eligible(row(), None))

    def test_all_pages_archived_and_deduplicated(self):
        session = ScriptedSession(
            [
                ("GET", ACTIVE, page([row()], "next")),
                ("GET", ACTIVE + "&cursor=next", page([row(B)])),
                ("GET", ARCHIVED, page([row(), row(title="ordinary")])),
            ]
        )
        self.assertEqual(candidates(session), [A, B])
        self.assertFalse(session.steps)

    def test_incomplete_listing_never_deletes(self):
        for result in (page([], "next"), ValueError("unavailable"), {"conversations": []}):
            session = ScriptedSession(
                [
                    ("GET", ACTIVE, page([row()], "next")),
                    ("GET", ACTIVE + "&cursor=next", result),
                ]
            )
            with self.assertRaises(ValueError):
                cleanup(session, delete=True, confirm=confirm)
            self.assertTrue(all(call[0] == "GET" for call in session.calls))

    def test_preview_and_wrong_confirmation_never_delete(self):
        for delete, answer in ((False, ""), (True, ""), (True, "DELETE"), (True, "yes")):
            session = ScriptedSession(
                [
                    ("GET", ACTIVE, page([row()])),
                    ("GET", ARCHIVED, page([])),
                ]
            )
            self.assertEqual(cleanup(session, delete=delete, confirm=lambda _: answer), 0)
            self.assertEqual(len(session.calls), 2)

    def test_changed_or_missing_chat_never_deleted(self):
        for current in (
            row(title="renamed"),
            row(user="someone-else"),
            row(B),
            urllib.error.HTTPError("https://example.invalid", 404, "", {}, None),
        ):
            session = ScriptedSession(
                [
                    ("GET", ACTIVE, page([row()])),
                    ("GET", ARCHIVED, page([])),
                    ("GET", "/api/convos/" + A, current),
                ]
            )
            self.assertEqual(cleanup(session, delete=True, confirm=confirm), 0)
            self.assertTrue(all(call[0] == "GET" for call in session.calls))

    def test_only_revalidated_id_deleted_and_verified(self):
        session = ScriptedSession(
            [
                ("GET", ACTIVE, page([row()])),
                ("GET", ARCHIVED, page([])),
                ("GET", "/api/convos/" + A, row()),
                ("DELETE", "/api/convos", {}),
                (
                    "GET",
                    "/api/convos/" + A,
                    urllib.error.HTTPError("https://example.invalid", 404, "", {}, None),
                ),
            ]
        )
        self.assertEqual(cleanup(session, delete=True, confirm=confirm), 1)
        self.assertEqual(
            session.calls[3], ("DELETE", "/api/convos", {"arg": {"conversationId": A}})
        )
        self.assertFalse(session.steps)

    def test_success_status_without_deletion_is_failure(self):
        session = ScriptedSession(
            [
                ("GET", ACTIVE, page([row()])),
                ("GET", ARCHIVED, page([])),
                ("GET", "/api/convos/" + A, row()),
                ("DELETE", "/api/convos", {}),
                ("GET", "/api/convos/" + A, row()),
            ]
        )
        with self.assertRaises(ValueError):
            cleanup(session, delete=True, confirm=confirm)


class PolicyTests(unittest.TestCase):
    def document(self, policy="pii:\n  default_action: pass\n"):
        return {
            "kind": "ConfigMap",
            "metadata": {"name": "policy", "namespace": "engine", "resourceVersion": "42"},
            "data": {"policy.yaml": policy},
        }

    def test_targeted_read_does_not_claim_effective_enforcement(self):
        for policy in ("pii:\n  default_action: pass\n", "é" * (1024 * 1024 // 2)):
            response = subprocess.CompletedProcess(
                [], 0, json.dumps(self.document(policy), ensure_ascii=False), ""
            )
            with patch("policy.subprocess.run", return_value=response) as run:
                snapshot = discover("test-context", "engine", "policy")
            run.assert_called_once_with(
                [
                    "kubectl",
                    "--context",
                    "test-context",
                    "--request-timeout=10s",
                    "--namespace",
                    "engine",
                    "get",
                    "configmap",
                    "policy",
                    "--output=json",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            report = snapshot.summary()
            self.assertEqual(report["resource_version"], "42")
            self.assertEqual(
                report["policy_sha256"], hashlib.sha256(policy.encode()).hexdigest()
            )
            self.assertEqual(snapshot.policy_yaml, policy)
            self.assertNotIn(policy, json.dumps(report))
            self.assertFalse(report["effective_policy_verified"])
            self.assertEqual(report["pii_status"], "BLOCKED")

    def test_missing_context_never_calls_kubectl(self):
        for context in (None, "", "  "):
            with patch("policy.subprocess.run") as run, self.assertRaises(ValueError):
                discover(context, "engine", "policy")
            run.assert_not_called()

    def test_failed_discovery_never_reports_readiness(self):
        invalid = [[], None, {}, {"kind": "ConfigMap"}]
        for key, value in (("kind", "Secret"), ("data", None), ("data", [])):
            document = self.document()
            document[key] = value
            invalid.append(document)
        for key in ("name", "namespace", "resourceVersion"):
            document = self.document()
            del document["metadata"][key]
            invalid.append(document)
        for key in ("name", "namespace"):
            document = self.document()
            document["metadata"][key] = "wrong"
            invalid.append(document)
        for value in (None, 3, "", "  ", "a" * (1024 * 1024 + 1)):
            invalid.append(self.document(value))
        missing = self.document()
        del missing["data"]["policy.yaml"]
        invalid.append(missing)
        failures = [
            subprocess.TimeoutExpired("kubectl", 20),
            FileNotFoundError(),
            subprocess.CompletedProcess([], 1, "", "private diagnostic"),
            subprocess.CompletedProcess([], 0, "{", ""),
            *(subprocess.CompletedProcess([], 0, json.dumps(doc), "") for doc in invalid),
        ]
        for failure in failures:
            with self.subTest(case=type(failure).__name__):
                options = (
                    {"side_effect": failure}
                    if isinstance(failure, Exception)
                    else {"return_value": failure}
                )
                with patch("policy.subprocess.run", **options), self.assertRaises(ValueError):
                    discover("test-context", "engine", "policy")


if __name__ == "__main__":
    unittest.main()
