"""Demo scope directory: who the users are and which memory layers each can read.

Grants are hardcoded for the demo. Priya and Deena share the ops team, Arun is
on eng, so Arun can never read Priya's personal or team layer.
"""

from dataclasses import dataclass
from typing import Literal

from app.domain.errors import UnknownScopeError

LayerName = Literal["org", "team", "personal"]

ORG_PATH = "org"


@dataclass(frozen=True, slots=True)
class DemoUser:
    scope: str
    name: str
    team: str


@dataclass(frozen=True, slots=True)
class Layer:
    name: LayerName
    path: str


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser(scope="org/user/u-0001", name="Priya", team="org/team/ops"),
    DemoUser(scope="org/user/u-0002", name="Arun", team="org/team/eng"),
    DemoUser(scope="org/user/u-0003", name="Deena", team="org/team/ops"),
)


class ScopeDirectory:
    def __init__(self, users: tuple[DemoUser, ...] = DEMO_USERS) -> None:
        self._users = {user.scope: user for user in users}

    def users(self) -> list[DemoUser]:
        return list(self._users.values())

    def get(self, scope: str) -> DemoUser:
        try:
            return self._users[scope]
        except KeyError:
            raise UnknownScopeError(scope) from None

    def read_layers(self, scope: str) -> list[Layer]:
        """Org, then the user's team, then the user's own scope."""
        user = self.get(scope)
        return [
            Layer("org", ORG_PATH),
            Layer("team", user.team),
            Layer("personal", user.scope),
        ]

    def describe(self, scopes: list[str]) -> str:
        """'Priya + Deena' for a list of known scopes."""
        return " + ".join(self.get(scope).name for scope in scopes)


class ActiveScopes:
    """Which users the demo is currently acting as. Process-wide, not per browser."""

    def __init__(self, initial: list[str]) -> None:
        self._scopes = list(initial)

    def get(self) -> list[str]:
        return list(self._scopes)

    def switch(self, scopes: list[str]) -> list[str]:
        """Set the active scopes and return the previous ones."""
        previous, self._scopes = self._scopes, list(dict.fromkeys(scopes))
        return previous
