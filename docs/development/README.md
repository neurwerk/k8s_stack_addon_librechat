# Development

## Requirements and checks

Run commands from this repository's root. Install the tools pinned in [.tool-versions](../../.tool-versions) through the workspace's approved tool setup, and provide Python compatible with [pyproject.toml](../../pyproject.toml). The checks need a local Tooling checkout with `addon-check`; `ADDON_TOOLING` overrides its default location.

```bash
export WORKSPACE_ROOT=/absolute/path/to/k8s_stack
mise exec -- make check
```

[Makefile](../../Makefile) runs frozen Tooling validation, strict Helm lint/render validation for every chart, Kustomize/schema validation for the selected release packages, and Python test discovery in `tests/charts`. It does not deploy resources. Kubeconform ignores missing schemas, so a successful run is not complete CRD validation. Dependency resolution and schema retrieval may require network access.

For a reviewed Base candidate, run from the add-on root with explicit absolute paths:

```bash
mise exec -- uv run --frozen --project "$WORKSPACE_ROOT/tooling" addon-check "$PWD" --base /absolute/path/to/base-candidate --installable
```

[CI](../../.github/workflows/ci.yml) runs the full check on main pushes and pull requests with its own pinned Tooling revision. Local Tooling and CI pins must be considered when comparing results. There is no application build or image publication workflow in this repository.

## Change locations

| Change | Source |
| --- | --- |
| Product defaults and generated application settings | [shared values](../../charts/librechat/shared/values.yaml), `shared/templates/config-map.yaml`, model/cost/speech helpers. |
| App environment, probes, storage and egress | [app chart](../../charts/librechat/app); speech settings also appear in shared values. |
| Role/cache integration with upstream | [permission adapter](../../charts/librechat/app/files/provision-permissions.cjs), [health adapter](../../charts/librechat/app/files/valkey-health.cjs), and their chart templates. |
| Composition, value precedence and prerequisites | [releases](../../releases/librechat) and [release manifest](../../release/manifest.yaml). |
| Regression checks | [tests/charts](../../tests/charts), including catalog ownership, attachments and delegated files. |

Keep application image pins in owning chart defaults. Before changing an upstream image, follow shared [image-release guidance](https://github.com/neurwerk/docs/blob/main/dev/operations/image-releases.md), including verification of the permission adapter against the target image. Local chart tests cannot establish compatibility with an unexamined upstream runtime.
