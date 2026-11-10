"""Team admin decisions on the review list (spec sections 4 and 7).

Approve writes the team rule; close writes a closing value over it (facts take
no end date and forget is never granted, checks S4 and S6).

Every decision, and the job's drop step, runs under one lock per store (the
backend is one uvicorn process), so the state check, the Agent Memory write and
the status change happen together: two admins deciding at once get one success
and one 409, and a run can't drop an item while it is being approved.
"""

import asyncio
import weakref
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.domain.errors import PromotionStateError
from app.domain.ports.promotion import FactGroup, PromotionRepository, ReviewItem
from app.domain.ports.team_rules import TeamRuleWriter

_LOCKS: "weakref.WeakKeyDictionary[object, asyncio.Lock]" = weakref.WeakKeyDictionary()


def lock_for(repo: PromotionRepository) -> asyncio.Lock:
    """The one lock for decisions on this store."""
    lock = _LOCKS.get(repo)
    if lock is None:
        lock = _LOCKS[repo] = asyncio.Lock()
    return lock


@dataclass(frozen=True, slots=True)
class RuleEdit:
    label: str
    entity_type: str
    entity: str
    key: str
    value: str


def closing_text(by: str, today: date) -> str:
    return f"no longer a team rule (closed by {by} on {today.day} {today:%b})"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


async def _item(repo: PromotionRepository, item_id: int) -> ReviewItem:
    found = next((i for i in await repo.review_items() if i.id == item_id), None)
    if found is None:
        raise PromotionStateError(item_id, None)
    return found


async def _group(repo: PromotionRepository, group_id: int) -> FactGroup:
    found = next((g for g in await repo.groups() if g.id == group_id), None)
    if found is None:
        raise PromotionStateError(group_id, None)
    return found


async def approve(
    repo: PromotionRepository,
    writer: TeamRuleWriter,
    item_id: int,
    *,
    by: str,
    edit: RuleEdit | None,
) -> ReviewItem:
    """Write the rule, then mark the candidate active. Refused while the topic
    already has an active rule: close that one first, so one key never holds two
    rules."""
    async with lock_for(repo):
        item = await _item(repo, item_id)
        if item.kind != "candidate" or item.status != "open":
            raise PromotionStateError(item_id, item.status)
        items = await repo.review_items()
        if any(
            i.kind == "candidate" and i.status == "active" and i.group_id == item.group_id
            for i in items
        ):
            raise PromotionStateError(item_id, "blocked by an active rule in this topic")
        group = await _group(repo, item.group_id)
        etype, entity, key = group.rule_entity_type, group.rule_entity, group.rule_key
        value = item.value
        if edit is not None:
            etype, entity, key, value = edit.entity_type, edit.entity, edit.key, edit.value
        ref = await writer.write(
            entity_type=etype,
            entity=entity,
            key=key,
            value=value,
            labels=["kind=rule", f"approved_by={by}"],
        )
        if edit is not None:
            await repo.update_rule(
                item.group_id, label=edit.label, entity_type=etype, entity=entity, key=key
            )
        return await repo.set_status(
            item_id,
            "active",
            expect={"open"},
            by=by,
            at=_now(),
            memory_ref=ref,
            target=(etype, entity, key),
        )


async def reject(
    repo: PromotionRepository, item_id: int, *, by: str, score_now: float | None = None
) -> ReviewItem:
    """`score_now` is kept, so the value comes back only if its score climbs above it."""
    async with lock_for(repo):
        item = await _item(repo, item_id)
        if item.kind != "candidate":
            raise PromotionStateError(item_id, item.status)
        return await repo.set_status(
            item_id, "rejected", expect={"open"}, by=by, at=_now(), score=score_now
        )


async def keep(
    repo: PromotionRepository, item_id: int, *, by: str, score_now: float | None = None
) -> ReviewItem:
    """`score_now` is kept, so a new flag opens only above it."""
    async with lock_for(repo):
        item = await _item(repo, item_id)
        if item.kind != "flag":
            raise PromotionStateError(item_id, item.status)
        return await repo.set_status(
            item_id, "kept", expect={"open"}, by=by, at=_now(), score=score_now
        )


async def close(
    repo: PromotionRepository,
    writer: TeamRuleWriter,
    item_id: int,
    *,
    by: str,
    today: date,
) -> ReviewItem:
    """Close an active rule, or a flag together with the rule it questions.
    The closing value goes to the entity and key the rule was written under."""
    async with lock_for(repo):
        item = await _item(repo, item_id)
        if item.kind == "flag":
            if item.status not in ("open", "kept") or item.rule_id is None:
                raise PromotionStateError(item_id, item.status)
            rule = await _item(repo, item.rule_id)
        else:
            rule = item
        if rule.status != "active" or rule.id is None:
            raise PromotionStateError(rule.id or item_id, rule.status)
        if rule.rule_entity and rule.rule_key:
            etype, entity, key = rule.rule_entity_type or "", rule.rule_entity, rule.rule_key
        else:
            group = await _group(repo, rule.group_id)
            etype, entity, key = group.rule_entity_type, group.rule_entity, group.rule_key
        ref = await writer.write(
            entity_type=etype,
            entity=entity,
            key=key,
            value=closing_text(by, today),
            labels=["kind=closed", f"closed_by={by}"],
        )
        at = _now()
        closed_rule = await repo.set_status(
            rule.id, "closed", expect={"active"}, by=by, at=at, closed_ref=ref
        )
        # Any open or kept flag on this rule closes with it.
        for flag in await repo.review_items():
            if flag.kind == "flag" and flag.rule_id == rule.id and flag.status in ("open", "kept"):
                done = await repo.set_status(
                    flag.id or 0, "closed", expect={"open", "kept"}, by=by, at=at
                )
                if flag.id == item_id:
                    return done
        return closed_rule
