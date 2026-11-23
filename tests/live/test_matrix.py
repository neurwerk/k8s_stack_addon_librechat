"""Offline execution boundaries for model and response-mode selections."""

import contextlib
import io
import itertools
import unittest
from pathlib import Path
from unittest.mock import patch

from run import Runner
from scenarios import MODES, SCENARIOS, run_case
from settings import DEFAULTS


class MatrixTests(unittest.TestCase):
    def setUp(self):
        settings = DEFAULTS | {
            "local_model": "local-test",
            "remote_model": "remote-test",
            "local_endpoint": "test-local",
            "remote_endpoint": "test-remote",
            "kube_context": "test-context",
        }
        with patch("run.load", return_value=settings):
            self.runner = Runner(Path("unused.json"))
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_selected_cartesian_product_only(self):
        for model_choice, mode_choice in itertools.product(range(3), repeat=2):
            with self.subTest(models=model_choice, modes=mode_choice):
                self.runner.results.clear()
                groups = (("local",), ("remote",), ("local", "remote"))[model_choice]
                modes = ((MODES[0],), (MODES[1],), MODES)[mode_choice]
                with (
                    patch("run.choose", side_effect=[model_choice, mode_choice]),
                    patch.object(self.runner, "require_session") as session,
                    patch.object(self.runner, "discover_policy") as policy,
                    patch("run.run_case", return_value="PASS") as adapter,
                ):
                    self.runner.run([SCENARIOS[0]])
                expected_keys = {
                    (group, f"test-{group}", f"{group}-test", mode, "1.1")
                    for group in groups
                    for mode in modes
                }
                self.assertEqual(set(self.runner.results), expected_keys)
                calls = len(groups) * len(modes)
                self.assertEqual(adapter.call_count, calls)
                self.assertEqual(session.call_count, calls)
                self.assertEqual(policy.call_count, int(calls > 0))
                for call in adapter.call_args_list:
                    self.assertIn(call.args[4], [f"{group}-test" for group in groups])
                    self.assertIn(call.kwargs["mode"], modes)
                for key, result in self.runner.results.items():
                    self.assertEqual(result, "PASS")
                # Endpoint is part of identity: changing it must preserve previous results.
                if calls:
                    group = groups[0]
                    before = set(self.runner.results)
                    self.runner.settings[group + "_endpoint"] = "other-endpoint"
                    with (
                        patch("run.choose", side_effect=[0 if group == "local" else 1, 0]),
                        patch.object(self.runner, "require_session"),
                        patch.object(self.runner, "discover_policy"),
                        patch("run.run_case", return_value="PASS"),
                    ):
                        self.runner.run([SCENARIOS[0]])
                    self.assertTrue(before < set(self.runner.results))
                    self.runner.settings[group + "_endpoint"] = f"test-{group}"

    def test_cancel_at_either_dimension_makes_no_requests(self):
        for answers in ([4], [2, 3]):
            with (
                patch("run.choose", side_effect=answers),
                patch.object(self.runner, "require_session") as session,
                patch.object(self.runner, "discover_policy") as policy,
                patch("run.run_case") as adapter,
            ):
                self.runner.run([SCENARIOS[0]])
            session.assert_not_called()
            policy.assert_not_called()
            adapter.assert_not_called()
            self.assertFalse(self.runner.results)

    def test_planned_combinations_never_submit(self):
        planned = next(case for case in SCENARIOS if case.blocked)
        for case, mode in (
            (planned, "Streaming"),
            (planned, "Non-streaming"),
        ):
            # None is intentional: any transport or upload would fail this check.
            result = run_case(None, case, "Local model", "test", "test", mode)
            self.assertTrue(result.startswith("BLOCKED:"))
        with (
            patch("run.choose", side_effect=[2, 2]),
            patch.object(self.runner, "require_session") as session,
            patch.object(self.runner, "discover_policy") as policy,
            patch("run.run_case") as adapter,
        ):
            self.runner.run([planned])
        self.assertEqual(len(self.runner.results), 4)
        session.assert_not_called()
        policy.assert_not_called()
        adapter.assert_not_called()
        with (
            patch("run.choose", side_effect=[2, 2]),
            patch.object(self.runner, "require_session"),
            patch.object(self.runner, "discover_policy"),
            patch("run.run_case", return_value="PASS") as adapter,
        ):
            self.runner.run([SCENARIOS[0], planned, SCENARIOS[0]])
        self.assertEqual(len(self.runner.results), 8)
        self.assertEqual(adapter.call_count, 4)


if __name__ == "__main__":
    unittest.main()
