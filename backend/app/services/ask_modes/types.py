"""Types shared by the Ask modes."""

from dataclasses import dataclass
from typing import Literal

from app.services.ask_flow import Answer
from app.services.ask_modes.points import Conflict, FactVerdict

AskMode = Literal["default", "best_match", "by_layer"]
ASK_MODES: tuple[AskMode, ...] = ("default", "best_match", "by_layer")


@dataclass(frozen=True, slots=True)
class ModeAnswer:
    mode: AskMode
    answer: Answer
    # Empty for default.
    conflicts: list[Conflict]
    # Hit id -> verdict, for best_match only.
    verdicts: dict[str, FactVerdict]
