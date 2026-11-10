"""The review list from scores (spec sections 4 and 6).

Candidates: a value at or above candidate_at opens one, unless it already has
an open or active candidate. Open candidates below the threshold are dropped;
a dropped value may be listed again later. A rejected value is listed again
only when its score climbs above the score it had when it was rejected.

Flags: an active rule whose against-score reaches flag_at gets one open flag.
After a flag is kept, a new one opens only above the kept flag's score.
"""

from contextlib import suppress
from dataclasses import dataclass, field

from app.domain.errors import PromotionStateError
from app.domain.ports.promotion import PromotionRepository, ReviewItem, Statement
from app.domain.promotion import ScoredStatement, ValueScore, same_value
from app.services.promotion.decisions import lock_for


@dataclass
class ReviewChanges:
    open: list[ReviewItem] = field(default_factory=list)
    drop: list[int] = field(default_factory=list)


def to_scored(rows: list[Statement]) -> list[ScoredStatement]:
    return [
        ScoredStatement(
            r.user, r.group_id, r.norm_value or r.value, r.stance, r.said_at, str(r.id or "")
        )
        for r in rows
        if r.group_id is not None and r.stance is not None
    ]


def _same(item: ReviewItem, group_id: int, value: str) -> bool:
    return item.group_id == group_id and same_value(item.value, value)


def plan_review(
    scores: list[ValueScore],
    items: list[ReviewItem],
    *,
    candidate_at: float,
    flag_at: float,
) -> ReviewChanges:
    changes = ReviewChanges()
    candidates = [i for i in items if i.kind == "candidate"]
    flags = [i for i in items if i.kind == "flag"]

    for v in scores:
        mine = [i for i in candidates if _same(i, v.group_id, v.value)]
        live = [i for i in mine if i.status in ("open", "active")]
        for i in live:
            if i.status == "open" and v.team_score < candidate_at and i.id is not None:
                changes.drop.append(i.id)
        if live or v.team_score < candidate_at:
            continue
        rejected = [i for i in mine if i.status == "rejected"]
        if rejected and v.team_score <= max(i.score_when_listed for i in rejected):
            continue
        changes.open.append(ReviewItem("candidate", v.group_id, v.value, v.team_score, "open"))

    # Open candidates whose value no longer has any statements are dropped too.
    scored = {(v.group_id, v.value) for v in scores}
    for i in candidates:
        gone = not any(_same(i, g, val) for g, val in scored)
        if i.status == "open" and i.id is not None and i.id not in changes.drop and gone:
            changes.drop.append(i.id)

    for rule in (i for i in candidates if i.status == "active" and i.id is not None):
        against = next((v.against_score for v in scores if _same(rule, v.group_id, v.value)), 0.0)
        if against < flag_at:
            continue
        mine = [f for f in flags if f.rule_id == rule.id]
        if any(f.status == "open" for f in mine):
            continue
        kept = [f for f in mine if f.status == "kept"]
        if kept and against <= max(f.score_when_listed for f in kept):
            continue
        changes.open.append(
            ReviewItem("flag", rule.group_id, rule.value, against, "open", rule_id=rule.id)
        )
    return changes


async def apply_review(repo: PromotionRepository, changes: ReviewChanges) -> None:
    async with lock_for(repo):
        await _apply(repo, changes)


async def _apply(repo: PromotionRepository, changes: ReviewChanges) -> None:
    items = {i.id: i for i in await repo.review_items()}
    for item in changes.open:
        await repo.add_review_item(item)
    for item_id in changes.drop:
        if (current := items.get(item_id)) is None or current.status != "open":
            continue
        # An admin may have decided it during the run; their decision stands.
        with suppress(PromotionStateError):
            await repo.set_status(item_id, "dropped", expect={"open"})
