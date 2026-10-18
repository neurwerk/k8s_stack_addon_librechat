# LibreChat addon

LibreChat, its admin panel, Meilisearch, and Valkey use Base's identity, gateway, database, and storage services.

- [Configuration](configuration.md)
- [Release contract](../release/manifest.yaml)
- [Provenance](provenance.md)
- [Release and crossover](operations/release-and-crossover.md)

Clients select an exact addon revision and enable its namespace, secret, database, access, OIDC, certificate, and application stages.
RAG and code interpreter sources are retained but excluded from installation.

## Shared services and access

The addon owns its database user, application roles, OIDC client, secret delivery and certificate approval. Base owns the shared servers and reusable provisioning charts. DocumentDB's broad Mongo roles permit only one document-store product on this instance; separate database names do not isolate products.

Clients explicitly approve the OIDC scopes and exact AgentGateway binding IDs. User tokens retain the user's own model, MCP and company-provider permissions; addon selection grants no user permissions.

## Crossover

Follow the [release and crossover procedure](operations/release-and-crossover.md) before replacing a Base-owned installation. Fresh installations and later removal retain databases, volumes and credentials by default.
