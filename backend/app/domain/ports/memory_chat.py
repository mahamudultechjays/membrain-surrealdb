"""Port for chatting with memory: an answer with citations, read only from granted scopes."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ChatAccess:
    """What one chat turn may touch.

    `owner` is who the turn is for (an email); each owner has one live
    credential, replaced when their access changes.
    """

    owner: str
    # Scope paths the answer may draw on. Exact paths, not their children.
    read: tuple[str, ...]
    # The one scope the user's message is stored in.
    write: str


@dataclass(frozen=True, slots=True)
class ChatCitation:
    # The inline marker in the reply, e.g. "S1" for "[S1]".
    marker: str
    id: str
    # attribute, entity, relation, turn, chunk, section, ...
    kind: str
    snippet: str
    score: float
    document_title: str | None = None
    position_percent: float | None = None
    # "assistant" when the citation is an earlier stored reply.
    role: str | None = None
    occurred_at: str | None = None


@dataclass(frozen=True, slots=True)
class ChatReply:
    reply: str
    session_id: str
    trace_id: str | None = None
    citations: list[ChatCitation] = field(default_factory=list)
    # Entities, attributes and relations extracted from the user's message.
    facts_saved: int = 0


@dataclass(frozen=True, slots=True)
class Reflection:
    """A synthesis across the readable scopes, with what it drew on."""

    text: str
    # The stored memories the answer was built from, as Agent Memory quotes them.
    evidence: list[str] = field(default_factory=list)
    trace_id: str | None = None


class MemoryReflect(Protocol):
    async def reflect(self, question: str, *, access: ChatAccess) -> Reflection:
        """Synthesise an answer from `access.read` only. Never saves anything."""
        ...


class MemoryChat(Protocol):
    async def chat(self, message: str, *, access: ChatAccess, session_id: str | None) -> ChatReply:
        """Answer `message` from `access.read` only, storing it in `access.write`."""
        ...
