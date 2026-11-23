"""One bounded synthetic turn through LibreChat's signed-in application API."""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def chat(
    opener,
    origin: str,
    headers: dict[str, str],
    endpoint: str,
    model: str,
    *,
    attachment: dict | None = None,
    expected_text: str | None = None,
    save_title: str | None = None,
    disable_streaming: bool = False,
    prompt: str | None = None,
) -> str:
    """Submit once, then require a completed nonempty assistant response."""
    started = time.monotonic()
    payload = {
        "endpoint": endpoint,
        "endpointType": "custom",
        "model": model,
        "text": "Reply with one short greeting. This is a synthetic integration test.",
        "sender": "User",
        "isCreatedByUser": True,
        "messageId": str(uuid.uuid4()),
        "clientRequestId": str(uuid.uuid4()),
        "parentMessageId": "00000000-0000-0000-0000-000000000000",
        "conversationId": None,
        "isTemporary": not bool(save_title),
        "max_tokens": 128,
        # The application event channel stays SSE; this controls model generation.
        "disableStreaming": disable_streaming,
    }
    if attachment is not None:
        payload["files"] = [attachment]
        payload["text"] = "Transcribe the text in the attached image. Keep your answer short."
    if prompt is not None:
        payload["text"] = prompt
        payload["max_tokens"] = 512
    request = urllib.request.Request(
        origin + "/api/agents/chat/" + urllib.parse.quote(endpoint, safe=""),
        data=json.dumps(payload).encode(),
        headers={**headers, "Content-Type": "application/json"},
    )
    conversation_ids = set()

    def remember(event):
        for item in (
            event,
            event.get("conversation"),
            event.get("responseMessage"),
            event.get("requestMessage"),
        ):
            if isinstance(item, dict) and item.get("conversationId"):
                identifier = str(uuid.UUID(item["conversationId"]))
                if identifier not in conversation_ids:
                    conversation_ids.add(identifier)
                    print("Test chat: " + origin + "/c/" + identifier, flush=True)

    completed = False
    try:
        text = _complete(
            opener, request, origin, headers, started, model, expected_text, remember
        )
        completed = True
    finally:
        if save_title:
            for identifier in conversation_ids:
                save_conversation_title(opener, origin, headers, identifier, save_title)
            if not conversation_ids:
                print("WARN no conversation ID received; saved title could not be verified")
                if completed:
                    raise ValueError("Saved conversation could not be identified")
    if save_title:
        for identifier in conversation_ids:
            verify_saved_mode(opener, origin, headers, identifier, disable_streaming)
    return text


def verify_saved_mode(opener, origin, headers, identifier, disable_streaming):
    request = urllib.request.Request(
        origin + "/api/convos/" + identifier,
        headers={**headers, "Accept": "application/json"},
    )
    with opener.open(request, timeout=15) as response:
        body = response.read(1048577)
        if len(body) > 1048576:
            raise ValueError("Oversized conversation response")
        saved = json.loads(body)
    if (
        saved.get("conversationId") != identifier
        or type(saved.get("disableStreaming")) is not bool
        or saved["disableStreaming"] != disable_streaming
    ):
        raise ValueError("Saved model-generation mode missing or mismatched")
    print("PASS saved model-generation mode; upstream wire transport not directly observed")


def _complete(opener, request, origin, headers, started, model, expected_text, remember):
    with opener.open(request, timeout=30) as response:
        if response.headers.get_content_type() in {"text/event-stream", "text/plain"}:
            print("Reading application SSE response", flush=True)
            return verify_stream(response, started, model, expected_text, remember)
        body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("Oversized generation acknowledgement")
        job = json.loads(body)
    stream = job.get("streamId")
    if not isinstance(stream, str) or not stream or job.get("status") != "started":
        raise ValueError("No generation acknowledgement")
    remember(job)
    print("Chat accepted; waiting for terminal response", flush=True)
    request = urllib.request.Request(
        origin + "/api/agents/chat/stream/" + urllib.parse.quote(stream, safe=""),
        headers={**headers, "Accept": "text/event-stream"},
    )
    with opener.open(request, timeout=90) as response:
        if response.headers.get_content_type() != "text/event-stream":
            raise ValueError("Expected SSE response")
        return verify_stream(response, started, model, expected_text, remember)


def save_conversation_title(opener, origin, headers, conversation_id, save_title):
    for attempt in range(4):
        request = urllib.request.Request(
            origin + "/api/convos/update",
            data=json.dumps(
                {
                    "arg": {"conversationId": conversation_id, "title": save_title},
                }
            ).encode(),
            headers={**headers, "Content-Type": "application/json"},
        )
        try:
            with opener.open(request, timeout=15) as response:
                body = response.read(65537)
                if len(body) > 65536:
                    raise ValueError("Oversized saved conversation response")
                saved = json.loads(body)
                if (
                    saved.get("conversationId") != conversation_id
                    or saved.get("title") != save_title
                ):
                    raise ValueError("Saved conversation title did not match")
        except urllib.error.HTTPError as exc:
            if exc.code != 409 or attempt == 3:
                raise
            exc.close()
            time.sleep(1)
            continue
        print("PASS test conversation saved with requested title", flush=True)
        return


def verify_stream(
    response,
    started: float,
    model: str,
    expected_text: str | None = None,
    remember=None,
) -> str:
    total = 0
    data = []
    event_name = ""
    while time.monotonic() - started < 120:
        raw = response.readline(65537)
        total += len(raw)
        if len(raw) > 65536 or total > 1048576:
            raise ValueError("Oversized stream")
        if not raw:
            break
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif line.startswith("event:"):
            event_name = line[6:].strip()
        elif not line and data:
            event = json.loads("\n".join(data))
            data = []
            if not isinstance(event, dict):
                raise ValueError("Unexpected stream event")
            if remember is not None:
                remember(event)
            if event_name == "error" or event.get("error"):
                known = {
                    "Illegal request",
                    "Error parsing conversation",
                    "Error building endpoint option",
                    "Model spec mismatch",
                    "Agent not found",
                }
                for key in ("text", "message", "error"):
                    if isinstance(event.get(key), str) and event[key] in known:
                        raise ValueError("Application rejected chat: " + event[key])
                raise ValueError("Application reported a generation error")
            event_name = ""
            if event.get("final"):
                message = event.get("responseMessage") or {}
                text = message.get("text")
                nonempty = isinstance(text, str) and bool(text.strip())
                texts = [text] if isinstance(text, str) else []
                for part in message.get("content") or []:
                    if not isinstance(part, dict) or part.get("type") != "text":
                        continue
                    text = part.get("text")
                    if isinstance(text, dict):
                        text = text.get("value")
                    nonempty |= isinstance(text, str) and bool(text.strip())
                    if isinstance(text, str):
                        texts.append(text)
                if (
                    message.get("error")
                    or message.get("refusal")
                    or message.get("unfinished")
                    or message.get("finish_reason") not in (None, "stop")
                    or not nonempty
                ):
                    raise ValueError("No successful assistant content")
                if message.get("model") != model:
                    raise ValueError("Response model did not match selected model")
                if expected_text:
                    normalized = " ".join(" ".join(texts).upper().split())
                    expected = " ".join(expected_text.upper().split())
                    if not re.search(r"(?<!\w)" + re.escape(expected) + r"(?!\w)", normalized):
                        raise ValueError(
                            "Expected attachment text absent from assistant response"
                        )
                print(
                    f"PASS completed LibreChat chat ({time.monotonic() - started:.3f}s); "
                    "response text withheld"
                )
                # LibreChat can mirror the content blocks in its legacy text field.
                # Prefer the blocks, never concatenate both representations.
                blocks = texts[1:] if isinstance(message.get("text"), str) else texts
                return "".join(blocks) if any(block.strip() for block in blocks) else texts[0]
    raise ValueError("Stream ended without a verified terminal response")
