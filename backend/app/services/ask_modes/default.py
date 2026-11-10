"""Default mode: every readable scope, listed by layer, with nothing compared."""

from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.user_scopes import ScopeGrant
from app.services import ask_flow
from app.services.ask_flow import Answer
from app.services.ask_modes.types import ModeAnswer


async def run(recall: MemoryRecall, grants: list[ScopeGrant], *, q: str) -> ModeAnswer:
    return apply(await ask_flow.ask(recall, grants, q=q))


def apply(answer: Answer) -> ModeAnswer:
    return ModeAnswer("default", answer, conflicts=[], verdicts={})
