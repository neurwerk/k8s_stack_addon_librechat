"""LibreChat upload configuration follows the shared attachment contract."""

import unittest

from helm import render


class DocumentAttachmentTests(unittest.TestCase):
    def test_bad_enabled_settings_fail(self):
        self.assertNotEqual(render(
            "librechat/shared",
            {"frontendLibrechat": {"documentAttachments": {"enabled": "false"}}},
            check=False,
        ).returncode, 0)

    def test_opt_in_uses_mib_and_preserves_disabled_output(self):
        disabled = render("librechat/shared", {}).stdout
        self.assertNotIn("fileConfig:", disabled)
        self.assertNotIn("imageOutputType:", disabled)
        values = {"frontendLibrechat": {"documentAttachments": {"enabled": True}}}
        enabled = render("librechat/shared", values).stdout
        for text in ("fileConfig:", "AgentGateway:", "fileLimit: 5", "fileSizeLimit: 20",
                     "totalSizeLimit: 40", "fallback: provider", "'^application/pdf$'", "'^text/csv$'"):
            self.assertIn(text, enabled)
        self.assertNotIn("'^image/", enabled)
        values["documentAttachments"] = {"fileBytes": 1048576, "totalBytes": 2097152, "count": 2}
        changed = render("librechat/shared", values).stdout
        self.assertIn("fileSizeLimit: 1", changed)
        self.assertIn("totalSizeLimit: 2", changed)
        self.assertIn("fileLimit: 2", changed)
        values["frontendLibrechat"]["documentAttachments"]["imagesEnabled"] = True
        for version in (1, 2, "3"):
            values["guardrails"] = {"llmPolicyEngine": {"attachmentPolicyVersion": version}}
            self.assertIn("image uploads require", render("librechat/shared", values, check=False).stderr)
        values["guardrails"]["llmPolicyEngine"]["attachmentPolicyVersion"] = 3
        images = render("librechat/shared", values).stdout
        for text in ("imageOutputType: png", "'^image/jpeg$'", "'^image/png$'", "'^image/heic$'"):
            self.assertIn(text, images)
        self.assertNotIn("'^image/webp$'", images)
        values["guardrails"]["llmPolicyEngine"]["attachmentPolicyVersion"] = 4
        v4_images = render("librechat/shared", values).stdout
        for text in ("imageOutputType: png", "'^image/jpeg$'", "'^image/png$'",
                     "'^image/heic$'", "'^image/webp$'"):
            self.assertIn(text, v4_images)
        values["guardrails"]["llmPolicyEngine"]["attachmentPolicyVersion"] = "4.1"
        self.assertEqual(render("librechat/shared", values).stdout, v4_images)
        values["guardrails"]["llmPolicyEngine"]["attachmentPolicyVersion"] = 4.1
        self.assertIn("image uploads require", render("librechat/shared", values, check=False).stderr)
        values["frontendLibrechat"]["documentAttachments"]["enabled"] = False
        self.assertIn("image uploads require", render("librechat/shared", values, check=False).stderr)
