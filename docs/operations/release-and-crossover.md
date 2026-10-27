# Release and adoption

Use the exact [manifest](../../release/manifest.yaml) for the first supported Base, SDK and setup baseline. Older add-on definitions are rejected; no compatibility or old-record copy path exists. Candidate validation is not proof that the baseline or tooling image is published.

Publish and verify the SDK wheel/sdist, setup package and product tooling in dependency order. Resolve genuine locks against their published URLs and hashes, run full [checks](../development/README.md#requirements-and-checks), and verify image digests and permission-hook compatibility. The operator runs approved release commands from the workstation. Record actual versions and revisions in release records, not guessed availability in guides.

The tooling image uses the standard pinned Python/locked environment recipe. Before public adoption, verify package visibility and an anonymous pull; repository visibility does not establish package visibility. Tag/publication, immutable client source selection and reconciliation are separate actions. Follow the shared [release procedure](https://github.com/neurwerk/docs/blob/main/dev/operations/image-releases.md).

The tooling publisher accepts `tooling/v<version>` and requires matching package, manifest and lock versions. The operator signs the reviewed tag on the workstation and verifies its signature before pushing, using the workspace-authorized SSH signing agent key; stop if that key is unavailable and never read its private key. `gh release --verify-tag` only checks tag existence, not that signature. The workflow runs full CI and packaged/native smoke checks before publication, rejects an existing version from another revision, and verifies anonymous version/digest pulls before creating `LibreChat Neurwerk add-on tooling v<version>` release notes. Initial public package visibility is a manual gate; rerun failed verification jobs without replacing a published tag.

## Maintenance ownership handoff

Stop the old product reconciliation and consumers during the agreed maintenance window. Prevent old Helm/Flux inventories from pruning final Secrets, the shared settings HelmRelease and ConfigMaps while ownership transfers. Relinquish Helm ownership of `frontend-librechat-secret` and `frontend-librechat-admin-panel-secret` before their ExternalSecrets adopt them. The old Secret-containing-Helm-values path is removed, not retained as fallback.

Stage namespaces, nonsecret settings and delivery objects before workstation setup. Use approved canonical records and the product-owned `addon-librechat-runtime` reader; leave unowned old roles untouched. Gate database, identity and application consumers on their actual delivery readiness. Keep speech features disabled unless selected and supplied, and keep RAG and code interpreter excluded.

No maintenance action implicitly authorizes deleting namespaces, shared databases, PVCs, buckets or OpenBao records. Preserve valid encryption keys and unrelated data. Refresh, provisioning, explicit restart, rotation and removal are separate operations.

After authorized adoption, inspect Flux sources and releases, warning events, bounded logs, database/cache readiness, native permission provisioning, browser sign-in and an approved model/MCP route. Accept applicable operator-confirmed feature tests. A Git revert is not a persistent-data rollback.
