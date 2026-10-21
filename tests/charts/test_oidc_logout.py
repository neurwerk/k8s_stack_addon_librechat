"""Keep LibreChat logout within the provisioning Job's exact URL allowlist."""

import unittest

import yaml

from helm import render, resource


class OidcLogoutTests(unittest.TestCase):
    def test_logout_destination_matches_the_provisioned_application_origin(self):
        for hostname in ("chat.example.test", "assistant.example.test"):
            with self.subTest(hostname=hostname):
                values = {
                    "frontendLibrechat": {
                        "enabled": True,
                        "hostname": hostname,
                        "adminPanel": {"hostname": "admin.example.test"},
                    },
                }
                deployment = resource(render("librechat/app", values), "Deployment")
                container = deployment["spec"]["template"]["spec"]["containers"][0]
                logout = [
                    entry["value"] for entry in container["env"]
                    if entry["name"] == "OPENID_POST_LOGOUT_REDIRECT_URI"
                ]
                self.assertEqual(logout, [f"https://{hostname}"])
                env = {entry["name"]: entry for entry in container["env"]}
                self.assertEqual(env["OPENID_USE_END_SESSION_ENDPOINT"]["value"], "true")
                settings = resource(render("librechat/oidc", values), "ConfigMap")
                auth = yaml.safe_load(settings["data"]["values.yaml"])["authentication"]
                self.assertEqual(logout, [auth["webOrigins"][0]])
                self.assertNotEqual(logout[0], auth["webOrigins"][1])
