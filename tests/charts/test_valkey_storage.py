"""Valkey chart/application version bumps must not change immutable storage."""

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from helm import ROOT, render, resource


class ValkeyStorageTests(unittest.TestCase):
    def test_claim_templates_are_stable_across_version_bumps(self):
        values = {"frontendLibrechat": {"valkey": {"persistence": {
            "size": "5Gi", "storageClassName": "example-storage",
        }}}}
        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory) / "valkey"
            shutil.copytree(ROOT / "charts/librechat/valkey", chart)
            before = resource(render(str(chart), values), "StatefulSet")
            metadata = yaml.safe_load((chart / "Chart.yaml").read_text())
            metadata.update(version="99.0.0", appVersion="99.0.0")
            (chart / "Chart.yaml").write_text(yaml.safe_dump(metadata))
            after = resource(render(str(chart), values), "StatefulSet")
        self.assertNotEqual(before["metadata"]["labels"], after["metadata"]["labels"])
        for field in ("volumeClaimTemplates", "serviceName", "selector"):
            self.assertEqual(before["spec"][field], after["spec"][field])
        claim = before["spec"]["volumeClaimTemplates"][0]
        self.assertNotIn("helm.sh/chart", claim["metadata"]["labels"])
        self.assertNotIn("app.kubernetes.io/version", claim["metadata"]["labels"])
        self.assertEqual(claim["spec"], {
            "accessModes": ["ReadWriteOnce"], "volumeMode": "Filesystem",
            "resources": {"requests": {"storage": "5Gi"}},
            "storageClassName": "example-storage",
        })
