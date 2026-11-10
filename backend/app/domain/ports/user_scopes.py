"""Port for the user -> scope grants our backend owns (the governance layer)."""

from dataclasses import dataclass
from typing import Literal, Protocol

Access = Literal["read", "write"]
LayerName = Literal["org", "team", "personal"]
# Our own roles, not Agent Memory grants (spec: team admin is a role).
ROLE_TEAM_ADMIN = "team_admin"


@dataclass(frozen=True, slots=True)
class ScopeGrant:
    """One Agent Memory scope a user may read, or read and write."""

    email: str
    name: str
    scope_path: str
    access: Access
    layer: LayerName


class UserScopeRepository(Protocol):
    async def grants_for(self, email: str) -> list[ScopeGrant]:
        """Every grant this user holds; empty for a user never seen before."""
        ...

    async def all_grants(self) -> list[ScopeGrant]:
        """Every grant of every user, ordered by email then scope."""
        ...

    async def put(self, grant: ScopeGrant) -> None:
        """Add the grant, or replace the access and layer of an existing one."""
        ...

    async def remove(self, email: str, scope_path: str) -> bool:
        """Drop one grant. False when the user did not hold it."""
        ...

    async def roles_for(self, email: str) -> set[str]: ...

    async def set_role(self, email: str, role: str, on: bool) -> None: ...

    async def emails_with_role(self, role: str) -> list[str]: ...
