"""Port for the small model that matches statements to topics (spec 5.1)."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.promotion import Stance


@dataclass(frozen=True, slots=True)
class StatementIn:
    ref: str
    subject: str
    text: str
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class TopicIn:
    id: int
    label: str
    # Values already in the topic, in the form it uses.
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NewTopic:
    label: str
    entity_type: str
    entity: str
    key: str


@dataclass(frozen=True, slots=True)
class TopicMatch:
    ref: str
    # None with new_topic None: "none of these".
    topic_id: int | None
    new_topic: NewTopic | None
    # The value in the form the topic uses ("about two weeks" -> "14 days").
    value: str
    stance: Stance


class GroupingModel(Protocol):
    async def match(
        self, statements: list[StatementIn], topics: list[TopicIn], *, allow_new: bool
    ) -> list[TopicMatch]:
        """Raises GroupingModelError when the model cannot answer."""
        ...
