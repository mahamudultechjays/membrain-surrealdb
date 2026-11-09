"""Ask chat schemas: an answer with [S1]-style markers and the sources they cite."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # From an earlier reply, to continue that conversation. Null starts a new one.
    session_id: str | None = None
    # Narrows which readable scopes the answer may draw on. Null or empty reads all.
    scopes: list[str] | None = None


class ChatCitationOut(BaseModel):
    # The marker as it appears in the reply, without brackets: "S1" for "[S1]".
    marker: str
    id: str
    kind: str
    snippet: str
    score: float
    document_title: str | None
    position_percent: float | None
    # "assistant" when the source is an earlier stored reply rather than a fact.
    role: str | None
    occurred_at: str | None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    # The scopes the answer could draw on.
    scopes: list[str]
    citations: list[ChatCitationOut]
    # Entities, attributes and relations Agent Memory extracted from the message.
    facts_saved: int
    trace_id: str | None
