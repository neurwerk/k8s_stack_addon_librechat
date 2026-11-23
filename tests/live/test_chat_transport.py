"""Mode-setting and terminal-event regressions without model or cluster traffic."""

import contextlib
import io
import json
import time
import unittest
from email.message import Message

from chat_smoke import chat, verify_stream

IDENTIFIER = "00000000-0000-4000-8000-000000000001"
TITLE = "NEURWERK AUTOMATIC TESTS - Local model - Streaming - 1.1 - Basic chat"
PRIVATE_REPLY = "synthetic response withheld from logs"


class Response(io.BytesIO):
    def __init__(self, body, kind="application/json"):
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = kind


class FakeOpener:
    def __init__(self, *, direct=False, mode=False, saved_mode=False, message=None):
        self.direct = direct
        self.mode = mode
        self.saved_mode = saved_mode
        self.message = message or {"model": "test", "text": PRIVATE_REPLY}
        self.calls = []
        self.payload = None

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        if request.full_url.endswith("/update"):
            return Response(json.dumps({"conversationId": IDENTIFIER, "title": TITLE}).encode())
        if "/api/convos/" in request.full_url:
            saved = {"conversationId": IDENTIFIER}
            if self.saved_mode is not None:
                saved["disableStreaming"] = self.saved_mode
            return Response(json.dumps(saved).encode())
        if "/stream/" not in request.full_url:
            self.payload = json.loads(request.data)
            if self.payload["disableStreaming"] != self.mode:
                raise AssertionError("Wrong requested generation mode")
            if not self.direct:
                return Response(
                    json.dumps(
                        {
                            "status": "started",
                            "streamId": "test",
                            "conversationId": IDENTIFIER,
                        }
                    ).encode()
                )
        event = {"final": True, "conversationId": IDENTIFIER, "responseMessage": self.message}
        return Response(("data: " + json.dumps(event) + "\n\n").encode(), "text/event-stream")


class ChatTransportTests(unittest.TestCase):
    def test_both_generation_modes_and_sse_paths_verify_saved_setting(self):
        for direct in (False, True):
            for mode in (False, True):
                opener = FakeOpener(direct=direct, mode=mode, saved_mode=mode)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    text = chat(
                        opener,
                        "https://chat.example.com",
                        {},
                        "Test",
                        "test",
                        save_title=TITLE,
                        disable_streaming=mode,
                    )
                self.assertEqual(text, PRIVATE_REPLY)
                self.assertNotIn(PRIVATE_REPLY, output.getvalue())
                self.assertTrue(opener.calls[-1].endswith("/api/convos/" + IDENTIFIER))

    def test_missing_or_mismatched_saved_mode_fails(self):
        for saved in (None, "false", True):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                chat(
                    FakeOpener(saved_mode=saved),
                    "https://chat.example.com",
                    {},
                    "Test",
                    "test",
                    save_title=TITLE,
                )

    def test_terminal_error_wrong_model_or_empty_text_fails(self):
        for message in (
            {"model": "test", "text": PRIVATE_REPLY, "error": True},
            {"model": "wrong", "text": PRIVATE_REPLY},
            {"model": "test", "text": ""},
        ):
            opener = FakeOpener(message=message)
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                chat(opener, "https://chat.example.com", {}, "Test", "test", save_title=TITLE)
            self.assertTrue(opener.calls[-1].endswith("/update"))

    def test_expected_image_text_not_in_prompt(self):
        opener = FakeOpener()
        with contextlib.redirect_stdout(io.StringIO()):
            chat(
                opener,
                "https://chat.example.com",
                {},
                "Test",
                "test",
                attachment={"file_id": "synthetic"},
                expected_text=PRIVATE_REPLY,
                save_title=TITLE,
            )
        self.assertNotIn(PRIVATE_REPLY, opener.payload["text"])

    def test_text_blocks_preserve_order_without_repeating_legacy_mirror(self):
        answer = '{"answer":"café"}'
        for message in (
            {"text": answer},
            {"content": [{"type": "text", "text": answer}]},
            {"text": answer, "content": [{"type": "text", "text": {"value": answer}}]},
            {
                "text": "unused mirror",
                "content": [
                    {"type": "text", "text": '{"answer":"ca'},
                    {"type": "text", "text": 'fé"}'},
                ],
            },
        ):
            with self.subTest(message=message), contextlib.redirect_stdout(io.StringIO()):
                result = chat(
                    FakeOpener(message={"model": "test", **message}),
                    "https://chat.example.com",
                    {},
                    "Test",
                    "test",
                )
                self.assertEqual(result, answer)

    def test_matching_intermediate_answer_without_successful_terminal_is_not_success(self):
        intermediate = 'data: {"text":"{\\"answer\\":160}"}\n\n'
        for ending in (
            "",
            'event: error\ndata: {"error":true}\n\n',
            'data: {"final":true,"responseMessage":{"model":"test","text":"160",'
            '"finish_reason":"length"}}\n\n',
        ):
            with self.subTest(ending=ending), self.assertRaises(ValueError):
                verify_stream(
                    Response((intermediate + ending).encode()), time.monotonic(), "test"
                )


if __name__ == "__main__":
    unittest.main()
