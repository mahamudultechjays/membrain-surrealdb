"""Memory job schemas: trigger consolidate, elaborate or reflect on a scope by hand."""

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class LabRunRequest(BaseModel):
    # A registered scope under the org scope; null means the whole Context,
    # which is allowed only as a consolidation preview.
    scope: str | None = Field(max_length=200)
    action: Literal["consolidate", "elaborate", "reflect"]
    # reflect: the synthesis question.
    query: str | None = Field(default=None, max_length=1000)
    # consolidate / elaborate: preview only, nothing saved.
    dry_run: bool = False
    # reflect: save the insights as new (lower-trust) facts.
    persist: bool = False

    @model_validator(mode="after")
    def _inputs(self) -> Self:
        if self.action == "reflect" and not (self.query or "").strip():
            raise ValueError("reflect needs a query")
        if self.scope is None and not (self.action == "consolidate" and self.dry_run):
            raise ValueError("the whole context only allows a consolidation preview")
        return self


class LabCountsOut(BaseModel):
    entities: int
    attributes: int
    relations: int
    # Attributes and relations by origin: turn, elaboration, consolidation, reflect, ...
    by_source: dict[str, int]


class LabOutcomeOut(BaseModel):
    summary: dict[str, int]
    items: list[str]
    text: str | None
    trace_ids: list[str]


class LabRunResponse(BaseModel):
    action: str
    # Null for the whole Context.
    scope: str | None
    before: LabCountsOut
    after: LabCountsOut
    outcome: LabOutcomeOut
    latency_ms: int
    ran_at: str
