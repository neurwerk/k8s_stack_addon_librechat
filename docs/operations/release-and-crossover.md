# Release and crossover

## Release prerequisites

Use the [manifest](../../release/manifest.yaml) from the exact released commit for prerequisites and enabled packages. Base `v0.3.26` is incompatible: its signed release lacks the shared DocumentDB and OIDC provisioning charts required by this add-on.

Before publication, verify the runtime Tooling image and standalone `stack-setup` release are published and match the reviewed versions, and record the exact reviewed Base release candidate. Run the full check and candidate validation from [development](../development/README.md#requirements-and-checks). Verify image digests and permission-hook compatibility against the pinned LibreChat image using shared [image-release guidance](https://github.com/neurwerk/docs/blob/main/dev/operations/image-releases.md); reuse applicable operator-confirmed checks.

After review and merge, obtain authorization to create and publish an annotated tag on the approved commit. Verify the remote tag target and publish GitHub release notes linking to this procedure and the manifest, stating the required Base version without implying it is already available. The add-on may be published after validation against the reviewed Base candidate; installation and adoption require the published, verified signed Base release. This add-on uses an annotated release tag and clients select its exact commit. This repository has CI for branches and pull requests, but no tag publication workflow. Client adoption and reconciliation require their own approval.

## Replace a Base-owned installation

This is a hard crossover with an operator-approved loss of LibreChat conversations, not an in-place data migration. Record the old and new source revisions, the exact product resources being replaced and the approved data-loss scope before execution. Backups must cover retained shared state independently of production storage.

1. Stop reconciliation of the old LibreChat stages and stop their workloads before enabling the add-on. Remove the old product definitions from the client graph so they cannot return. Inspect Flux prune and Helm ownership before removing conflicting product resources; the old and new sources must never manage the same object concurrently.
2. Preserve shared PostgreSQL/DocumentDB servers, Keycloak, OpenBao, storage, CA material and valid credentials. Do not re-bootstrap shared services or rotate credentials for the crossover. Conversation-discard approval does not authorize deleting namespaces, shared databases, volumes or buckets; approve any required product-only deletion by exact resource separately. Retain attachments and unrelated product data unless their deletion is explicitly included.
3. Verify and adopt the exact published, signed Base prerequisite and install the matching standalone `stack-setup`. Review its add-on catalog and provision only the add-on's scoped credentials using its documented procedure, preserving existing valid values. Supply the client-owned ConfigMaps listed in the manifest, explicit OIDC approvals and allowed AgentGateway binding IDs.
4. Select the add-on release's exact 40-character commit using `spec.ref.commit` and enable `frontendLibrechat.enabled`. Reconcile namespaces and Secret delivery first, then database and access provisioning, OIDC settings/client and certificate approval, then the application according to the manifest dependencies. Keep RAG and code interpreter excluded.
5. Inspect Flux sources, Kustomizations, HelmReleases, warning events and bounded application logs. Verify database/cache readiness, successful permission provisioning, OIDC sign-in, intended USER/ADMIN permissions and an approved model/MCP route; accept relevant operator-confirmed feature results. Confirm shared services and retained data remain usable.

After discarded data or database changes, reverting a Git source is not a data rollback. Keep the old installation stopped and use an approved forward fix or component-native restore from an independent backup; never move an existing release tag.
