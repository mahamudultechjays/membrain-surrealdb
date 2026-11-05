"""Ask reflect schemas: one synthesis per layer, with org > team > personal applied."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ReflectRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # Narrows which readable scopes are reflected on. Null or empty reads all.
    scopes: list[str] | None = None

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class ReflectLayerOut(BaseModel):
    layer: str
    scope: str
    # applies: the highest layer whose reflection drew on evidence.
    # overridden: a lower layer that also had evidence. empty: no evidence.
    # failed: this layer's reflection call failed (see error).
    status: Literal["applies", "overridden", "empty", "failed"]
    # The model's synthesis from this scope alone; null when it failed.
    answer: str | None
    # The stored memories it drew on, as Agent Memory quotes them.
    evidence: list[str]
    error: str | None
    trace_id: str | None


class ReflectResponse(BaseModel):
    # One entry per scope, org first, then team, then personal.
    layers: list[ReflectLayerOut]
    # The scope whose reflection applies, or null when no layer had evidence.
    applies: str | None
    scopes: list[str]
