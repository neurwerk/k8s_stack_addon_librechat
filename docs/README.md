# LibreChat add-on

This repository packages LibreChat, its admin panel, Meilisearch and Valkey as an optional product. It owns product charts, release stages and runtime adapters; Base supplies shared identity, gateway, database and storage services. Clients select the add-on revision, settings and Flux graph.

- [Architecture](architecture/README.md): components, identity, permissions and ownership.
- [Development](development/README.md): source map and local checks.
- [Operations](operations/README.md): configuration, adoption and recovery.
- [Release manifest](../release/manifest.yaml): exact prerequisites, packages and retention.
- [Provenance](provenance.md): extraction and upstream ownership.

RAG and code interpreter sources are retained but excluded from installation. Replacing a Base-owned LibreChat installation requires the approved [hard crossover](operations/release-and-crossover.md#replace-a-base-owned-installation).
