"""Stable scenario IDs shared by local and remote model runs."""

from dataclasses import dataclass

from chat_smoke import chat
from cleanup import PREFIX
from documents import DOCUMENTS, run_document
from fixtures import IMAGE_EXPECTED_TEXT, IMAGE_PATH
from image_upload import upload_image
from session import Session


@dataclass(frozen=True)
class Scenario:
    identifier: str
    name: str
    kind: str
    blocked: str = ""


CATEGORIES = (
    ("Basic chat", "chat"),
    ("PII actions", "pii"),
    ("PII detection and restoration", "restoration"),
    ("Notices", "notices"),
    ("Images", "image"),
    ("Documents / Docling", "documents"),
    ("MCP tools", "mcp"),
)

MODES = ("Streaming", "Non-streaming")


def planned(
    group: int, kind: str, names: tuple[str, ...], reason: str, start: int = 1
) -> tuple[Scenario, ...]:
    return tuple(
        Scenario(f"{group}.{index}", name, kind, reason)
        for index, name in enumerate(names, start)
    )


SCENARIOS = (
    Scenario("1.1", "Basic chat", "chat"),
    *planned(
        1,
        "chat",
        ("Follow-up context", "Unicode", "Long response"),
        "Scenario assertions not implemented",
        start=2,
    ),
    Scenario("2.1", "Image text", "image"),
    *planned(
        2,
        "image",
        ("Faces only", "Faces and text", "Neither faces nor text"),
        "Synthetic fixtures and policy assertions pending",
        start=2,
    ),
    *planned(
        3,
        "pii",
        (
            "Clean control",
            "Pass",
            "Mask",
            "Replace",
            "Redact",
            "Hash",
            "Encrypt",
            "Reversible replacement",
            "Reroute",
            "Block",
        ),
        "Effective policy binding and action assertions pending",
    ),
    *planned(
        4,
        "restoration",
        (
            "Entity types",
            "Multiple entities",
            "Repeated values",
            "Restoration",
            "Replacement-token leakage",
            "Conversation isolation",
        ),
        "Synthetic PII fixtures and restoration assertions pending",
    ),
    *planned(
        5,
        "notices",
        (
            "No PII notice",
            "Changes notice",
            "Block and reroute notices",
            "Disabled preferences",
            "Once-only injection",
            "Accurate counts",
        ),
        "Notice preferences and assertions pending",
    ),
    *planned(
        6,
        "documents",
        (
            "Page limits",
            "Malformed document",
        ),
        "Deployed limits and rejection assertions pending",
        start=5,
    ),
    *planned(
        7,
        "mcp",
        (
            "Tool discovery",
            "Read-only invocation",
            "Result propagation",
            "Denied or unavailable tool",
        ),
        "Approved read-only tool checks pending",
    ),
)

SCENARIOS = tuple(
    sorted(
        (
            *SCENARIOS,
            *(
                Scenario(case.identifier, case.name, "documents", case.blocked)
                for case in DOCUMENTS.values()
            ),
        ),
        key=lambda scenario: tuple(map(int, scenario.identifier.split("."))),
    )
)


def readiness(scenario: Scenario, mode: str) -> str | None:
    if mode not in MODES:
        raise ValueError("Unknown response mode")
    if scenario.blocked:
        return "BLOCKED: " + scenario.blocked
    if scenario.kind == "image" and not IMAGE_PATH.is_file():
        return "FAIL: bundled image fixture is missing"
    return None


def run_case(
    session: Session,
    scenario: Scenario,
    label: str,
    endpoint: str,
    model: str,
    mode: str = "Streaming",
) -> str:
    if label not in {"Local model", "Remote model"}:
        raise ValueError("Unknown model group")
    unavailable = readiness(scenario, mode)
    if unavailable:
        return unavailable
    models = session.json("/api/models")
    if not isinstance(models, dict):
        raise ValueError("Invalid model discovery response")
    if model not in models.get(endpoint, []):
        return "SKIP: configured model unavailable at selected endpoint"
    title = PREFIX + f"{label} - {mode} - {scenario.identifier} - {scenario.name}"
    if scenario.kind == "documents":
        return run_document(
            session, DOCUMENTS[scenario.identifier], endpoint, model, mode, title
        )
    attachment = (
        upload_image(
            session.opener, session.origin, session.headers, endpoint, model, IMAGE_PATH
        )
        if scenario.kind == "image"
        else None
    )
    chat(
        session.opener,
        session.origin,
        session.headers,
        endpoint,
        model,
        attachment=attachment,
        expected_text=IMAGE_EXPECTED_TEXT if scenario.kind == "image" else None,
        save_title=title,
        disable_streaming=mode == "Non-streaming",
    )
    return "PASS"
