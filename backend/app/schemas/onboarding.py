"""Onboarding schemas: the VCT map, node suggestions, and a user's confirmed nodes."""

from typing import Literal

from pydantic import BaseModel, Field


class VctNodeOut(BaseModel):
    id: str
    name: str
    description: str
    domain_id: str
    section_id: str = ""


class DomainRef(BaseModel):
    id: str
    name: str


class VctDomainOut(DomainRef):
    nodes: list[VctNodeOut]


class VctGoalOut(BaseModel):
    id: str
    name: str
    description: str
    # The goal's share of EBITDA.
    weight: float


class VctSectionOut(BaseModel):
    id: str
    label: str
    ebitda_weight: float
    goals: list[VctGoalOut]


class VctMapResponse(BaseModel):
    topology_version: str
    domains: list[VctDomainOut]
    # The value-chain sections in order, each with its goals.
    sections: list[VctSectionOut] = Field(default_factory=list)


class OnboardingPreviewRequest(BaseModel):
    primary_work: str = Field(min_length=3, max_length=2000)


class ClauseOut(BaseModel):
    clause: str
    # Best first. Recall gives rank, not confidence, so there is no score.
    candidates: list[VctNodeOut]


class OnboardingPreviewResponse(BaseModel):
    clauses: list[ClauseOut]
    # The first candidate of each clause, once each: pre-tick these.
    suggested: list[str]
    domains: list[DomainRef]


class OnboardingConfirmRequest(BaseModel):
    primary_work: str = Field(min_length=3, max_length=2000)
    role: str | None = Field(default=None, max_length=120)
    team: str | None = Field(default=None, max_length=120)
    node_ids: list[str] = Field(max_length=8)
    primary_node_id: str | None = None


class AdminVctRequest(BaseModel):
    node_ids: list[str] = Field(max_length=8)
    primary_node_id: str | None = None


class MappedNodeOut(VctNodeOut):
    rank: int
    is_primary: bool
    confirmed_by: Literal["user", "admin"]


class OnboardingStatus(BaseModel):
    email: str
    onboarded: bool
    primary_work: str | None = None
    role: str | None = None
    team: str | None = None
    onboarded_at: str | None = None
    nodes: list[MappedNodeOut] = []
    # Derived from the nodes through the metro map, primary node's domain first.
    domains: list[DomainRef] = []


class SeedResponse(BaseModel):
    scope: str
    seeded: int
    goals_scope: str | None = None
    goals_seeded: int = 0
