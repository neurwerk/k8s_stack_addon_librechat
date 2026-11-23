"""Private, Git-ignored settings for the interactive runner."""

import json
import os
import tempfile
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("settings.local.json")
DEFAULTS = {
    "origin": "",
    "kube_context": "",
    "policy_namespace": "monitor-pii-engine",
    "policy_configmap": "monitor-pii-engine-config-map",
    "refresh": True,
    "local_endpoint": "AgentGateway-local",
    "local_model": "",
    "remote_endpoint": "AgentGateway",
    "remote_model": "",
    "request_headers": "",
}


def load(path: Path) -> dict:
    values = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(values, dict) or values.keys() - DEFAULTS.keys():
        raise ValueError("Unknown settings")
    for key, value in values.items():
        if type(value) is not type(DEFAULTS[key]):
            raise ValueError("Invalid setting type")
    return DEFAULTS | values


def save(path: Path, values: dict) -> None:
    # The local file may contain credentials; always enforce private permissions.
    data = {key: values[key] for key in DEFAULTS}
    descriptor, temporary = tempfile.mkstemp(
        prefix=".live-settings-", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
