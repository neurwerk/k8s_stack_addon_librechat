"""DocumentDB remains exclusive; endpoint declarations may not invent a Service."""

import copy
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from k8s_stack_tooling.addons import ContractError, load_manifest
from k8s_stack_tooling.addons.validation import check_database_claims

ROOT = Path(__file__).resolve().parents[2]


def test_claim_matches_selected_base_and_rejects_second_document_store():
    selected = os.environ.get("BASE_REPO")
    if not selected:
        pytest.fail("BASE_REPO is required for the real service topology")
    addon = load_manifest(ROOT / "release/manifest.yaml")
    claim = addon.spec.databases[0]
    chart = Path(selected) / "charts/postgres/operations"
    result = subprocess.run(
        [
            "helm",
            "template",
            "postgres-operations",
            str(chart),
            "--namespace",
            claim.service.namespace,
            "--show-only",
            "templates/service.yaml",
            "-f",
            str(ROOT / "tests/validation/helm-lint-values.yaml"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    services = [obj for obj in yaml.safe_load_all(result.stdout) if obj]
    service = next(obj for obj in services if obj["metadata"]["name"] == claim.service.name)
    assert {p["name"] for p in service["spec"]["ports"]} == {"postgresql", "documentdb"}
    assert claim.exclusive and claim.engine == "documentdb"
    other = copy.deepcopy(addon)
    other.metadata.name = "second-document-store"
    other.spec.databases[0].database = "SecondStore"
    other.spec.databases[0].owner = "second-document-store"
    with pytest.raises(ContractError, match="exclusive|incompatible"):
        check_database_claims([addon, other])
