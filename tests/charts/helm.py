"""Small offline Helm helpers shared by chart tests."""

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LINT_VALUES = ROOT / "tests/validation/helm-lint-values.yaml"


def render(
    chart,
    values=None,
    *,
    namespace="catalog-test",
    release="catalog-test",
    value_files=(LINT_VALUES,),
    extra_args=(),
    check=True,
):
    command = ["helm", "template", release, str(ROOT / "charts" / chart), "--namespace", namespace]
    for path in value_files:
        command.extend(("--values", str(path)))
    result = subprocess.run(
        [*command, "--values", "-", *extra_args],
        input=json.dumps(values or {}),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(result.stderr + result.stdout)
    return result


def documents(result):
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(result, kind, name=None):
    matches = [
        doc
        for doc in documents(result)
        if doc["kind"] == kind and (name is None or doc["metadata"]["name"] == name)
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind} {name}, found {len(matches)}")
    return matches[0]
