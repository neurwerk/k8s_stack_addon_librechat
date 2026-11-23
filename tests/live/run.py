# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Start with uv run tests/live/run.py; configure everything in the menu."""

import argparse
import json
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

from cleanup import cleanup
from documents import DOCUMENTS, DocumentError
from menu import TITLE, choose, paste_headers, select_many
from policy import PolicyError, discover
from scenarios import CATEGORIES, MODES, SCENARIOS, readiness, run_case
from session import Session, SessionError
from settings import DEFAULT_PATH, load, save


class Runner:
    def __init__(self, path: Path):
        self.path = path
        self.settings = load(path)
        self.session = None
        self.results = {}
        self.interactive = True

    def connect(self, *, use_saved=False):
        origin = self.settings["origin"]
        if not self.interactive and (not origin or not self.settings["request_headers"]):
            raise SessionError(
                "Saved LibreChat origin and request headers are required for CLI runs."
            )
        if not origin:
            origin = input("LibreChat HTTPS origin: ").strip()
        raw = self.settings["request_headers"] if use_saved else ""
        if not raw:
            raw = paste_headers()
        session = Session(origin, raw_headers=raw, on_refresh=self.save_session)
        session.authenticate(refresh=self.settings["refresh"], renew_now=not use_saved)
        self.session = session
        self.save_session(session)
        print("Connected. Headers saved in the private local settings file.")
        if session.auto_refresh:
            print("Automatic renewal enabled; rotated tokens and cookies will be saved.")

    def save_session(self, session):
        self.settings["origin"] = session.origin
        self.settings["request_headers"] = session.copied_headers()
        save(self.path, self.settings)

    def require_session(self):
        if self.session is None:
            self.connect(use_saved=True)
        else:
            self.session.ensure_fresh()
        return self.session

    def models(self):
        catalog = self.require_session().json("/api/models")
        if not isinstance(catalog, dict):
            raise ValueError("Invalid model catalog")
        while True:
            group = choose(
                "Select one or two models",
                [
                    "Local model: " + (self.settings["local_model"] or "none"),
                    "Remote model: " + (self.settings["remote_model"] or "none"),
                    "Back",
                ],
            )
            if group == 2:
                return
            key = "local" if group == 0 else "remote"
            endpoints = sorted(
                name
                for name, models in catalog.items()
                if isinstance(name, str)
                and isinstance(models, list)
                and all(isinstance(model, str) for model in models)
                and models
            )
            index = choose(
                "Choose endpoint for " + key + " model",
                [*endpoints, "Disable this model", "Back"],
            )
            if index == len(endpoints) + 1:
                continue
            if index == len(endpoints):
                self.settings[key + "_model"] = ""
            else:
                endpoint = endpoints[index]
                models = catalog[endpoint]
                selected = choose("Choose " + key + " model", [*models, "Back"])
                if selected == len(models):
                    continue
                self.settings[key + "_endpoint"] = endpoint
                self.settings[key + "_model"] = models[selected]
            save(self.path, self.settings)

    def configure(self):
        keys = [
            "origin",
            "kube_context",
            "policy_namespace",
            "policy_configmap",
            "refresh",
        ]
        labels = [
            "LibreChat origin",
            "Kubernetes context",
            "Policy namespace",
            "Policy ConfigMap",
            "Automatically renew LibreChat session",
        ]
        descriptions = [
            "Base HTTPS address, without /api or a chat path. Example: https://chat.example.com",
            "Explicit context from kubectl config get-contexts. Example: development-context",
            "Namespace containing the PII Engine policy. Example: monitor-pii-engine",
            "ConfigMap containing policy.yaml. Example: monitor-pii-engine-config-map",
            "On: renew during runs and automatically save rotated tokens and cookies.",
        ]
        while True:
            index = choose(
                "Settings — saved automatically",
                [
                    f"{label}  ·  "
                    + (
                        ("On" if self.settings[key] else "Off")
                        if key == "refresh"
                        else self.settings[key] or "Not set"
                    )
                    for label, key in zip(labels, keys, strict=True)
                ]
                + ["Back"],
                overview=[
                    "Select a setting to edit. Changes save automatically.",
                    "Examples use reserved example.com domains.",
                ],
                descriptions=descriptions + ["Return to the main menu."],
            )
            if index == len(keys):
                return
            key = keys[index]
            if key == "refresh":
                self.settings[key] = not self.settings[key]
                if self.session is not None:
                    self.session.auto_refresh = self.settings[key]
            else:
                print("\n" + labels[index])
                print(descriptions[index])
                print("Current: " + (self.settings[key] or "Not set"))
                value = input(labels[index] + " (blank clears): ").strip()
                self.settings[key] = value
                if key == "origin":
                    self.session = None
            save(self.path, self.settings)

    def launch_dimensions(self, count):
        while True:
            model_choice = choose(
                f"Run {count} scenario(s) · Choose models",
                [
                    "Local only · " + (self.settings["local_model"] or "not configured"),
                    "Remote only · " + (self.settings["remote_model"] or "not configured"),
                    "Both local and remote",
                    "Change configured models",
                    "Cancel",
                ],
            )
            if model_choice == 4:
                return None
            if model_choice == 3:
                self.models()
                continue
            break
        mode_choice = choose(
            f"Run {count} scenario(s) · Choose response modes",
            [*MODES, "Both streaming and non-streaming", "Cancel"],
            ["Model generation mode; LibreChat uses SSE for application events in both modes."],
        )
        if mode_choice == 3:
            return None
        groups = (("local",), ("remote",), ("local", "remote"))[model_choice]
        modes = ((MODES[0],), (MODES[1],), MODES)[mode_choice]
        return groups, modes

    def run(self, cases, *, dimensions=None):
        cases = tuple({case.identifier: case for case in cases}.values())
        if not cases:
            return 2
        if dimensions is None:
            dimensions = self.launch_dimensions(len(cases))
        if dimensions is None:
            print("Run cancelled.")
            return 2
        groups, modes = dimensions
        print("Run UTC: " + datetime.now(UTC).isoformat())
        print(
            f"{len(cases)} scenarios × {len(groups)} models × {len(modes)} modes"
            f" = {len(cases) * len(groups) * len(modes)} combinations"
        )
        runnable = any(
            self.settings[group + "_model"] and readiness(case, mode) is None
            for group in groups
            for mode in modes
            for case in cases
        )
        if runnable and self.settings["kube_context"]:
            try:
                self.discover_policy()
            except PolicyError as exc:
                print(failure(exc))
        summary = []
        counts = {}
        session_failure = None
        for key in groups:
            label = "Local model" if key == "local" else "Remote model"
            model = self.settings[key + "_model"]
            endpoint = self.settings[key + "_endpoint"]
            print(f"\n{label}: {model}")
            for mode in modes:
                for case in cases:
                    result = readiness(case, mode)
                    if not model:
                        result = "SKIP: model not configured"
                    if result is None and session_failure:
                        result = session_failure
                    if result is None:
                        try:
                            result = run_case(
                                self.require_session(),
                                case,
                                label,
                                endpoint,
                                model,
                                mode=mode,
                            )
                        except (OSError, ValueError, TypeError, KeyError) as exc:
                            result = failure(exc)
                            if self.session is None or isinstance(exc, SessionError):
                                session_failure = result
                    self.results[(key, endpoint, model, mode, case.identifier)] = result
                    summary.append(
                        f"{label} · {mode} · {case.identifier} {case.name}: {result}"
                    )
                    status = result.split(":", 1)[0]
                    counts[status] = counts.get(status, 0) + 1
        print("\nRun summary")
        print("\n".join(summary))
        print(" · ".join(f"{status}: {count}" for status, count in counts.items()))
        if counts.get("FAIL"):
            return 1
        return 0 if set(counts) == {"PASS"} else 2

    def case_status(self, case) -> str:
        if case.blocked:
            return "PREPARED · BLOCKED" if case.identifier in DOCUMENTS else "PLANNED"
        states = []
        for key in ("local", "remote"):
            model = self.settings[key + "_model"]
            if model:
                endpoint = self.settings[key + "_endpoint"]
                for mode in MODES:
                    result = self.results.get((key, endpoint, model, mode, case.identifier))
                    if result:
                        states.append(f"{key}/{mode}: {result.split(':', 1)[0]}")
        return " | ".join(states) or "READY · not run"

    def discover_policy(self):
        snapshot = discover(
            self.settings["kube_context"],
            self.settings["policy_namespace"],
            self.settings["policy_configmap"],
        )
        print(json.dumps(snapshot.summary(), indent=2))

    def category(self, category):
        name, kind = category
        cases = [case for case in SCENARIOS if case.kind == kind]
        while True:
            options = [
                f"{case.identifier} {case.name} — {self.case_status(case)}" for case in cases
            ] + ["Select several tests", "Test all in category", "Back"]
            index = choose(
                name,
                options,
                ["Enter runs a test. Models and modes are chosen at launch."],
                descriptions=[
                    (
                        DOCUMENTS[case.identifier].question + " " + case.blocked
                        if case.identifier in DOCUMENTS
                        else case.blocked
                        or "Checks completion and the saved model-generation mode."
                    )
                    for case in cases
                ]
                + [
                    "Choose a subset.",
                    "Run every scenario in this category.",
                    "Back to categories.",
                ],
            )
            if index == len(cases) + 2:
                return
            if index == len(cases):
                selected = select_many(
                    name + " · Select tests",
                    [f"{case.identifier} {case.name}" for case in cases],
                )
                if not selected:
                    continue
                self.run([cases[i] for i in selected])
            else:
                self.run(cases if index == len(cases) + 1 else [cases[index]])
            input("\nEnter to return to category…")

    def live_tests(self):
        while True:
            options = []
            for name, kind in CATEGORIES:
                cases = [case for case in SCENARIOS if case.kind == kind]
                ready = sum(not case.blocked for case in cases)
                prepared = sum(
                    case.identifier in DOCUMENTS and bool(case.blocked) for case in cases
                )
                extra = f" / {prepared} prepared" if prepared else ""
                options.append(f"{name} · {ready} ready{extra} / {len(cases)} scenarios")
            options += ["Select tests across categories", "Test all categories", "Back"]
            index = choose(
                "Live tests",
                options,
                [
                    "Seven categories · model × response mode selected at launch",
                    "PREPARED/PLANNED cases stay BLOCKED until prerequisites are verified.",
                ],
            )
            if index == len(CATEGORIES) + 2:
                return
            if index < len(CATEGORIES):
                self.category(CATEGORIES[index])
                continue
            if index == len(CATEGORIES):
                selected = select_many(
                    "Live tests · Select tests",
                    [
                        f"{case.identifier} {case.name} · {self.case_status(case)}"
                        for case in SCENARIOS
                    ],
                )
                if not selected:
                    continue
                self.run([SCENARIOS[i] for i in selected])
            else:
                self.run(SCENARIOS)
            input("\nEnter to return to live tests…")

    def cleanup_menu(self):
        while True:
            index = choose(
                "Cleanup",
                [
                    "Preview automatic test chats",
                    "Delete automatic test chats",
                    "Back",
                ],
            )
            if index == 2:
                return
            cleanup(self.require_session(), delete=index == 1)
            input("\nEnter to return to cleanup…")

    def setup(self):
        while True:
            index = choose(
                "Setup",
                [
                    "Configure models",
                    "Paste LibreChat headers / reconnect",
                    "Discover policy via kubectl",
                    "Back",
                ],
            )
            if index == 3:
                return
            if index == 0:
                self.models()
                continue
            if index == 1:
                self.connect()
            else:
                self.discover_policy()
            input("\nEnter to return to setup…")

    def main(self):
        while True:
            options = [
                "1. Live tests",
                "2. Cleanup",
                "3. Settings",
                "4. Setup",
                "5. Quit",
            ]
            index = choose(TITLE, options)
            if index == len(options) - 1:
                return 0
            try:
                if index == 0:
                    self.live_tests()
                elif index == 1:
                    self.cleanup_menu()
                elif index == 2:
                    self.configure()
                else:
                    self.setup()
            except (OSError, ValueError, TypeError, KeyError) as exc:
                print(failure(exc))
                input("\nEnter to return to menu…")


def failure(exc) -> str:
    if isinstance(exc, (PolicyError, SessionError, DocumentError)):
        return "FAIL: " + str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        exc.close()
        return f"FAIL: HTTP {code}; reconnect if the session expired. Response withheld."
    return "FAIL: invalid settings, response, or connection; private details withheld."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--test",
        action="append",
        metavar="ID",
        help="Run a scenario without menus; repeat to select several",
    )
    selection.add_argument("--all", action="store_true", help="Run all scenarios without menus")
    parser.add_argument("--models", choices=["local", "remote", "both"], default="both")
    parser.add_argument(
        "--modes", choices=["streaming", "non-streaming", "both"], default="both"
    )
    args = parser.parse_args()
    known = {case.identifier: case for case in SCENARIOS}
    if args.test and any(identifier not in known for identifier in args.test):
        parser.error("Unknown scenario ID; use Live tests to view the catalog")
    try:
        runner = Runner(args.config)
        if args.test or args.all:
            runner.interactive = False
            cases = SCENARIOS if args.all else [known[identifier] for identifier in args.test]
            groups = ("local", "remote") if args.models == "both" else (args.models,)
            modes = (
                MODES
                if args.modes == "both"
                else ("Streaming" if args.modes == "streaming" else "Non-streaming",)
            )
            return runner.run(cases, dimensions=(groups, modes))
        return runner.main()
    except (EOFError, KeyboardInterrupt):
        print("\nExited.")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(failure(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
