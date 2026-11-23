"""Renewal regressions using synthetic tokens and the real HTTP cookie processor."""

import base64
import io
import json
import stat
import tempfile
import unittest
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from session import NoRedirect, Session, SessionError
from settings import DEFAULTS, load, save

ORIGIN = "https://chat.example.com"


def token(expiry):
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode()).decode().rstrip("=")
    )
    return "synthetic." + payload + ".unsigned"


def headers(access):
    return (
        f"Authorization: Bearer {access}\nCookie: connect.sid=old-session\n"
        "User-Agent: Synthetic-browser"
    )


class Transport(urllib.request.HTTPSHandler):
    def __init__(self, steps):
        super().__init__()
        self.steps = list(steps)
        self.requests = []

    def https_open(self, request):
        self.requests.append(request)
        method, path, status, body, cookies = self.steps.pop(0)
        if (request.get_method(), request.full_url) != (method, ORIGIN + path):
            raise AssertionError("Unexpected request sequence")
        response_headers = Message()
        response_headers["Content-Type"] = "application/json"
        for cookie in cookies:
            response_headers.add_header("Set-Cookie", cookie)
        response = urllib.response.addinfourl(
            io.BytesIO(json.dumps(body).encode()), response_headers, request.full_url, status
        )
        response.msg = "Synthetic"
        return response


def step(path, body, *, method="GET", status=200, cookies=()):
    return method, path, status, body, cookies


def session_for(access, steps, callback=None):
    session = Session(ORIGIN, raw_headers=headers(access), on_refresh=callback)
    transport = Transport(steps)
    session.opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        transport,
        urllib.request.HTTPCookieProcessor(session.cookies),
        NoRedirect(),
    )
    session.auto_refresh = True
    session.user_id = "synthetic-owner"
    return session, transport


class RefreshTests(unittest.TestCase):
    def test_saved_valid_token_connects_without_unnecessary_refresh(self):
        session, transport = session_for(
            token(5000),
            [
                step("/api/user", {"id": "synthetic-owner"}),
            ],
        )
        session.user_id = None
        with patch("session.time.time", return_value=1000):
            session.authenticate(refresh=True, renew_now=False)
        self.assertEqual(session.user_id, "synthetic-owner")
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(transport.requests[0].get_method(), "GET")

    def test_refresh_before_expiry_or_unknown_token_age(self):
        for expiry, age, renew in (
            (1181, 0, False),
            (1180, 0, True),
            (999, 0, True),
            (None, 299, False),
            (None, 300, True),
            ("invalid", 300, True),
        ):
            with self.subTest(expiry=expiry, age=age):
                steps = []
                if renew:
                    steps.append(
                        step("/api/auth/refresh", {"token": token(2000)}, method="POST")
                    )
                steps += [step("/api/models", {}), step("/api/models", {})]
                with (
                    patch("session.time.time", return_value=1000),
                    patch("session.time.monotonic", return_value=age),
                ):
                    session, transport = session_for(token(expiry), steps)
                    session._last_refresh = 0
                    session.json("/api/models")
                    session.json("/api/models")
                self.assertEqual(len(transport.requests), 3 if renew else 2)
                self.assertFalse(transport.steps)

    def test_get_401_recovers_once_with_rotated_credentials(self):
        session, transport = session_for(
            token(5000),
            [
                step("/api/models", {}, status=401),
                step(
                    "/api/auth/refresh",
                    {"token": token(6000)},
                    method="POST",
                    cookies=["connect.sid=new-session; Path=/; Secure; HttpOnly"],
                ),
                step("/api/models", {"Test": ["model"]}),
            ],
        )
        with patch("session.time.time", return_value=1000):
            self.assertEqual(session.json("/api/models"), {"Test": ["model"]})
        self.assertEqual(
            transport.requests[-1].get_header("Authorization"), "Bearer " + token(6000)
        )
        self.assertIn("connect.sid=new-session", transport.requests[-1].get_header("Cookie"))
        self.assertEqual(len(transport.requests), 3)

    def test_second_401_or_failed_refresh_stops(self):
        for refresh_status in (200, 401, 403):
            steps = [
                step("/api/models", {}, status=401),
                step(
                    "/api/auth/refresh",
                    {"token": token(6000)},
                    method="POST",
                    status=refresh_status,
                ),
            ]
            if refresh_status == 200:
                steps.append(step("/api/models", {}, status=401))
            session, transport = session_for(token(5000), steps)
            with (
                patch("session.time.time", return_value=1000),
                self.assertRaises((SessionError, urllib.error.HTTPError)) as caught,
            ):
                session.json("/api/models")
            if isinstance(caught.exception, urllib.error.HTTPError):
                caught.exception.close()
            self.assertFalse(transport.steps)
            self.assertEqual(len(transport.requests), 3 if refresh_status == 200 else 2)

    def test_mutations_and_permission_denials_are_not_replayed(self):
        for method, status in (("POST", 401), ("DELETE", 401), ("GET", 403)):
            session, transport = session_for(
                token(5000),
                [
                    step("/api/convos", {}, method=method, status=status),
                ],
            )
            with (
                patch("session.time.time", return_value=1000),
                self.assertRaises(urllib.error.HTTPError) as caught,
            ):
                session.json("/api/convos", method=method)
            caught.exception.close()
            self.assertEqual(len(transport.requests), 1)

    def test_rotated_credentials_saved_before_later_user_lookup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"

            def persist(session):
                save(path, DEFAULTS | {"request_headers": session.copied_headers()})

            session, transport = session_for(
                token(5000),
                [
                    step(
                        "/api/auth/refresh",
                        {"token": token(6000)},
                        method="POST",
                        cookies=["connect.sid=new-session; Path=/; Secure; HttpOnly"],
                    ),
                    step("/api/user", {}, status=403),
                ],
                persist,
            )
            session.user_id = None
            with self.assertRaises(urllib.error.HTTPError) as caught:
                session.authenticate(refresh=True)
            caught.exception.close()
            stored = load(path)["request_headers"]
            self.assertIn(token(6000), stored)
            self.assertIn("connect.sid=new-session", stored)
            self.assertNotIn("old-session", stored)
            self.assertIn(
                "connect.sid=new-session", transport.requests[-1].get_header("Cookie")
            )

    def test_bearer_only_cannot_renew_and_browser_pairs_are_supported(self):
        session = Session(
            ORIGIN, raw_headers="Authorization: Bearer synthetic\nUser-Agent: test"
        )
        with (
            patch.object(session.opener, "open") as open_request,
            self.assertRaises(SessionError),
        ):
            session.authenticate(refresh=True)
        open_request.assert_not_called()
        session = Session(
            ORIGIN,
            raw_headers=(
                "Authorization\n\tBearer synthetic\nCookie\n\tconnect.sid=synthetic\n"
                "User-Agent\n\tSynthetic-browser"
            ),
        )
        self.assertEqual(session.headers["authorization"], "Bearer synthetic")
        self.assertEqual(next(iter(session.cookies)).value, "synthetic")


class SettingsPersistenceTests(unittest.TestCase):
    def test_private_atomic_replace_and_failure_keeps_previous_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save(path, DEFAULTS | {"request_headers": "previous"})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            def reject_replace(source, destination):
                self.assertEqual(Path(destination), path)
                self.assertEqual(stat.S_IMODE(Path(source).stat().st_mode), 0o600)
                self.assertIn("renewed", Path(source).read_text())
                raise OSError("synthetic disk failure")

            with (
                patch("settings.os.replace", side_effect=reject_replace),
                self.assertRaises(OSError),
            ):
                save(path, DEFAULTS | {"request_headers": "renewed"})
            self.assertEqual(load(path)["request_headers"], "previous")
            self.assertEqual(list(Path(directory).iterdir()), [path])
            save(path, DEFAULTS | {"request_headers": "renewed"})
            self.assertEqual(load(path)["request_headers"], "renewed")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
