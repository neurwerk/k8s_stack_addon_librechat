"""Document delivery and false-positive boundaries, with synthetic app responses."""

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

from documents import DOCUMENTS, DocumentError, run_document, verify_answer
from fixtures import DATA
from test_chat_transport import TITLE, FakeOpener, Response


class DocumentSession:
    def __init__(self, *, upload=None, config=None):
        self.origin = "https://chat.example.com"
        self.headers = {}
        self.upload = (
            upload
            if upload is not None
            else {
                "file_id": "synthetic-file-id",
                "filepath": "/files/synthetic/file.pdf",
                "filename": "text_with_vector_rule.pdf",
                "type": "application/pdf",
                "llmDeliveryPath": "provider",
                "source": "s3",
            }
        )
        self.config = (
            config
            if config is not None
            else {
                "endpoints": {"Test": {"supportedMimeTypes": ["^application/pdf$"]}},
            }
        )
        self.chat = FakeOpener(
            message={
                "model": "test",
                "text": json.dumps({"answer": DOCUMENTS["6.1"].expected}),
            }
        )
        self.requests = []
        self.opener = self

    def json(self, path):
        if path != "/api/files/config":
            raise AssertionError("Unexpected application read")
        return self.config

    def ensure_fresh(self):
        pass

    def open(self, request, timeout):
        self.requests.append(request)
        if request.full_url.endswith("/api/files"):
            return Response(json.dumps(self.upload).encode())
        return self.chat.open(request, timeout)


class DocumentTests(unittest.TestCase):
    def test_strict_typed_answers_reject_false_positives(self):
        for actual, expected in (
            (' {"answer": 160}\n', 160),
            ('{"answer":["JSON","Markdown"]}', ["JSON", "Markdown"]),
            ('{"answer":{"items":[false,2]}}', {"items": [False, 2]}),
        ):
            verify_answer(actual, expected)
        for actual, expected in (
            ('{"answer":160}', "160"),
            ('{"answer":false}', 0),
            ('{"answer":160.0}', 160),
            ('{"answer":{"items":[0,2]}}', {"items": [False, 2]}),
            ('{"answer":["Markdown","JSON"]}', ["JSON", "Markdown"]),
            ('{"answer":159}', 160),
            ('{"answer":null}', 160),
            ('{"answer":0,"answer":160}', 160),
            ('{"answer":160,"explanation":"extra"}', 160),
            ("{}", 160),
            ('{"answer":NaN}', 160),
            ('{"answer":Infinity}', 160),
            ('{"answer":160', 160),
            ('```json\n{"answer":160}\n```', 160),
            ('The answer is {"answer":160}', 160),
            ("I cannot answer that", 160),
        ):
            with self.subTest(actual=actual), self.assertRaises(DocumentError):
                verify_answer(actual, expected)

    def test_original_file_and_delivery_reach_chat_without_leaking_expected_answer(self):
        case = DOCUMENTS["6.1"]
        session = DocumentSession()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = run_document(session, case, "Test", "test", "Streaming", TITLE)
        self.assertTrue(result.startswith("PASS:"))
        upload = session.requests[0]
        self.assertEqual(upload.get_method(), "POST")
        self.assertEqual(upload.full_url, session.origin + "/api/files")
        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: "
            + upload.get_header("Content-type").encode()
            + b"\r\n\r\n"
            + upload.data
        )
        parts = {
            part.get_param("name", header="content-disposition"): part
            for part in message.iter_parts()
        }
        self.assertEqual(parts["file"].get_filename(), Path(case.path).name)
        self.assertEqual(parts["file"].get_content_type(), case.mime)
        self.assertEqual(parts["file"].get_payload(decode=True), case.fixture())
        for key, expected in {
            "endpoint": "Test",
            "model": "test",
            "endpointType": "custom",
            "message_file": "true",
        }.items():
            self.assertEqual(parts[key].get_payload(decode=True).decode(), expected)
        self.assertEqual(session.chat.payload["files"], [session.upload])
        prompt = session.chat.payload["text"]
        self.assertIn(case.question, prompt)
        self.assertNotIn(case.expected, prompt)
        self.assertNotIn(case.source_evidence, prompt)
        self.assertNotIn(case.expected, output.getvalue())
        self.assertNotIn(session.upload["filepath"], output.getvalue())

    def test_unusable_upload_never_submits_chat(self):
        valid = DocumentSession().upload
        for upload in (
            {},
            {"file_id": "synthetic"},
            {**valid, "file_id": ""},
            {**valid, "type": "text/plain"},
            {**valid, "filename": "converted.txt"},
            {**valid, "llmDeliveryPath": "text"},
            {**valid, "llmDeliveryPath": "none"},
        ):
            session = DocumentSession(upload=upload)
            with self.subTest(upload=upload), self.assertRaises(ValueError):
                run_document(session, DOCUMENTS["6.1"], "Test", "test", "Streaming", TITLE)
            self.assertIsNone(session.chat.payload)
            self.assertEqual(len(session.requests), 1)

    def test_unknown_or_disabled_upload_support_never_uploads(self):
        for config in (
            {},
            {"endpoints": {"Other": {"supportedMimeTypes": ["^application/pdf$"]}}},
            {"endpoints": {"Test": {"supportedMimeTypes": ["^text/plain$"]}}},
            {"endpoints": {"Test": {"supportedMimeTypes": [{}]}}},
            {"endpoints": {"Test": {"supportedMimeTypes": ["["]}}},
            {"endpoints": {"Test": {"disabled": True, "supportedMimeTypes": [".*"]}}},
        ):
            session = DocumentSession(config=config)
            with self.subTest(config=config):
                result = run_document(
                    session, DOCUMENTS["6.1"], "Test", "test", "Streaming", TITLE
                )
                self.assertTrue(result.startswith("BLOCKED:"))
                self.assertFalse(session.requests)

    def test_tampered_fixture_and_unreleased_case_never_upload(self):
        case = DOCUMENTS["6.1"]
        session = DocumentSession()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / case.path
            fixture.parent.mkdir(parents=True)
            fixture.write_bytes(case.fixture() + b"tampered")
            (root / "manifest.json").write_bytes((DATA / "manifest.json").read_bytes())
            with patch("documents.DATA", root), self.assertRaises(DocumentError):
                run_document(session, case, "Test", "test", "Streaming", TITLE)
        self.assertFalse(session.requests)
        result = run_document(
            None,
            replace(case, blocked="Runtime adoption unverified"),
            "Test",
            "test",
            "Streaming",
            TITLE,
        )
        self.assertTrue(result.startswith("BLOCKED:"))


if __name__ == "__main__":
    unittest.main()
