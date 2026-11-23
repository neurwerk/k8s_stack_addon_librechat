"""Noninteractive execution must not request credentials or turn failures into success."""

import contextlib
import io
import unittest
from unittest.mock import patch

from run import main
from session import SessionError
from settings import DEFAULTS


class CommandTests(unittest.TestCase):
    def invoke(self, arguments, settings):
        with (
            patch("sys.argv", ["run.py", *arguments]),
            patch("run.load", return_value=settings),
            patch("builtins.input", side_effect=AssertionError("CLI must not prompt")),
            patch("run.choose", side_effect=AssertionError("CLI must not open menus")),
            patch(
                "run.paste_headers", side_effect=AssertionError("CLI must not request headers")
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return main()

    def test_explicit_dimensions_and_exit_status(self):
        settings = DEFAULTS | {"local_model": "test", "request_headers": "synthetic"}
        with patch("run.Runner.run", return_value=2) as run:
            self.assertEqual(
                self.invoke(
                    ["--test", "1.1", "--models", "local", "--modes", "non-streaming"],
                    settings,
                ),
                2,
            )
        self.assertEqual(run.call_args.kwargs["dimensions"], (("local",), ("Non-streaming",)))

    def test_missing_credentials_or_failed_refresh_never_prompts(self):
        settings = DEFAULTS | {"local_model": "test"}
        self.assertEqual(self.invoke(["--test", "1.1", "--models", "local"], settings), 1)
        settings |= {"origin": "https://chat.example.com", "request_headers": "synthetic"}
        with patch(
            "run.Session", side_effect=SessionError("Refresh returned no JSON credentials")
        ):
            self.assertEqual(self.invoke(["--test", "1.1", "--models", "local"], settings), 1)

    def test_unknown_test_rejected_before_settings_or_auth(self):
        with (
            patch("sys.argv", ["run.py", "--test", "unknown"]),
            patch("run.load") as load,
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            main()
        self.assertEqual(error.exception.code, 2)
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
