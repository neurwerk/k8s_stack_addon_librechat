# Operations

## Settings and owners

Clients supply the namespace-local ConfigMaps listed in the [release manifest](../../release/manifest.yaml). `frontendLibrechat.enabled` must agree with the selected stages. Set `frontendLibrechat.hostname` and `.adminPanel.hostname` consistently in the OIDC and application inputs.

The application releases read defaults, client values and `librechat-product-values` in that order; later values win. The shared release also imports optional model/pricing catalogs and `librechat-agentgateway-model-values`, never credential-bearing Helm values. It creates ExternalSecrets that deliver canonical add-on records directly into final application Secrets. Inspect each [HelmRelease](../../releases/librechat/app) for its exact precedence. Supply the same speech, object-storage and other cross-chart settings to their consumers.

| Setting/input | Purpose |
| --- | --- |
| `librechat-oidc-approval-values` | Client approval of browser OIDC scope and exact gateway bindings for Base's OIDC provisioning. |
| `librechat-agentgateway-model-values` | Client-owned grouped API providers; model routes must match the Base gateway's actual `routes.api.path`. |
| `frontendLibrechat.agentGateway` | Internal origin/host allowance, primary binding, optional default model and streaming selection. |
| `mcp-servers.enabled`, `mcp-servers.catalog` | Enabled gateway MCP routes; the renderer uses `/mcp/<canonical-server-id>`. |
| `frontendLibrechat.objectStorage` | Optional bucket storage; the app requires a browser-reachable HTTPS endpoint and controller-owned bucket credentials. |
| Memory, speech, attachments, delegation and cost display | Opt-in settings described in [configuration](../configuration.md). |

Defaults and resource settings live in [chart values](../../charts/librechat). Private values belong to OpenBao/Secret delivery. Tooling owns setup and refresh procedures; use shared [OpenBao operations](https://github.com/neurwerk/docs/blob/main/dev/operations/openbao.md), preserving existing credentials during adoption.

## Adoption and verification

Follow [release and crossover](release-and-crossover.md) for publication, immutable client adoption and replacing an existing Base-owned installation. Use the selected manifest's exact prerequisites and package dependencies. The sequence is namespaces → Secret delivery → database/access → OIDC, with certificate approval after namespaces and the app gated on database, OIDC and certificates. Clients own Flux readiness gates; HelmRelease dependencies add service-level gates.

After authorized reconciliation, follow shared [upgrade verification](https://github.com/neurwerk/docs/blob/main/dev/operations/upgrades.md#after-deployment). Confirm the intended source revision, Secret delivery, database provisioning, `keycloak-librechat-access`, `librechat-oidc-settings`, `keycloak-librechat-oidc` and application releases. Check the permission Job result and bounded app logs before judging the product ready. Validate sign-in, USER/ADMIN behavior and an approved model/MCP request, accepting applicable operator-confirmed results.

The app's init container waits for HTTPS OIDC discovery with an exact issuer and required HTTPS endpoints. Its custom [health probe](../../charts/librechat/app/files/valkey-health.cjs) checks HTTP health and Valkey identity. A Valkey outage removes readiness while keeping the process alive; recovery after an outage or a changed Valkey run ID fails liveness so Kubernetes restarts the app with fresh Redis clients. Do not interpret an available admin-panel `/health` endpoint as proof of database or gateway functionality.

## Retention and recovery

The manifest retains databases, volumes and credentials by default. Removing workload stages does not authorize deleting their namespace, PVCs, bucket or shared state. Retained storage is not an independent backup, and the app's temporary volumes are not durable attachment storage.

For a failed adoption, preserve shared services and valid credentials and use the approved forward fix or component-native restore described in [crossover recovery](release-and-crossover.md). A Git/Helm revert does not undo discarded conversations or database changes. Base owns shared-service recovery, Tooling owns credential setup procedures, and the client operator owns the approved restore/data-loss scope.
