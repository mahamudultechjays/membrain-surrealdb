"""Chat: which scopes a chat turn may read and write, and whose sessions are whose.

Reads cover the user's granted scopes (optionally narrowed), ordered org ->
team -> personal like Ask. The user's message is stored in their personal
scope, since that is the only scope a user always writes.

Every chat key is minted from the one admin key, so they all act as the same
Agent Memory principal and its session ownership check can't tell users apart.
`ChatSessions` does that here: a session id is only accepted from the user it
was issued to.
"""

from app.domain.errors import ScopeNotGrantedError
from app.domain.ports.memory_chat import ChatAccess
from app.domain.ports.user_scopes import ScopeGrant
from app.services.ask_flow import plan_reads


def plan_access(
    owner: str, readable: list[ScopeGrant], *, wanted: list[str] | None = None
) -> ChatAccess:
    """Raises ScopeNotGrantedError for a wanted scope the user can't read, or
    when the user has no personal scope to store the message in."""
    reads = [read.area for read in plan_reads(readable)]
    if wanted:
        wanted_set = {w.strip("/") for w in wanted}
        missing = wanted_set - set(reads)
        if missing:
            raise ScopeNotGrantedError(", ".join(sorted(missing)))
        reads = [area for area in reads if area in wanted_set]
    personal = next(
        (g.scope_path for g in readable if g.layer == "personal" and g.access == "write"), None
    )
    if personal is None:
        raise ScopeNotGrantedError("no personal scope to store the chat in")
    return ChatAccess(owner=owner, read=tuple(reads), write=personal)


class ChatSessions:
    """Session id -> the user it belongs to. In memory: a restart ends every chat."""

    def __init__(self) -> None:
        self._owners: dict[str, str] = {}

    def belongs_to(self, session_id: str, owner: str) -> bool:
        return self._owners.get(session_id) == owner

    def remember(self, session_id: str, owner: str) -> None:
        self._owners.setdefault(session_id, owner)
