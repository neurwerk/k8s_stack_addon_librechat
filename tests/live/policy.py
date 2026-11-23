"""Read the deployed PII policy ConfigMap using an explicit Kubernetes context."""

import hashlib
import json
import subprocess
from dataclasses import dataclass, field


class PolicyError(ValueError):
    """Safe, actionable discovery failure without cluster response contents."""


@dataclass(frozen=True)
class PolicySnapshot:
    resource_version: str
    policy_yaml: str = field(repr=False)

    def summary(self) -> dict:
        return {
            "source": "Kubernetes ConfigMap",
            "resource_version": self.resource_version,
            "configured_policy_read": True,
            "policy_sha256": hashlib.sha256(self.policy_yaml.encode()).hexdigest(),
            "effective_policy_verified": False,
            "pii_status": "BLOCKED",
            "reason": (
                "Configured rules retrieved; gateway/model enforcement, runtime adoption "
                "and user notice preferences still require verification"
            ),
        }


def discover(context: str, namespace: str, configmap: str) -> PolicySnapshot:
    if not all(
        isinstance(value, str) and value.strip() for value in (context, namespace, configmap)
    ):
        raise PolicyError(
            "Set the Kubernetes context, policy namespace and ConfigMap in Settings."
        )
    try:
        result = subprocess.run(
            [
                "kubectl",
                "--context",
                context,
                "--request-timeout=10s",
                "--namespace",
                namespace,
                "get",
                "configmap",
                configmap,
                "--output=json",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError:
        raise PolicyError("kubectl is not installed or not on PATH.") from None
    except subprocess.TimeoutExpired:
        raise PolicyError("Policy read timed out; check cluster connectivity.") from None
    except OSError:
        raise PolicyError("Could not run kubectl; check the local installation.") from None
    if result.returncode:
        raise PolicyError(
            "Cannot read policy; check kubectl context, connectivity and ConfigMap access."
        )
    if len(result.stdout.encode()) > 2 * 1024 * 1024:
        raise PolicyError("Policy ConfigMap response exceeded the size limit.")
    try:
        document = json.loads(result.stdout)
        metadata = document["metadata"]
        policy = document["data"]["policy.yaml"]
        version = metadata["resourceVersion"]
        valid = (
            document["kind"] == "ConfigMap"
            and metadata["name"] == configmap
            and metadata["namespace"] == namespace
            and isinstance(version, str)
            and bool(version)
            and isinstance(policy, str)
            and bool(policy.strip())
            and len(policy.encode()) <= 1024 * 1024
        )
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise PolicyError("Expected a policy.yaml entry in the selected policy ConfigMap.")
    return PolicySnapshot(version, policy)
