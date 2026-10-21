# Architecture

## Ownership and components

The LibreChat deployment charts, release packages, runtime adapters and validation tests moved from Base into this add-on. The repository references upstream images; it does not build an application fork. See [provenance](../provenance.md) and the image defaults in each component chart.

| Owner | Responsibility and source |
| --- | --- |
| Add-on | [App](../../charts/librechat/app), [admin panel](../../charts/librechat/admin-panel), [Meilisearch](../../charts/librechat/meilisearch) and [Valkey](../../charts/librechat/valkey) packaging; [shared configuration](../../charts/librechat/shared); product access, OIDC, database, Secret delivery and certificate-approval stages under [releases/librechat](../../releases/librechat). |
| Base | Shared Keycloak, AgentGateway, PostgreSQL/DocumentDB, OpenBao, certificate trust, ingress and storage; reusable `charts/postgres/documentdb-addon`, `charts/keycloak/addon-access` and `charts/keycloak/addon-oidc`. |
| Tooling | Reusable provisioning commands, add-on validation and `stack-setup` credential catalog/setup. Charts invoke these helpers rather than duplicating setup automation. |
| Client | Immutable `librechat-addon` source, namespace-local input ConfigMaps, OIDC scope/binding approval, product settings and ordered Flux stages. Required inputs are listed in the [manifest](../../release/manifest.yaml). |

The `app` stage installs shared configuration, LibreChat, the admin panel, search and cache. RAG and code-interpreter directories are retained source, absent from the installable package list. Their enable flags do not make them supported release stages.

## Browser identity and authorization

The app uses Keycloak OIDC with `openid profile email`, token reuse and role checks on `realm_access.roles`. Email login and registration are disabled. The [OIDC settings chart](../../charts/librechat/oidc/templates/settings.yaml) derives exact origins and callbacks from the chat and admin hostnames. Both login callbacks terminate on the chat hostname: `/oauth/openid/callback` and `/api/admin/oauth/openid/callback`. The admin panel calls LibreChat's API and has its own session Secret.

The [access stage](../../releases/librechat/access/access.yaml) owns `librechat-user` and `librechat-admin`; the latter includes the former. The OIDC stage configures an `agentgateway` audience, refresh-token rotation and user-token forwarding through Base's provisioning chart. Clients must explicitly approve the scope and binding selection; product admission does not grant model, MCP or company-provider permissions. See shared [authentication](https://github.com/neurwerk/docs/blob/main/dev/authentication/README.md).

The [permission adapter](../../charts/librechat/app/files/provision-permissions.cjs) runs as a pre-install/pre-upgrade Helm Job using the app image. USER and ADMIN may use Agents and Marketplace; only ADMIN may create, share or publicly share Agents. It preserves unrelated permission fields, requires the base tenant and shared Redis cache, and verifies database, cached and effective role values. Module, database, cache and deadline failures fail the release gate. This adapter depends on the pinned upstream image's internal APIs.

## Model and MCP requests

The [model helper](../../charts/librechat/shared/templates/_helpers.tpl) combines the selected OpenRouter catalog, client model definitions and explicit `self-hosted-api-providers` and `external-api-providers` entries. Every effective model must belong to exactly one enabled provider with `routes.api.enabled: true`, `openai-chat-completions-v1` and a `company` credential source or self-hosted `credentialSources: [none]`. Catalog visibility does not authorize invocation.

The [generated LibreChat configuration](../../charts/librechat/shared/templates/config-map.yaml) forwards the user's OIDC access token as `Authorization: Bearer ...`. Model URLs use `<origin><routes.api.path>/v1`, defaulting to `<origin>/bindings/<id>/v1` when `routes.api.path` is absent. A custom prefix replaces the default; it must match the effective Base gateway binding. `primaryBinding` names one endpoint `AgentGateway`; others use `AgentGateway-<id>`.

MCP selection comes from enabled `mcp-servers.catalog.presets` and `.custom` entries. Only route names reach LibreChat, not native provider credentials. MCP URLs are constructed as `<origin>/mcp/<canonical-server-id>`; there is no corresponding custom-prefix input here. The same user token authorizes gateway requests. Gateway enforcement applies only to routed requests; optional server speech connects directly to its configured service.

## Data and Secret delivery

LibreChat stores application data in the Mongo-compatible DocumentDB service hosted by shared operations PostgreSQL. The database stage provisions the LibreChat user through Base's DocumentDB add-on chart. DocumentDB's broad Mongo roles permit only one document-store product on this instance; database names do not isolate products.

[Secret delivery](../../releases/librechat/secret-sync) supplies runtime values in `frontend-librechat`, the database password in `infra-postgres-operations`, and the OIDC client secret in `auth-keycloak`. Setup must keep those corresponding credentials consistent. The shared chart turns runtime values into app/admin Secrets; applications consume them without embedding credentials in ConfigMaps.

Meilisearch owns the search index; Valkey supplies shared cache and streams. The app mounts an images PVC, while uploads, skills, logs and temporary paths use `emptyDir`. Optional object storage uses a Rook bucket claim and browser-reachable HTTPS URLs. Retention and crossover decisions must account for these different storage paths; see [operations](../operations/README.md).
