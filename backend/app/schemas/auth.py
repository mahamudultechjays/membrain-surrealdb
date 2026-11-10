"""Auth schemas: who is signed in, and which scopes they hold."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CurrentUser(BaseModel):
    """The identity stored in the session cookie."""

    email: str
    name: str


class GrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope_path: str
    access: Literal["read", "write"]
    layer: Literal["org", "team", "personal"]
    # Whose space this is: the name of the user holding it as their personal
    # scope. None for org and team scopes nobody owns.
    owner: str | None = None


class MeResponse(BaseModel):
    email: str
    name: str
    is_admin: bool
    # Holds the team-admin role: sees Admin > Promotion only.
    is_team_admin: bool = False
    grants: list[GrantOut]


class AuthConfigResponse(BaseModel):
    sso_enabled: bool
    dev_login_enabled: bool


class DevLoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    name: str = Field(min_length=1, max_length=120)
