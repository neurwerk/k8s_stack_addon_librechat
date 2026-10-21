"""Delegation and current-message file sharing require explicit deployment opt-in."""

import unittest

import yaml

from helm import ROOT, render, resource


def agents_config(values):
    # The lint fixture enables code execution; native file sharing needs neither it nor RAG.
    values = {**values, "frontendLibrechat": {
        "codeInterpreter": {"enabled": False},
        "rag": {"enabled": False},
        **values.get("frontendLibrechat", {}),
    }}
    config = resource(render("librechat/shared", values), "ConfigMap",
                      "frontend-librechat-config-map")
    return yaml.safe_load(config["data"]["librechat.yaml"])["endpoints"]["agents"]


class SubagentFileTests(unittest.TestCase):
    def test_defaults_preserve_existing_capabilities_without_sharing(self):
        defaults = yaml.safe_load(
            (ROOT / "charts/librechat/shared/values.yaml").read_text()
        )["frontendLibrechat"]["subagents"]
        self.assertIs(defaults["enabled"], False)
        self.assertIs(defaults["fileSharing"]["enabled"], False)
        self.assertEqual(agents_config({}), {"capabilities": []})
        self.assertEqual(agents_config({"mcp-servers": {"enabled": True}}),
                         {"capabilities": ["tools"]})

    def test_delegation_preserves_tools_without_enabling_sharing(self):
        self.assertEqual(agents_config({
            "mcp-servers": {"enabled": True},
            "frontendLibrechat": {"subagents": {"enabled": True}},
        }), {"capabilities": ["subagents", "tools"]})

    def test_sharing_uses_bounded_defaults_without_sibling_grants(self):
        self.assertEqual(agents_config({"frontendLibrechat": {"subagents": {
            "enabled": True, "fileSharing": {"enabled": True},
        }}}), {
            "capabilities": ["subagents"],
            "fileSharing": {
                "enabled": True,
                "allowSiblingSharing": False,
                "maxFiles": 100,
                "maxPrivateBytes": 268435456,
                "ttlMs": 3600000,
            },
        })

    def test_sharing_requires_delegation(self):
        result = render("librechat/shared", {"frontendLibrechat": {"subagents": {
            "fileSharing": {"enabled": True},
        }}}, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "frontendLibrechat.subagents.fileSharing.enabled requires "
            "frontendLibrechat.subagents.enabled", result.stderr,
        )
