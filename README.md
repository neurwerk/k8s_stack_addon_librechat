# neurwerk.base - LibreChat Add-on

LibreChat chat, its admin panel, Meilisearch and Valkey, packaged as an optional addon to [neurwerk.base](https://base.neurwerk.com/).

| Repository | Description |
| --- | --- |
| [Base chart](https://github.com/neurwerk/k8s_stack_base) | Shared platform charts and release packages. |
| [Studio](https://github.com/neurwerk/k8s_stack_studio) | Web dashboard and API for operating AI platform services. |
| [Tooling](https://github.com/neurwerk/k8s_stack_tooling) | Runtime helpers and setup CLI tools. |
| [PII Engine](https://github.com/neurwerk/k8s_stack_pii_engine) | PII processing and safety policies. |
| [AgentGateway External Processor](https://github.com/neurwerk/k8s_stack_agentgateway_extproc) | Gateway integration with the PII Engine. |
| [Keycloak API Key Bridge](https://github.com/neurwerk/k8s_stack_keycloak_api_key_bridge) | API keys backed by Keycloak permissions. |
| [Keycloak Theme](https://github.com/neurwerk/k8s_stack_keycloak_theme) | Keycloak login pages and emails. |
| [Example client](https://github.com/neurwerk/k8s_stack_client_example_com) | Reference client configuration and Flux deployment graph. |
| [Dify Add-on](https://github.com/neurwerk/k8s_stack_addon_dify) | Optional Dify package. |
| [LibreChat Add-on](https://github.com/neurwerk/k8s_stack_addon_librechat) | LibreChat deployment package (**this repo**). |

## Documentation

See [Repository documentation](docs/README.md) and the [release contract](release/manifest.yaml).

## Contributing and support

Use [GitHub Issues](https://github.com/neurwerk/k8s_stack_addon_librechat/issues) for reproducible bugs and focused feature requests; run `make check` before proposing changes.

## Security

Report vulnerabilities privately through [GitHub security advisories](https://github.com/neurwerk/k8s_stack_addon_librechat/security/advisories/new).

## Licensing

Project-owned content uses the [MIT License](LICENSE); see [provenance](docs/provenance.md) for upstream ownership.
