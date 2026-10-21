"""Client product settings override optional shared catalog defaults."""

import copy
import unittest

import yaml

from helm import ROOT, render, resource


class CatalogOwnershipTests(unittest.TestCase):
    def test_grouped_release_requires_exact_base_and_rejects_legacy_inputs(self):
        manifest = yaml.safe_load((ROOT / "release/manifest.yaml").read_text())
        self.assertEqual(manifest["spec"]["prerequisites"]["base"], "0.3.29")
        for legacy, message in [
            ({"aiGateway": {"bindings": []}}, "aiGateway.bindings has been removed"),
            ({"mcp": {"enabled": False}}, "root mcp has been removed"),
        ]:
            with self.subTest(legacy=legacy):
                result = render("librechat/shared", legacy, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def config(self, values):
        result = render("librechat/shared", values, value_files=(
            ROOT / "tests/validation/helm-lint-values.yaml",
            ROOT / "releases/shared/default-mcp-settings.yaml",
        ))
        return yaml.safe_load(resource(result, "ConfigMap", "frontend-librechat-config-map")["data"]["librechat.yaml"])

    def grouped_values(self):
        values = yaml.safe_load((ROOT / "tests/validation/helm-lint-values.yaml").read_text())
        values["frontendLibrechat"]["agentGateway"].update(
            primaryBinding="example", defaultModel="remote/example/model",
            origin="http://gateway.example.test:8082")
        return values

    def test_grouped_api_models_preserve_paths_defaults_and_identity(self):
        values = self.grouped_values()
        provider = values["external-api-providers"][0]
        provider["routes"]["api"]["path"] = "/custom/api"
        local = copy.deepcopy(provider)
        local.update(id="local", provider="Custom", credentialSources=["none"],
                     models=[{"name": "local/chat", "upstreamModel": "local-upstream"}])
        local.pop("authSecret")
        local["routes"]["api"].pop("path")
        values["self-hosted-api-providers"] = [local]
        config = self.config(values)
        endpoints = {entry["name"]: entry for entry in config["endpoints"]["custom"]}
        origin = values["frontendLibrechat"]["agentGateway"]["origin"]
        self.assertEqual(endpoints["AgentGateway"]["baseURL"], origin + "/custom/api/v1")
        self.assertEqual(endpoints["AgentGateway-local"]["baseURL"], origin + "/bindings/local/v1")
        for endpoint, model in [("AgentGateway", "remote/example/model"), ("AgentGateway-local", "local/chat")]:
            self.assertEqual(endpoints[endpoint]["models"], {"default": [model], "fetch": False})
            self.assertEqual(endpoints[endpoint]["headers"]["Authorization"], "Bearer {{LIBRECHAT_OPENID_ACCESS_TOKEN}}")
            self.assertEqual(endpoints[endpoint]["apiKey"], "unused")
        specs = {spec["name"]: spec for spec in config["modelSpecs"]["list"]}
        self.assertTrue(specs["remote/example/model"]["default"])
        self.assertEqual(specs["local/chat"]["preset"]["endpoint"], "AgentGateway-local")
        values["frontendLibrechat"]["agentGateway"]["defaultModel"] = "local/chat"
        self.assertTrue(next(spec for spec in self.config(values)["modelSpecs"]["list"]
                             if spec["name"] == "local/chat")["default"])

    def test_ineligible_providers_cannot_satisfy_company_local_binding(self):
        for case in ("disabled", "api-disabled", "api-missing", "caller-only", "profile", "subscription", "external-none"):
            with self.subTest(case=case):
                values = self.grouped_values()
                provider = values["external-api-providers"][0]
                if case == "disabled":
                    provider["enabled"] = False
                elif case == "api-disabled":
                    provider["routes"]["api"]["enabled"] = False
                elif case == "api-missing":
                    provider.pop("routes")
                elif case == "caller-only":
                    provider["credentialSources"] = ["caller_supplied"]
                elif case == "profile":
                    provider["profiles"] = ["openai-responses-v1"]
                elif case == "subscription":
                    values["external-subscription-providers"] = values["external-api-providers"]
                    values["external-api-providers"] = []
                else:
                    provider["credentialSources"] = ["none"]
                result = render("librechat/shared", values, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("requires an explicit company/local API binding", result.stderr)

    def test_catalog_selection_still_has_exactly_one_owner(self):
        values = self.grouped_values()
        provider = values["external-api-providers"][0]
        provider["catalogModels"] = [provider.pop("models")[0]["name"]]
        self.assertEqual(self.config(values)["endpoints"]["custom"][0]["models"]["default"],
                         ["remote/example/model"])
        duplicate = copy.deepcopy(provider)
        duplicate["id"] = "duplicate"
        values["self-hosted-api-providers"] = [duplicate]
        result = render("librechat/shared", values, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one API binding", result.stderr)

    def test_client_values_override_optional_catalog(self):
        release = yaml.safe_load((ROOT / "releases/librechat/app/shared.yaml").read_text())
        refs = release["spec"]["valuesFrom"]
        names = [ref["name"] for ref in refs]
        catalog_index = names.index("client-openrouter-catalog-values")
        client_index = names.index("client-values")
        self.assertEqual(refs[catalog_index], {
            "kind": "ConfigMap", "name": "client-openrouter-catalog-values",
            "valuesKey": "values.yaml", "optional": True,
        })
        self.assertLess(catalog_index, client_index)
        self.assertLess(client_index, names.index("librechat-product-values"))
        for index, ref in enumerate(refs):
            if ref["kind"] == "ConfigMap" and (
                ref["name"].startswith("base-shared-") or ref["name"].endswith("-app-defaults")
            ):
                self.assertLess(index, catalog_index, ref["name"])
            if ref["kind"] == "Secret":
                self.assertLess(catalog_index, index)
                self.assertLess(index, client_index)
        model_index = names.index("librechat-agentgateway-model-values")
        self.assertLess(client_index, model_index)
        self.assertLess(model_index, names.index("librechat-product-values"))
