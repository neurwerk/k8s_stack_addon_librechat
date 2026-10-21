# LibreChat configuration

These opt-in settings live under `frontendLibrechat` in [shared values](../charts/librechat/shared/values.yaml), with app-side settings in [app values](../charts/librechat/app/values.yaml). See [operations](operations/README.md) for value delivery and precedence.

## Attachments

`documentAttachments.enabled` enables provider delivery for the configured document MIME types. The renderer converts top-level `documentAttachments.fileBytes` and `totalBytes` to MiB and sets the file count from `count`. It validates `pages` as positive but does not render a LibreChat page-limit field. This setting does not enable RAG or grant model attachment permissions.

`documentAttachments.imagesEnabled` also requires document uploads and `guardrails.llmPolicyEngine.attachmentPolicyVersion` 3, 4, or exact string `"4.1"`, after compatible Engine/extProc deployment. Version 3 allows JPEG, PNG and HEIC but not WebP. Versions 4 and 4.1 additionally allow `image/webp`; all retain `imageOutputType: png`. The pinned browser converts HEIC before upload. Upload configuration grants neither a model attachment mode nor image-forwarding permission.

## Agent delegation

`subagents.enabled` exposes foreground delegation; each saved parent agent must select its children. `subagents.fileSharing.enabled` additionally allows current-message attachments to be delegated, and each parent must opt into `shareFiles`. File sharing requires delegation to be enabled. It does not render PDFs or establish a local-only visual processing path. The generated settings disable sibling sharing and bound file count, private bytes and lifetime; see [config-map.yaml](../charts/librechat/shared/templates/config-map.yaml).

## Cost display

`costs.enabled` enables approximate USD/context display. It requires a positive `costs.contextWindows` entry for every effective public model name and matching input/output base rates under `providers`; cache rates are optional. The shared release can import `providers` from `librechat-model-cost-catalog` using `catalog.json`. Reuse the client's canonical gateway catalog rather than maintaining a second price list. This display does not import gateway totals, pricing tiers, reroutes or provider invoices. Validation and model-to-price mapping are in the [cost helper](../charts/librechat/shared/templates/_costs.tpl).

## Memory

`memory.enabled` defaults to false and renders `memory.disabled: true`. Enabling it makes per-user saved memories and their controls available; it does not reset an existing user opt-out. Users otherwise default to on in the pinned application, which has no supported per-user default-off setting.

Automatic updates separately require `memory.agent.enabled: true` and an explicit `memory.agent.model` from the effective model catalog. The generated agent uses that model's gateway endpoint and the user's credentials and permissions, with no new Secret. For a configured model named `local/example`:

```yaml
frontendLibrechat:
  memory:
    enabled: true
    tokenLimit: 2000
    maxInputTokens: 4000
    messageWindowSize: 5
    agent:
      enabled: true
      model: local/example
```

The stored-memory token limit, recent-chat token limit and recent message count must be positive integers. Clients can override these limits and `memory.agent.instructions`. Default instructions save clearly stated lasting preferences, update corrections and honor forget requests. Automatic updates default to off independently of manual memory. No inline composer memory tools are enabled.

`personalize: true` and `interface.memories: true` keep upstream USER/ADMIN memory controls available without changing Agents/Marketplace policy. Users can turn off **Settings > Data controls > Reference saved memories** and add, edit or delete entries in **Memories**. Turning it off stops future use and automatic updates; it does not delete saved entries or prior chat content.

Memories are stored in the existing LibreChat database. Automatic processing adds model calls subject to the selected route's tracing and PII policy. A local memory model does not prevent saved notes being sent with later cloud-model chats.

## Speech

Speech uses the pinned application's existing support, with no application patch or custom image. Both app and shared charts consume identical `speech.stt` and `speech.tts` values. Each defaults to disabled, provider `openai-compatible`, empty `url` and `model`, and `auth.enabled: false`. TTS also defaults to empty `voices` and `allowExternal: false`. Disabled directions create no provider configuration, speech egress, environment variables or ExternalSecrets; disabling both omits speech configuration entirely.

Enabled directions require a model and a full HTTP(S) API URL with a canonical RFC1918 IPv4 address and explicit port from 1 to 65535. For example, `http://10.20.30.40:8000/v1/audio/transcriptions` is a synthetic STT URL, not a default. STT rejects DNS, public, loopback, link-local and noncanonical addresses. URLs cannot contain credentials, queries, fragments, substitutions or encoded characters. Paths use letters, digits, `/`, `.`, `_`, `~` and `-`. The URL determines the exact `host:port` SSRF allowance and `/32` TCP NetworkPolicy rule; there is no separate address/port override.

TTS also requires nonempty voice names. Explicit `speech.tts.allowExternal: true` additionally permits a lowercase DNS HTTPS URL on port 443, omitted or explicit, with a full API path. This approves sending response text to that service. External TTS gets no private-address SSRF exemption and uses the app's existing public TCP 443 egress, which is not a DNS allowlist. Server speech bypasses AgentGateway and PII Engine. HTTPS certificate verification remains enabled.

With an enabled direction and `auth.enabled: true`, the app creates `frontend-librechat-stt-secret` or `frontend-librechat-tts-secret` through `frontend-librechat-openbao-secret-store`. Each reads only `sttApiKey` or `ttsApiKey` from OpenBao KV `frontend-librechat/external`. Required Secret references supply `LIBRECHAT_STT_API_KEY` or `LIBRECHAT_TTS_API_KEY`, and Reloader watches the selected Secrets. The ConfigMap contains the environment placeholder; no-auth providers get `apiKey: ""`. No broad runtime-secret fields are needed.

Speech UI engines default to `external` for enabled directions. These are user defaults, not locks; conversation mode remains user-controlled. Browser recognition is unchanged and may use a cloud service, so these settings do not enforce local-only browser recognition. Keep speech values identical in app and shared releases to align configuration, credentials and egress.

Enabled STT also accepts `autoTranscribeAudio` (boolean, default false), `decibelValue` (negative number, default -45), and `autoSendText` (integer seconds, default -1 to disable). For example, `autoTranscribeAudio: true` and `autoSendText: 3` stop recording after the application's silence interval, transcribe, then send three seconds after successful transcription. Existing browser preferences take precedence; users can change saved settings in Speech settings.
