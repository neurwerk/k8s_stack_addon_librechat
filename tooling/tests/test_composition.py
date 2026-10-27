"""Required real chart composition uses nonsecret inputs and explicit browser approval."""

import json
import os
from pathlib import Path

import pytest
import yaml
from k8s_stack_tooling.addons import load_manifest
from k8s_stack_tooling.addons.helm_images import validate_helm_images
from k8s_stack_tooling.addons.validation import render

ROOT = Path(__file__).resolve().parents[2]


def test_actual_effective_images_and_browser_approval():
    base = os.environ.get("BASE_REPO")
    if not base:
        pytest.fail("BASE_REPO is required for candidate composition")
    addon = load_manifest(ROOT / "release/manifest.yaml")
    packages = {p.name: render(ROOT / p.path, root=ROOT) for p in addon.spec.packages}
    configmaps = {
        (obj["metadata"]["namespace"], obj["metadata"]["name"]): obj
        for objects in packages.values()
        for obj in objects
        if obj["kind"] == "ConfigMap"
    }
    fixture = yaml.safe_load((ROOT / "tests/validation/helm-lint-values.yaml").read_text())
    values = {
        key: fixture[key]
        for key in (
            "authKeycloak",
            "frontendLibrechat",
            "infraAgentgatewayWrapper",
            "external-api-providers",
            "mcp-servers",
            "infraRookCeph",
        )
    }
    values["frontendLibrechat"]["enabled"] = True
    values["frontendLibrechat"]["codeInterpreter"]["enabled"] = False
    hostname = values["frontendLibrechat"]["hostname"]
    admin = values["frontendLibrechat"]["adminPanel"]["hostname"]
    approval = {
        "clientApproval": {
            "clientId": "librechat",
            "redirectUris": [
                f"https://{hostname}/oauth/openid/callback",
                f"https://{hostname}/api/admin/oauth/openid/callback",
            ],
            "webOrigins": [f"https://{hostname}", f"https://{admin}"],
            "realmRoles": ["librechat-user", "librechat-admin"],
            "audiences": ["agentgateway"],
            "gatewayPermissions": values["authKeycloak"]["agentgatewayClientRoles"],
        }
    }
    for item in addon.spec.inputs:
        if item.kind != "ConfigMap":
            continue
        data = (
            values
            if item.name == "client-values"
            else (approval if item.name == "librechat-oidc-approval-values" else {})
        )
        configmaps[(item.namespace, item.name)] = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"namespace": item.namespace, "name": item.name},
            "data": {"values.yaml": json.dumps(data), "catalog.json": "{}"},
        }
    validate_helm_images(
        addon,
        packages,
        sources={
            ("GitRepository", "flux-system", "k8s-stack"): Path(base),
            ("GitRepository", "flux-system", "librechat-addon"): ROOT,
        },
        configmaps=configmaps,
        kube_version="1.34.1",
        api_versions=(
            "gateway.networking.k8s.io/v1",
            "external-secrets.io/v1",
            "policy.cert-manager.io/v1alpha1",
        ),
    )
