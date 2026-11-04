"""Memory jobs: run one operation on one scope, counting facts before and after.

The counts are what the experiments compare (e.g. 9 facts -> 15 after
consolidation). Background elaboration can also add relations between runs,
so the "before" count is always taken right before the job.
"""

import time
from dataclasses import dataclass
from typing import Literal

from app.domain.ports.memory_lab import LabCounts, LabOutcome, MemoryLab

LabAction = Literal["consolidate", "elaborate", "reflect"]


class LabScopeError(ValueError):
    """Not a scope under the org scope."""


@dataclass(frozen=True, slots=True)
class LabRun:
    action: LabAction
    scope: str | None
    before: LabCounts
    after: LabCounts
    outcome: LabOutcome
    latency_ms: int


def check_scope(org: str, scope: str) -> str:
    """The scope, if it is the org scope or below it."""
    org = org.strip("/")
    scope = scope.strip("/")
    if scope != org and not scope.startswith(f"{org}/"):
        raise LabScopeError(f"Jobs run only on scopes under {org}.")
    return scope


async def run(
    lab: MemoryLab,
    action: LabAction,
    scope: str | None,
    *,
    query: str | None = None,
    dry_run: bool = False,
    persist: bool = False,
) -> LabRun:
    started = time.perf_counter()
    before = await lab.counts(scope)
    outcome: LabOutcome
    if action == "consolidate":
        outcome = await lab.consolidate(scope, dry_run=dry_run)
    elif scope is None:
        raise LabScopeError("Only consolidation can run on the whole context.")
    elif action == "elaborate":
        outcome = await lab.elaborate(scope, dry_run=dry_run)
    else:
        outcome = await lab.reflect(scope, query or "", persist=persist)
    after = await lab.counts(scope)
    return LabRun(
        action=action,
        scope=scope,
        before=before,
        after=after,
        outcome=outcome,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
