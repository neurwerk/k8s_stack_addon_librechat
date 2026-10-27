# Development

## Requirements and checks

Run commands from this repository's root with [.tool-versions](../../.tool-versions) and a reviewed Base checkout. The [product tooling project](../../tooling/pyproject.toml) installs exact SDK `0.14.0` in one locked environment; setup `0.7.0` is development-only for required integration tests. Canonical GitHub wheel URLs and archive hashes are recorded in the project and its committed `tooling/uv.lock`; candidate local wheel installations are not a release lock.

```bash
mise exec -- make check BASE_REPO=/absolute/path/to/base
```

[Makefile](../../Makefile) runs frozen Tooling validation, strict Helm lint/render validation for every chart, Kustomize/schema validation for the selected release packages, and Python test discovery in `tests/charts`. It does not deploy resources. Kubeconform ignores missing schemas, so a successful run is not complete CRD validation. Dependency resolution and schema retrieval may require network access.

For a reviewed Base candidate, run from the add-on root with explicit absolute paths:

```bash
mise exec -- uv run --locked --project tooling addon-check "$PWD" --base /absolute/path/to/base-candidate
```

[CI](../../.github/workflows/ci.yml) acquires the manifest's exact Base prerequisite and runs full checks with the locked tooling dependency. Required tests exercise real credential planning with speech disabled or enabled, encryption-key preservation, browser approval and every effective Helm image consumer. Missing setup dependencies or `BASE_REPO` fail rather than skip. Installable validation additionally requires published tooling-image digests; never add fake values to bypass it.

## Change locations

| Change | Source |
| --- | --- |
| Product defaults and generated application settings | [shared values](../../charts/librechat/shared/values.yaml), `shared/templates/config-map.yaml`, model/cost/speech helpers. |
| App environment, probes, storage and egress | [app chart](../../charts/librechat/app); speech settings also appear in shared values. |
| Role/cache integration with upstream | [packaged permission adapter](../../tooling/src/librechat_tooling/payloads/provision-permissions.cjs), [health adapter](../../charts/librechat/app/files/valkey-health.cjs), and their chart templates. |
| Composition, value precedence and prerequisites | [releases](../../releases/librechat) and [release manifest](../../release/manifest.yaml). |
| Regression checks | [tests/charts](../../tests/charts), including catalog ownership, attachments and delegated files. |

Keep application image pins in owning chart defaults. Before changing an upstream image, follow shared [image-release guidance](https://github.com/neurwerk/docs/blob/main/dev/operations/image-releases.md), including verification of the permission adapter against the target image. Local chart tests cannot establish compatibility with an unexamined upstream runtime.

`tooling-build` takes explicit `VERSION` and `REVISION`, uses `tooling/` as its context, and installs one locked environment on the pinned Python base. Native permission code is staged into `/work/payloads` through shared helpers, then executed by the pinned application image; the staging container receives no credentials or ServiceAccount token.
