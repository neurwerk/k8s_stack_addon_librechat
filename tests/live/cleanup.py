"""Preview and delete only the current user's explicitly named automatic test chats."""

import hashlib
import urllib.error
import urllib.parse
import uuid
from collections.abc import Callable

from session import Session

PREFIX = "NEURWERK AUTOMATIC TESTS - "


def eligible(conversation: dict, user_id: str | None) -> bool:
    return (
        bool(user_id)
        and conversation.get("user") == user_id
        and isinstance(conversation.get("title"), str)
        and conversation["title"].startswith(PREFIX)
    )


def candidates(session: Session) -> list[str]:
    if not session.user_id:
        raise ValueError("Cleanup requires an authenticated LibreChat user")
    found = set()
    for archived in ("false", "true"):
        cursor = None
        seen = set()
        for _ in range(500):
            query = {"limit": "100", "isArchived": archived}
            if cursor:
                query["cursor"] = cursor
            result = session.json("/api/convos?" + urllib.parse.urlencode(query))
            if not isinstance(result, dict) or not isinstance(
                result.get("conversations"), list
            ):
                raise ValueError("Invalid conversation listing")
            for conversation in result["conversations"]:
                if not isinstance(conversation, dict):
                    raise ValueError("Malformed conversation")
                if eligible(conversation, session.user_id):
                    found.add(str(uuid.UUID(conversation["conversationId"])))
            if "nextCursor" not in result:
                raise ValueError("Missing pagination state")
            cursor = result["nextCursor"]
            if cursor is None:
                break
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise ValueError("Invalid or repeated pagination cursor")
            seen.add(cursor)
        else:
            raise ValueError("Conversation listing exceeded limit; nothing deleted")
    return sorted(found)


def cleanup(
    session: Session, *, delete: bool = False, confirm: Callable[[str], str] = input
) -> int:
    selected = candidates(session)
    print(f"Matching automatic test chats (including archived): {len(selected)}")
    for identifier in selected:
        print("  " + identifier)
    if not delete or not selected:
        return 0
    fingerprint = hashlib.sha256("\n".join(selected).encode()).hexdigest()[:8]
    phrase = f"DELETE {len(selected)} {fingerprint}"
    if confirm(f"Type {phrase} to delete these chats: ").strip() != phrase:
        print("Deletion cancelled")
        return 0
    deleted = 0
    for identifier in selected:
        try:
            current = session.json("/api/convos/" + identifier)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            exc.close()
            print("SKIP missing chat: " + identifier)
            continue
        if current.get("conversationId") != identifier or not eligible(
            current, session.user_id
        ):
            print("SKIP changed chat: " + identifier)
            continue
        session.json(
            "/api/convos", method="DELETE", payload={"arg": {"conversationId": identifier}}
        )
        # Verify disappearance, rather than assuming an HTTP success deleted it.
        try:
            session.json("/api/convos/" + identifier)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            exc.close()
        else:
            raise ValueError("Conversation still exists after deletion")
        deleted += 1
        print("Deleted test chat: " + identifier)
    print(f"Deleted {deleted} automatic test chats")
    return deleted
