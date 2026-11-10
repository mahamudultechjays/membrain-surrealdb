"""Grouping: match new statements to topics with a small model (spec 5.1).

1. Same subject first: topics whose subject or alias equals the statement's
   cleaned subject; the model may only pick one of them or say none.
2. Full list: anything unmatched, or with a generic subject, goes with every
   topic; only here may the model create a new topic.
3. A full-list match to a topic under another subject saves that subject as an
   alias, so next time it matches in step 1.
Statements without a valid answer stay unprocessed and are retried next run.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace

from app.domain.errors import GroupingModelError
from app.domain.ports.grouping_model import GroupingModel, StatementIn, TopicIn, TopicMatch
from app.domain.ports.promotion import FactGroup, PromotionRepository, Statement
from app.domain.promotion import Stance, clean_subject, norm


@dataclass
class GroupingStats:
    sent: int = 0
    first_pass: int = 0
    full_list: int = 0
    new_topics: int = 0
    aliases: int = 0
    left: int = 0
    error: str | None = None


def _input(s: Statement) -> StatementIn:
    return StatementIn(str(s.id), clean_subject(s.entity), s.text, s.key, s.value)


async def _topics(repo: PromotionRepository, groups: Iterable[FactGroup]) -> list[TopicIn]:
    values: dict[int, list[str]] = {}
    for row in await repo.counted():
        if row.group_id is not None and row.norm_value:
            seen = values.setdefault(row.group_id, [])
            if row.norm_value not in seen:
                seen.append(row.norm_value)
    return [TopicIn(g.id, g.label, tuple(values.get(g.id, []))) for g in groups if g.id]


async def group_new(
    repo: PromotionRepository,
    model: GroupingModel,
    *,
    batch_size: int,
    generic_subjects: frozenset[str],
    now: str,
    max_batches: int = 20,
) -> GroupingStats:
    stats = GroupingStats()
    todo = await repo.unprocessed(batch_size * max_batches)
    for start in range(0, len(todo), batch_size):
        try:
            await _batch(
                repo, model, todo[start : start + batch_size], generic_subjects, now, stats
            )
        except GroupingModelError as exc:
            stats.error = str(exc) or type(exc).__name__
            stats.left += len(todo) - start
            break
    return stats


async def _batch(
    repo: PromotionRepository,
    model: GroupingModel,
    batch: list[Statement],
    generic: frozenset[str],
    now: str,
    stats: GroupingStats,
) -> None:
    by_ref = {str(s.id): s for s in batch}
    stats.sent += len(batch)
    done: list[tuple[int, int, str, Stance]] = []
    matched: set[str] = set()

    # 1. Same subject first.
    specific = [s for s in batch if clean_subject(s.entity) not in generic]
    subjects = {clean_subject(s.entity) for s in specific}
    near = await repo.groups_for_subjects(subjects) if subjects else []
    if near:
        allowed = {g.id for g in near}
        for m in await model.match(
            [_input(s) for s in specific], await _topics(repo, near), allow_new=False
        ):
            s = by_ref.get(m.ref)
            if (
                s
                and s.id
                and m.topic_id is not None
                and m.topic_id in allowed
                and m.ref not in matched
            ):
                matched.add(m.ref)
                done.append((s.id, m.topic_id, m.value, m.stance))
                stats.first_pass += 1

    # 2. Full list for the rest.
    rest = [s for s in batch if str(s.id) not in matched]
    if rest:
        groups = await repo.groups()
        by_id = {g.id: g for g in groups}
        created: dict[str, int] = {}
        answers = await model.match(
            [_input(s) for s in rest], await _topics(repo, groups), allow_new=True
        )
        for m in answers:
            s = by_ref.get(m.ref)
            if not s or not s.id or m.ref in matched:
                continue
            gid = await _target(repo, m, s, by_id, created, stats)
            if gid is None:
                continue
            matched.add(m.ref)
            done.append((s.id, gid, m.value, m.stance))
            stats.full_list += 1
            subject = clean_subject(s.entity)
            group = by_id.get(gid)
            if (
                group
                and subject
                and subject not in generic
                and subject != group.subject
                and subject not in group.aliases
            ):
                await repo.add_alias(gid, subject)
                by_id[gid] = replace(group, aliases=(*group.aliases, subject))
                stats.aliases += 1

    await repo.set_grouping(done, now)
    stats.left += len(batch) - len(done)


async def _target(
    repo: PromotionRepository,
    m: TopicMatch,
    s: Statement,
    by_id: dict[int | None, FactGroup],
    created: dict[str, int],
    stats: GroupingStats,
) -> int | None:
    """The group a full-list answer points to, creating a new topic once per label."""
    if m.topic_id is not None:
        return m.topic_id if m.topic_id in by_id else None
    if m.new_topic is None:
        return None
    # Same label, or same entity and key, in one run: one topic. The model names
    # new topics one statement at a time and can word the same fact differently.
    by_label = f"label:{norm(m.new_topic.label)}"
    by_key = f"key:{clean_subject(m.new_topic.entity)}|{norm(m.new_topic.key)}"
    known = created.get(by_label) or (created.get(by_key) if m.new_topic.key else None)
    if known is not None:
        created[by_label] = known
        return known
    key = by_label
    if key not in created:
        group = FactGroup(
            label=m.new_topic.label,
            subject=clean_subject(s.entity),
            rule_entity_type=m.new_topic.entity_type,
            rule_entity=m.new_topic.entity,
            rule_key=m.new_topic.key,
        )
        gid = await repo.add_group(group)
        created[key] = gid
        if m.new_topic.key:
            created[by_key] = gid
        by_id[gid] = replace(group, id=gid)
        stats.new_topics += 1
    return created[key]
