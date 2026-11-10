"""By layer mode (option C): every scope listed, disagreements flagged, nothing chosen."""

from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.user_scopes import ScopeGrant
from app.services import ask_flow
from app.services.ask_flow import Answer
from app.services.ask_modes.points import find_conflicts
from app.services.ask_modes.types import ModeAnswer


async def run(
    recall: MemoryRecall, grants: list[ScopeGrant], *, q: str, min_score: float = 0.0
) -> ModeAnswer:
    return apply(await ask_flow.ask(recall, grants, q=q), min_score=min_score)


def apply(answer: Answer, *, min_score: float = 0.0) -> ModeAnswer:
    """Flag disagreements in an answer already recalled."""
    conflicts, _ = find_conflicts(answer, min_score=min_score)
    return ModeAnswer("by_layer", answer, conflicts=conflicts, verdicts={})
