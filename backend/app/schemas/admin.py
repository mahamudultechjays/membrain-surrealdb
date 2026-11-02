"""Admin schemas: users with their scope grants, and registered scopes."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import GrantOut

# Lowercase slash-paths such as org/spreetail/team/ops.
SCOPE_PATH = r"^[a-z0-9][a-z0-9_\-]*(/[a-z0-9][a-z0-9_\-]*)*/?$"


class UserGrants(BaseModel):
    email: str
    name: str
    is_admin: bool
    grants: list[GrantOut]


class UsersResponse(BaseModel):
    users: list[UserGrants]


class GrantRequest(BaseModel):
    scope_path: str = Field(pattern=SCOPE_PATH, max_length=200)
    access: Literal["read", "write"] = "read"
    layer: Literal["org", "team", "personal"] = "team"
    # Used only when the user has no grants yet (we don't know their name).
    name: str | None = Field(default=None, max_length=120)


class ScopesResponse(BaseModel):
    scopes: list[str]


class RegisterScopeRequest(BaseModel):
    path: str = Field(pattern=SCOPE_PATH, max_length=200)
