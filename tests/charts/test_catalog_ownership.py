"""Client product settings override optional shared catalog defaults."""

import unittest

import yaml

from helm import ROOT


class CatalogOwnershipTests(unittest.TestCase):
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
