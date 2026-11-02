"""Scope schemas: the demo users and which of them the app is acting as."""

from typing import Literal

from pydantic import BaseModel, Field


class ScopeOut(BaseModel):
    id: str
    name: str
    type: Literal["user"]
    team: str
    # Layers this user can read, org first.
    reads: list[str]
    # True when the user has their own Agent Memory key in .env, so Agent Memory
    # enforces isolation. False: shared key, kept apart only by the app's lens.
    # Keys themselves are never returned.
    has_own_key: bool


class ScopeListResponse(BaseModel):
    scopes: list[ScopeOut]
    active_scopes: list[str]


class ScopeSwitchRequest(BaseModel):
    scopes: list[str] = Field(min_length=1)


class ScopeSwitchResponse(BaseModel):
    active_scopes: list[str]
    previous_scopes: list[str]
    message: str
