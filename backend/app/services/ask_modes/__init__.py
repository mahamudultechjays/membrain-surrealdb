"""Ask modes: three separate ways to answer from org, team and personal scopes.

- default: every readable scope, listed by layer. Nothing is compared.
- by_layer (option C): the same, with disagreements across scopes flagged.
- best_match (option B): disagreements resolved by match score, with near-ties
  going to the broader layer.

Each mode is its own module so they can be compared side by side. All three
read the scopes the same way (ask_flow.ask: one recall per scope), then apply
their rules to that answer, so compare() can share one recall between modes.
"""

from typing import Literal

from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.user_scopes import ScopeGrant
from app.services import ask_flow
from app.services.ask_modes import best_match, by_layer, default
from app.services.ask_modes.points import Conflict, ConflictValue, FactVerdict
from app.services.ask_modes.types import ASK_MODES, AskMode, ModeAnswer

__all__ = [
    "ASK_MODES",
    "AskMode",
    "Conflict",
    "ConflictValue",
    "FactVerdict",
    "ModeAnswer",
    "compare",
    "resolve_mode",
    "run",
]


async def run(
    mode: AskMode,
    recall: MemoryRecall,
    grants: list[ScopeGrant],
    *,
    q: str,
    tie_margin: float,
    min_score: float = 0.0,
) -> ModeAnswer:
    """`min_score`: a conflict is flagged only when one of its values scores at
    least this much for the question (see points.find_conflicts)."""
    if mode == "best_match":
        return await best_match.run(recall, grants, q=q, tie_margin=tie_margin, min_score=min_score)
    if mode == "by_layer":
        return await by_layer.run(recall, grants, q=q, min_score=min_score)
    return await default.run(recall, grants, q=q)


async def compare(
    recall: MemoryRecall,
    grants: list[ScopeGrant],
    *,
    q: str,
    tie_margin: float,
    min_score: float = 0.0,
) -> tuple[ModeAnswer, ModeAnswer]:
    """Best match and By layer for one question, from a single recall.

    Asking each mode separately would recall every scope twice for the same
    hits; the modes differ only in what they do with them.
    """
    answer = await ask_flow.ask(recall, grants, q=q)
    return (
        best_match.apply(answer, tie_margin=tie_margin, min_score=min_score),
        by_layer.apply(answer, min_score=min_score),
    )


def resolve_mode(
    requested: AskMode | None, configured: AskMode
) -> tuple[AskMode, Literal["request", "config"]]:
    """The mode that answers, and where it came from.

    The one place a traffic split across modes would plug in later.
    """
    if requested is not None:
        return requested, "request"
    return configured, "config"
