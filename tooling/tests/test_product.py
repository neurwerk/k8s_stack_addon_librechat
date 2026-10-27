"""Product resource packaging and conditional setup behavior."""

from importlib.resources import files
from pathlib import Path
from unittest.mock import Mock

import pytest
from k8s_stack_tooling.addons import expand_setup, load_manifest
from k8s_stack_tooling.addons.schema import AddonSelection
from k8s_stack_tooling.api.payloads import stage_payloads
from openbao_stack_setup import client as client_module
from openbao_stack_setup import declarative

from librechat_tooling import cli

ROOT = Path(__file__).resolve().parents[2]


def test_installed_payload_stages_through_shared_helper(tmp_path, monkeypatch):
    def stage(source, resources):
        return stage_payloads(source, resources, destination=tmp_path)

    monkeypatch.setattr(cli, "stage_payloads", stage)
    cli.main()
    payload = tmp_path / "provision-permissions.cjs"
    assert (
        payload.read_bytes()
        == (files("librechat_tooling") / "payloads/provision-permissions.cjs").read_bytes()
    )
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize(
    "stt,tts", [(False, False), (True, False), (False, True), (True, True)]
)
def test_speech_fields_and_waits_activate_independently(stt, tts):
    addon = load_manifest(ROOT / "release/manifest.yaml")
    selected = AddonSelection.model_validate(
        {
            "id": "librechat",
            "sourceRef": {
                "kind": "GitRepository",
                "namespace": "flux-system",
                "name": "librechat-addon",
            },
            "features": {"stt-auth": stt, "tts-auth": tts},
        }
    )
    setup = expand_setup(addon, selected)
    speech = next((record for record in setup.records if record.id == "speech"), None)
    enabled = {direction for direction, active in (("stt", stt), ("tts", tts)) if active}
    assert (set(speech.fields) if speech else set()) == {f"{d}ApiKey" for d in enabled}
    assert {group.id for group in setup.input_groups} == enabled
    waits = {target.name for target in setup.lifecycle.delivery}
    for direction in ("stt", "tts"):
        assert (f"frontend-librechat-{direction}-secret" in waits) == (direction in enabled)
    assert not setup.handover
    snapshots = {}
    client = Mock(spec=client_module.OpenBaoClient)
    client.read_secret.side_effect = snapshots.get
    supplied = {
        "librechat": {direction: {"apiKey": "synthetic-speech-input"} for direction in enabled}
    }
    planned = declarative.plan_credentials(client, {"librechat": setup}, supplied=supplied)
    for write in planned.writes:
        snapshots[write.path] = client_module.SecretRecord(values=write.values, version=1)
    assert not declarative.plan_credentials(
        client,
        {"librechat": setup},
        supplied=supplied,
    ).writes
    runtime = snapshots["addons/librechat/runtime"].values
    runtime["credsKey"] = "invalid-retained-key"
    with pytest.raises(client_module.OpenBaoError):
        declarative.plan_credentials(client, {"librechat": setup}, supplied=supplied)
    client.write_secret.assert_not_called()
