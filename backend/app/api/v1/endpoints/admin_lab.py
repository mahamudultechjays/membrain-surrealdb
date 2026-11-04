"""Memory jobs (admins only): trigger consolidate, elaborate or reflect on a scope.

For the 2026-11-04 standup experiments: pick a scope, trigger a job, and see
what it did and how the fact counts changed. Any scope under ORG_SCOPE can be
used, each with a key that reads and writes only that scope. The whole Context
(scope null) is allowed only as a consolidation preview, since it pools every
scope. Decay, expire and fsck are left out: they are Context-wide.
"""

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AdminUserDep, MemoryLabDep
from app.core.config import settings
from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.schemas.lab import LabCountsOut, LabOutcomeOut, LabRunRequest, LabRunResponse
from app.services import lab_flow, logger
from app.services.lab_flow import LabScopeError

router = APIRouter(prefix="/admin/lab")


@router.post(
    "/runs",
    response_model=LabRunResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Agent Memory failing"}},
)
async def run_job(
    body: LabRunRequest, request: Request, admin: AdminUserDep, lab: MemoryLabDep
) -> LabRunResponse:
    """Run one job on a scope, with fact counts taken before and after."""
    try:
        scope = None if body.scope is None else lab_flow.check_scope(settings.ORG_SCOPE, body.scope)
        result = await lab_flow.run(
            lab,
            body.action,
            scope,
            query=body.query,
            dry_run=body.dry_run,
            persist=body.persist,
        )
    except LabScopeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except MemoryNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent Memory is not configured. Set AGENT_MEMORY_* in .env.",
        ) from exc
    except MemoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Agent Memory call failed: {exc}"
        ) from exc

    logger.log(
        "[JOB]",
        trace_id=getattr(request.state, "trace_id", None),
        user=admin.email,
        action=body.action,
        scope=scope or "(whole context)",
        dry_run=body.dry_run if body.action != "reflect" else None,
        persist=body.persist if body.action == "reflect" else None,
        attributes=f"{result.before.attributes}->{result.after.attributes}",
        relations=f"{result.before.relations}->{result.after.relations}",
        summary=result.outcome.summary,
        latency_ms=result.latency_ms,
        memory_trace=",".join(result.outcome.trace_ids[:5]) or None,
        # Reflection traces keep no answer text (checked 2026-11-04), so log the
        # question and the start of the answer for the experiment record.
        query=repr(body.query[:120]) if body.query else None,
        answer=repr(result.outcome.text[:300]) if result.outcome.text else None,
    )
    return LabRunResponse(
        action=result.action,
        scope=result.scope,
        before=LabCountsOut(**asdict(result.before)),
        after=LabCountsOut(**asdict(result.after)),
        outcome=LabOutcomeOut(**asdict(result.outcome)),
        latency_ms=result.latency_ms,
        ran_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
