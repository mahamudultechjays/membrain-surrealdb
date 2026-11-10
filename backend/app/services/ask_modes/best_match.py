"""Best match mode (option B): when scopes disagree, the closest match wins.

If another scope's value scores within the tie margin of the top one, the
broader layer wins (org, then team, then personal). Losing values stay in the
answer, marked set aside. This order is applied here, on top of Agent Memory's
ranking; Agent Memory itself has no scope precedence.
"""

from dataclasses import replace

from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.user_scopes import ScopeGrant
from app.services import ask_flow
from app.services.ask_flow import LAYER_ORDER, Answer
from app.services.ask_modes.points import (
    LAYER_LABELS,
    Conflict,
    FactVerdict,
    Located,
    find_conflicts,
)
from app.services.ask_modes.types import ModeAnswer


async def run(
    recall: MemoryRecall,
    grants: list[ScopeGrant],
    *,
    q: str,
    tie_margin: float,
    min_score: float = 0.0,
) -> ModeAnswer:
    answer = await ask_flow.ask(recall, grants, q=q)
    return apply(answer, tie_margin=tie_margin, min_score=min_score)


def apply(answer: Answer, *, tie_margin: float, min_score: float = 0.0) -> ModeAnswer:
    """Resolve disagreements in an answer already recalled."""
    conflicts, members = find_conflicts(answer, min_score=min_score)
    resolved: list[Conflict] = []
    verdicts: dict[str, FactVerdict] = {}
    for conflict in conflicts:
        decided, conflict_verdicts = resolve(conflict, members[conflict.id], tie_margin)
        resolved.append(decided)
        verdicts.update(conflict_verdicts)
    return ModeAnswer("best_match", answer, conflicts=resolved, verdicts=verdicts)


def resolve(
    conflict: Conflict, members: list[Located], tie_margin: float
) -> tuple[Conflict, dict[str, FactVerdict]]:
    """Pick the winning hit of one conflict and give every hit a verdict."""
    top = max(members, key=lambda m: m.hit.score)
    close = [m for m in members if top.hit.score - m.hit.score <= tie_margin + 1e-9]
    winner = min(close, key=lambda m: (LAYER_ORDER[m.layer], -m.hit.score, m.area))
    # A tie only matters when a close rival holds a different value in another scope.
    rivals = [m for m in close if m.norm_value != winner.norm_value and m.area != winner.area]
    if winner is not top or rivals:
        reason = (
            f"Scores within {tie_margin:.2f}, so the broader "
            f"{LAYER_LABELS[winner.layer]} layer wins"
        )
    else:
        runner_up = max(
            (m.hit.score for m in members if m.norm_value != winner.norm_value), default=0.0
        )
        reason = f"Closest match to the question ({winner.hit.score:.2f} vs {runner_up:.2f})"

    label = LAYER_LABELS[winner.layer]
    verdicts: dict[str, FactVerdict] = {}
    for m in members:
        if m.hit.id == winner.hit.id:
            verdicts[m.hit.id] = FactVerdict("used", reason)
        elif m.norm_value == winner.norm_value:
            verdicts[m.hit.id] = FactVerdict("used", "Agrees with the chosen value")
        else:
            verdicts[m.hit.id] = FactVerdict(
                "set_aside", f"Disagrees with the chosen {label} value: {winner.parsed.value}"
            )
    return replace(conflict, winner_hit_id=winner.hit.id, reason=reason), verdicts
