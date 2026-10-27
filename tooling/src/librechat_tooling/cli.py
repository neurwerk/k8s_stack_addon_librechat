"""Stage the declared permission adapter for execution in LibreChat's native image."""

from importlib.resources import as_file, files

from k8s_stack_tooling.api.payloads import stage_payloads


def main() -> None:
    with as_file(files("librechat_tooling") / "payloads") as source:
        stage_payloads(source, ["provision-permissions.cjs"])
