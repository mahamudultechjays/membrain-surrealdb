"""Findings schemas: the static tests, capabilities and gaps catalogues."""

from typing import Literal

from pydantic import BaseModel


class _Catalogue(BaseModel):
    # Where the data came from, and when it was checked.
    source: str
    checked: str


class TestFinding(BaseModel):
    id: str
    # Gap row the claim belongs to, e.g. "F1".
    requirement: str
    name: str
    # pass = claim confirmed hands-on, fail = contradicted, open = anything else.
    status: Literal["pass", "fail", "open"]
    how: str
    native_result: str
    # Not measured yet: the POC has no MemBrain-side run.
    membrain_result: str | None
    # Claim type: behaviour, absence, docs, time, two users or judgement.
    mark: str
    docs_check: str
    evidence: str


class TestsResponse(_Catalogue):
    tests: list[TestFinding]


class CapabilityFinding(BaseModel):
    area: str
    name: str
    call: str | None
    # native, workaround, partial, check or missing.
    mark: str
    screen: str | None
    evidence: str


class CapabilitiesResponse(_Catalogue):
    capabilities: list[CapabilityFinding]


class GapFinding(BaseModel):
    id: str
    name: str
    # The gap analysis classification, e.g. "True gap" or "Roadmap".
    status: str | None
    priority: str | None
    owner: str | None
    need: str | None
    agent_memory_today: str | None
    ask_surrealdb: str | None
    # Not written up yet for the POC.
    membrain_workaround: str | None
    # Hands-on verdict counts for the row's claims, e.g. "3 Confirmed".
    validation: str | None


class GapsResponse(_Catalogue):
    gaps: list[GapFinding]
