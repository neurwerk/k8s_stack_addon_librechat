{{/* Route IDs only; native metadata and credentials never reach LibreChat. */}}
{{- define "frontend-librechat-shared.mcpNames" -}}
{{- if hasKey .Values "mcp" }}{{ fail "root mcp has been removed; use mcp-servers" }}{{ end -}}
{{- $mcp := index .Values "mcp-servers" -}}
{{- $catalog := $mcp.catalog | default dict -}}
{{- $presets := $catalog.presets | default dict -}}
{{- $custom := $catalog.custom | default list -}}
{{- if hasKey $mcp "servers" }}{{ fail "mcp-servers.servers has been removed; configure mcp-servers.catalog" }}{{ end -}}
{{- $names := list -}}
{{- range $id, $selection := $presets -}}
{{- if not (kindIs "bool" $selection.enabled) -}}{{ fail "MCP preset selection requires boolean enabled" }}{{- end -}}
{{- if $selection.enabled -}}{{- $names = append $names $id -}}{{- end -}}
{{- end -}}
{{- range $custom -}}
{{- if not (kindIs "bool" .enabled) -}}{{ fail "MCP custom selection requires boolean enabled" }}{{- end -}}
{{- if .enabled -}}{{- $names = append $names .name -}}{{- end -}}
{{- end -}}
{{- $names | toYaml -}}
{{- end -}}
