"""Schemas for the VCT tagger admin endpoints."""

from pydantic import BaseModel, Field


class TaggerRunOut(BaseModel):
    started_at: str
    finished_at: str | None
    scopes: list[str]
    listed: int = Field(description="Facts seen in the tagged scopes.")
    new: int = Field(description="Facts not tagged before this run.")
    tagged: int
    not_business: int = Field(default=0, description="Tagged facts a decoy marked not business.")
    carried: int = Field(description="Tags a person set, carried to a fact's new version.")
    failed: int
    capped: bool = Field(description="True when the run hit its limit; the rest go next run.")
    error: str | None


class ConfusionOut(BaseModel):
    old: str
    new: str | None
    times: int


class TaggerStats(BaseModel):
    days: int
    edits: int
    corrections: int
    correction_rate: float | None = Field(
        description="Corrections per tag a person reviewed; None before any review."
    )
    confusions: list[ConfusionOut]


class TaggerStatus(BaseModel):
    enabled: bool
    version: str
    scopes: list[str]
    interval_hours: float
    running: bool
    next_run_at: str | None
    current: TaggerRunOut | None
    last: TaggerRunOut | None
    tagged_facts: int = 0
    not_business: int = 0
    stats: TaggerStats | None = None
