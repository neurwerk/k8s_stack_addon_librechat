"""Valkey chart/application version bumps must not change immutable storage."""

import copy
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from helm import ROOT, render, resource


class ValkeyStorageTests(unittest.TestCase):
    def existing_statefulset(self):
        return {
            "metadata": {
                "annotations": {
                    "meta.helm.sh/release-name": "catalog-test",
                    "meta.helm.sh/release-namespace": "catalog-test",
                },
                "labels": {"app.kubernetes.io/managed-by": "Helm"},
            },
            "spec": {"volumeClaimTemplates": [{
                "apiVersion": "v1", "kind": "PersistentVolumeClaim",
                "metadata": {
                    "name": "frontend-librechat-valkey-data",
                    "labels": {"helm.sh/chart": "frontend-librechat-valkey-1.0.0"},
                    "annotations": {"example.test/original": "preserve"},
                },
                "spec": {
                    "accessModes": ["ReadWriteOnce"], "volumeMode": "Filesystem",
                    "resources": {"requests": {"storage": "5Gi"}},
                    "storageClassName": "example-storage",
                },
                "status": {"phase": "Pending"},
            }]},
        }

    def render_upgrade(self, existing, *, persistence=None, versions=("1.0.2",), check=True):
        # Replace only the API read in a temporary chart; exercise the production
        # ownership/shape checks and preservation branch without a live cluster.
        lookup = 'lookup "apps/v1" "StatefulSet" .Release.Namespace "frontend-librechat-valkey-stateful-set"'
        values = {"syntheticExisting": existing, "frontendLibrechat": {"valkey": {
            "persistence": persistence or {"size": "5Gi", "storageClassName": "example-storage"},
        }}}
        results = []
        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory) / "valkey"
            shutil.copytree(ROOT / "charts/librechat/valkey", chart)
            template = chart / "templates/stateful-set.yaml"
            source = template.read_text()
            self.assertEqual(source.count(lookup), 1)
            template.write_text(source.replace(lookup, "(.Values.syntheticExisting | default dict)"))
            metadata = yaml.safe_load((chart / "Chart.yaml").read_text())
            for version in versions:
                metadata.update(version=version, appVersion=version)
                (chart / "Chart.yaml").write_text(yaml.safe_dump(metadata))
                results.append(render(str(chart), values, check=check))
        return results

    def test_owned_existing_templates_survive_repeated_version_bumps_exactly(self):
        existing = self.existing_statefulset()
        claims = existing["spec"]["volumeClaimTemplates"]
        results = self.render_upgrade(existing, versions=("1.0.2", "2.0.0", "3.0.0"))
        for result in results:
            self.assertEqual(resource(result, "StatefulSet")["spec"]["volumeClaimTemplates"], claims)

    def test_foreign_or_missing_helm_ownership_is_rejected(self):
        for field in ("meta.helm.sh/release-name", "meta.helm.sh/release-namespace", "app.kubernetes.io/managed-by"):
            for value in (None, "foreign"):
                with self.subTest(field=field, value=value):
                    existing = self.existing_statefulset()
                    section = "labels" if field == "app.kubernetes.io/managed-by" else "annotations"
                    if value is None:
                        existing["metadata"][section].pop(field)
                    else:
                        existing["metadata"][section][field] = value
                    result = self.render_upgrade(existing, check=False)[0]
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("not owned by this Helm release", result.stderr)

    def test_malformed_claim_shapes_and_unsupported_storage_are_rejected(self):
        claim = self.existing_statefulset()["spec"]["volumeClaimTemplates"][0]
        candidates = [None, {}, [], [claim, claim], [None], [{}],
                      [{**claim, "metadata": None}],
                      [{**claim, "metadata": {"name": "other"}}],
                      [{**claim, "spec": []}]]
        for override in [
            {"accessModes": ["ReadWriteMany"]},
            {"accessModes": ["ReadWriteOnce", "ReadOnlyMany"]},
            {"volumeMode": "Block"}, {"selector": {}},
            {"dataSource": {"name": "snapshot"}}, {"volumeName": "other-volume"},
            {"resources": None}, {"resources": {"requests": {}}},
            {"resources": {"requests": {"storage": "5Gi", "cpu": "1"}}},
            {"resources": {"requests": {"storage": "5Gi"}, "limits": {"storage": "5Gi"}}},
        ]:
            changed = copy.deepcopy(claim)
            changed["spec"].update(override)
            candidates.append([changed])
        for index, claims in enumerate(candidates):
            with self.subTest(case=index):
                existing = self.existing_statefulset()
                existing["spec"]["volumeClaimTemplates"] = claims
                result = self.render_upgrade(existing, check=False)[0]
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("existing Valkey", result.stderr)

    def test_size_and_explicit_class_changes_are_rejected(self):
        for persistence, message in [
            ({"size": "6Gi", "storageClassName": "example-storage"}, "size is immutable"),
            ({"size": "5Gi", "storageClassName": "other-storage"}, "storage class is immutable"),
        ]:
            with self.subTest(persistence=persistence):
                result = self.render_upgrade(self.existing_statefulset(), persistence=persistence, check=False)[0]
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_default_volume_mode_and_unset_class_preserve_installed_template(self):
        for installed_class in (None, "example-storage"):
            with self.subTest(installed_class=installed_class):
                existing = self.existing_statefulset()
                spec = existing["spec"]["volumeClaimTemplates"][0]["spec"]
                spec.pop("volumeMode")
                if installed_class is None:
                    spec.pop("storageClassName")
                result = self.render_upgrade(existing, persistence={"size": "5Gi", "storageClassName": ""})[0]
                self.assertEqual(resource(result, "StatefulSet")["spec"]["volumeClaimTemplates"],
                                 existing["spec"]["volumeClaimTemplates"])

    def test_fresh_claim_templates_are_stable_across_version_bumps(self):
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
