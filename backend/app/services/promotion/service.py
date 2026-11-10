"""The promotion job: intake, grouping, scores, review list. One run at a time.

Same pattern as the VCT tagger: an in-process lock (the backend is one uvicorn
process), start() for Run now, loop() for the schedule, and the last run kept
in memory only (blank after a restart until the next run).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.errors import (
    MemoryNotConfiguredError,
    MemoryUnavailableError,
    PromotionBusyError,
)
from app.domain.ports.fact_lister import FactLister
from app.domain.ports.grouping_model import GroupingModel
from app.domain.ports.promotion import PromotionRepository
from app.domain.ports.user_scopes import UserScopeRepository
from app.domain.promotion import ValueScore, Weights, score
from app.services.promotion.grouping import GroupingStats, group_new
from app.services.promotion.intake import IntakeStats, intake, personal_owners
from app.services.promotion.review import apply_review, plan_review, to_scored

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class PromotionRun:
    started_at: str
    finished_at: str | None = None
    intake: IntakeStats = field(default_factory=IntakeStats)
    grouping: GroupingStats = field(default_factory=GroupingStats)
    opened: int = 0
    dropped: int = 0
    error: str | None = None


class PromotionService:
    def __init__(
        self,
        repo: PromotionRepository,
        lister: FactLister,
        model: GroupingModel,
        grants: UserScopeRepository,
        *,
        weights: Weights,
        personal_rule_at: float,
        candidate_at: float,
        flag_at: float,
        batch_size: int,
        generic_subjects: frozenset[str],
    ) -> None:
        self.repo = repo
        self._lister = lister
        self._model = model
        self._grants = grants
        self.weights = weights
        self.personal_rule_at = personal_rule_at
        self.candidate_at = candidate_at
        self.flag_at = flag_at
        self._batch_size = batch_size
        self._generic = generic_subjects
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[PromotionRun | None] | None = None
        self.last: PromotionRun | None = None
        self.next_run_at: str | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked() or (self._task is not None and not self._task.done())

    def start(self) -> bool:
        """Run in the background (Run now); False when a run is already going."""
        if self.running:
            return False
        self._task = asyncio.create_task(self._quiet_run())
        return True

    async def run(self) -> PromotionRun:
        if self._lock.locked():
            raise PromotionBusyError
        async with self._lock:
            run = PromotionRun(started_at=_now())
            try:
                await self._steps(run)
            finally:
                run.finished_at = _now()
                self.last = run
            logger.info(
                "Promotion run: listed=%d new=%d replaced=%d grouped=%d new_topics=%d "
                "left=%d opened=%d dropped=%d error=%s",
                run.intake.listed, run.intake.new, run.intake.replaced,
                run.grouping.first_pass + run.grouping.full_list, run.grouping.new_topics,
                run.grouping.left, run.opened, run.dropped, run.error,
            )  # fmt: skip
            return run

    async def _steps(self, run: PromotionRun) -> None:
        now = _now()
        owners = personal_owners(await self._grants.all_grants())
        try:
            run.intake = await intake(self.repo, self._lister, owners, now=now)
        except (MemoryNotConfiguredError, MemoryUnavailableError) as exc:
            run.error = str(exc) or type(exc).__name__
            return
        run.grouping = await group_new(
            self.repo,
            self._model,
            batch_size=self._batch_size,
            generic_subjects=self._generic,
            now=now,
        )
        run.error = run.grouping.error
        changes = plan_review(
            await self.scores(),
            await self.repo.review_items(),
            candidate_at=self.candidate_at,
            flag_at=self.flag_at,
        )
        await apply_review(self.repo, changes)
        run.opened, run.dropped = len(changes.open), len(changes.drop)

    async def scores(self) -> list[ValueScore]:
        rows = to_scored(await self.repo.counted())
        rules = [
            (i.group_id, i.value)
            for i in await self.repo.review_items()
            if i.kind == "candidate" and i.status == "active"
        ]
        return score(rows, self.weights, personal_rule_at=self.personal_rule_at, extra=rules)

    async def loop(self, interval_seconds: float) -> None:
        """Run every `interval_seconds`, the first time after one interval."""
        while True:
            next_at = datetime.now(UTC) + timedelta(seconds=interval_seconds)
            self.next_run_at = next_at.isoformat(timespec="seconds")
            await asyncio.sleep(interval_seconds)
            await self._quiet_run()

    async def _quiet_run(self) -> PromotionRun | None:
        try:
            return await self.run()
        except PromotionBusyError:
            return None
        except Exception:
            logger.exception("Promotion run failed")
            return None
