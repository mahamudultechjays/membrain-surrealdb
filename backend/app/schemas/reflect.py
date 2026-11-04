"""Ask reflect schemas: a synthesis across the user's scopes, with its evidence."""

from pydantic import BaseModel, Field, field_validator


class ReflectRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # Narrows which readable scopes the answer may draw on. Null or empty reads all.
    scopes: list[str] | None = None

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class ReflectResponse(BaseModel):
    answer: str
    # The stored memories the answer drew on, as Agent Memory quotes them.
    evidence: list[str]
    # The scopes the answer could draw on.
    scopes: list[str]
    trace_id: str | None
