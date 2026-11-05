"""Port for users' onboarding answers and the VCT nodes they confirmed."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

ConfirmedBy = Literal["user", "admin"]


@dataclass(frozen=True, slots=True)
class MappedNode:
    node_id: str
    # 1 = first choice; the order the nodes were confirmed in.
    rank: int
    is_primary: bool
    confirmed_by: ConfirmedBy


@dataclass(frozen=True, slots=True)
class OnboardingRecord:
    email: str
    primary_work: str
    # Rapport only, as in membrain: shown back, never used for mapping.
    role: str | None = None
    team: str | None = None
    onboarded_at: str = ""
    nodes: list[MappedNode] = field(default_factory=list)


class OnboardingRepository(Protocol):
    async def get(self, email: str) -> OnboardingRecord | None:
        """This user's onboarding, or None before they finish it."""
        ...

    async def save(self, record: OnboardingRecord) -> None:
        """Store the answers and replace the user's mapped nodes."""
        ...
