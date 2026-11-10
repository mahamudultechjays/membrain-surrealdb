"""Admin > Promotion: the review list, Run now, and the team admin's decisions.

Org admins and team admins only. Approve is the one path that writes to the
team scope; close writes a closing value over a rule.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import (
    PromotionAdminDep,
    PromotionRepositoryDep,
    PromotionServiceDep,
    TeamRuleWriterDep,
)
from app.core.config import settings
from app.domain.errors import (
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    PromotionStateError,
)
from app.domain.ports.promotion import ReviewItem, Statement
from app.domain.promotion import EvidenceRow, ValueScore, evidence, same_value
from app.schemas.promotion import (
    EvidenceOut,
    GroupOut,
    PromotionStatus,
    ReviewItemOut,
    RuleEditIn,
    RunOut,
    RunStarted,
    SaidOut,
    ValueChip,
)
from app.services import logger
from app.services.promotion import decisions
from app.services.promotion.review import to_scored
from app.services.promotion.service import PromotionRun, PromotionService

router = APIRouter(prefix="/promotion")

_DECIDED_SHOWN = 20


@router.get("", response_model=PromotionStatus)
async def status_(
    admin: PromotionAdminDep, service: PromotionServiceDep, repo: PromotionRepositoryDep
) -> PromotionStatus:
    """The job's state and the review list: open, active and kept items, plus
    the latest closed, rejected and dropped ones."""
    return await _status(service, repo)


@router.post("/run", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED)
async def run_now(admin: PromotionAdminDep, service: PromotionServiceDep) -> RunStarted:
    if not service.start():
        raise HTTPException(status.HTTP_409_CONFLICT, "Promotion is already running.")
    return RunStarted(started=True)


@router.post("/items/{item_id}/approve", response_model=PromotionStatus)
async def approve(
    item_id: int,
    request: Request,
    admin: PromotionAdminDep,
    service: PromotionServiceDep,
    repo: PromotionRepositoryDep,
    writer: TeamRuleWriterDep,
    body: RuleEditIn | None = None,
) -> PromotionStatus:
    edit = decisions.RuleEdit(**body.model_dump()) if body else None
    await _decide(decisions.approve(repo, writer, item_id, by=admin.email, edit=edit))
    _log(request, admin.email, "approve", item_id)
    return await _status(service, repo)


@router.post("/items/{item_id}/reject", response_model=PromotionStatus)
async def reject(
    item_id: int,
    request: Request,
    admin: PromotionAdminDep,
    service: PromotionServiceDep,
    repo: PromotionRepositoryDep,
) -> PromotionStatus:
    now = await _score_now(service, repo, item_id, against=False)
    await _decide(decisions.reject(repo, item_id, by=admin.email, score_now=now))
    _log(request, admin.email, "reject", item_id)
    return await _status(service, repo)


@router.post("/items/{item_id}/keep", response_model=PromotionStatus)
async def keep(
    item_id: int,
    request: Request,
    admin: PromotionAdminDep,
    service: PromotionServiceDep,
    repo: PromotionRepositoryDep,
) -> PromotionStatus:
    now = await _score_now(service, repo, item_id, against=True)
    await _decide(decisions.keep(repo, item_id, by=admin.email, score_now=now))
    _log(request, admin.email, "keep", item_id)
    return await _status(service, repo)


@router.post("/items/{item_id}/close", response_model=PromotionStatus)
async def close(
    item_id: int,
    request: Request,
    admin: PromotionAdminDep,
    service: PromotionServiceDep,
    repo: PromotionRepositoryDep,
    writer: TeamRuleWriterDep,
) -> PromotionStatus:
    today = datetime.now(UTC).date()
    await _decide(decisions.close(repo, writer, item_id, by=admin.email, today=today))
    _log(request, admin.email, "close", item_id)
    return await _status(service, repo)


async def _decide(call: object) -> None:
    try:
        await call  # type: ignore[misc]
    except PromotionStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Agent Memory is not configured."
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc


async def _status(service: PromotionService, repo: PromotionRepositoryDep) -> PromotionStatus:
    groups = {g.id: g for g in await repo.groups()}
    scores = await service.scores()
    items = await repo.review_items()
    rows = await repo.counted()
    by_ref = {str(r.id): r for r in rows}
    scored = to_scored(rows)
    chips = _chips(scores)
    people = _people(rows)
    live = [i for i in items if i.status in ("open", "active", "kept")]
    decided = [i for i in items if i not in live][-_DECIDED_SHOWN:]
    out: list[ReviewItemOut] = []
    for item in [*live, *reversed(decided)]:
        group = groups.get(item.group_id)
        found = _score_of(scores, item)
        pro, con = evidence(scored, item.group_id, item.value, service.weights)
        out.append(
            ReviewItemOut(
                id=item.id or 0,
                kind=item.kind,
                status=item.status,
                group_id=item.group_id,
                label=group.label if group else "",
                entity_type=group.rule_entity_type if group else "",
                entity=group.rule_entity if group else "",
                key=group.rule_key if group else "",
                value=item.value,
                score_when_listed=item.score_when_listed,
                team_score=found.team_score if found else 0.0,
                for_score=found.for_score if found else 0.0,
                against_score=found.against_score if found else 0.0,
                holders=list(found.holders) if found else [],
                decided_by=item.decided_by,
                decided_at=item.decided_at,
                rule_id=item.rule_id,
                created_at=item.created_at,
                values=chips.get(item.group_id, []),
                people=people.get(item.group_id, 0),
                for_rows=[_evidence(e, by_ref) for e in pro],
                against_rows=[_evidence(e, by_ref) for e in con],
            )
        )
    return PromotionStatus(
        enabled=settings.PROMOTION_ENABLED,
        running=service.running,
        next_run_at=service.next_run_at,
        every_minutes=settings.PROMOTION_JOB_EVERY_MINUTES,
        team_scope=settings.PROMOTION_TEAM_SCOPE,
        model_configured=bool(
            settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY.get_secret_value()
        ),
        thresholds={
            "personal_rule_at": service.personal_rule_at,
            "candidate_at": service.candidate_at,
            "flag_at": service.flag_at,
            "repeat_factor": service.weights.repeat_factor,
        },
        last_run=_run_out(service.last),
        items=out,
        groups=[
            GroupOut(id=g.id, label=g.label, values=chips.get(g.id, []), people=people.get(g.id, 0))
            for g in groups.values()
            if g.id is not None
        ],
    )


def _chips(scores: list[ValueScore]) -> dict[int, list[ValueChip]]:
    out: dict[int, list[ValueChip]] = {}
    for v in sorted(scores, key=lambda v: -v.team_score):
        if v.holders:
            out.setdefault(v.group_id, []).append(ValueChip(value=v.value, team_score=v.team_score))
    return out


def _people(rows: list[Statement]) -> dict[int, int]:
    users: dict[int, set[str]] = {}
    for r in rows:
        if r.group_id is not None:
            users.setdefault(r.group_id, set()).add(r.user)
    return {g: len(u) for g, u in users.items()}


def _evidence(row: EvidenceRow, by_ref: dict[str, Statement]) -> EvidenceOut:
    said = [
        SaidOut(text=s.text, source=s.source, said_at=s.said_at)
        for ref in row.refs
        if (s := by_ref.get(ref)) is not None
    ]
    return EvidenceOut(user=row.user, weights=list(row.weights), value=row.value, said=said)


async def _score_now(
    service: PromotionService, repo: PromotionRepositoryDep, item_id: int, *, against: bool
) -> float | None:
    """The item's score now: team score for a candidate, against-score for a flag."""
    item = next((i for i in await repo.review_items() if i.id == item_id), None)
    found = _score_of(await service.scores(), item) if item else None
    if found is None:
        return None
    return found.against_score if against else found.team_score


def _score_of(scores: list[ValueScore], item: ReviewItem) -> ValueScore | None:
    return next(
        (v for v in scores if v.group_id == item.group_id and same_value(v.value, item.value)),
        None,
    )


def _run_out(run: PromotionRun | None) -> RunOut | None:
    if run is None:
        return None
    return RunOut(
        started_at=run.started_at,
        finished_at=run.finished_at,
        listed=run.intake.listed,
        new=run.intake.new,
        replaced=run.intake.replaced,
        grouped=run.grouping.first_pass + run.grouping.full_list,
        new_topics=run.grouping.new_topics,
        left=run.grouping.left,
        opened=run.opened,
        dropped=run.dropped,
        error=run.error,
    )


def _log(request: Request, admin: str, action: str, item_id: int) -> None:
    logger.log(
        "[PROMOTION]",
        trace_id=getattr(request.state, "trace_id", None),
        admin=admin,
        action=action,
        item=item_id,
    )
