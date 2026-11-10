"""Admin > Promotion: the review list and the job's state."""

from typing import Literal

from pydantic import BaseModel


class RunOut(BaseModel):
    started_at: str
    finished_at: str | None
    listed: int
    new: int
    replaced: int
    grouped: int
    new_topics: int
    left: int
    opened: int
    dropped: int
    error: str | None


class ValueChip(BaseModel):
    value: str
    team_score: float


class SaidOut(BaseModel):
    text: str
    # chat (Claude plugin or Chat) or app (Capture).
    source: str
    said_at: str


class EvidenceOut(BaseModel):
    user: str
    weights: list[float]
    # What they hold: the value, or "not <value>".
    value: str
    said: list[SaidOut]


class GroupOut(BaseModel):
    id: int
    label: str
    values: list[ValueChip]
    people: int


class ReviewItemOut(BaseModel):
    id: int
    kind: Literal["candidate", "flag"]
    status: Literal["open", "active", "closed", "rejected", "dropped", "kept"]
    group_id: int
    label: str
    entity_type: str
    entity: str
    key: str
    value: str
    score_when_listed: float
    # Now, from the latest statements.
    team_score: float
    for_score: float
    against_score: float
    holders: list[str]
    decided_by: str | None
    decided_at: str | None
    rule_id: int | None
    created_at: str | None
    # Every value said in this topic, highest score first.
    values: list[ValueChip] = []
    # People with any counted statement in the topic.
    people: int = 0
    for_rows: list[EvidenceOut] = []
    against_rows: list[EvidenceOut] = []


class PromotionStatus(BaseModel):
    enabled: bool
    running: bool
    next_run_at: str | None
    every_minutes: float
    team_scope: str
    model_configured: bool
    thresholds: dict[str, float]
    last_run: RunOut | None
    items: list[ReviewItemOut]
    groups: list[GroupOut] = []


class RuleEditIn(BaseModel):
    label: str
    entity_type: str
    entity: str
    key: str
    value: str


class RunStarted(BaseModel):
    started: bool
