from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from app.adapters.anthropic.grouping import (
    ClaudeGroupingModel,
    MatchList,
    MatchOut,
    NotConfiguredGroupingModel,
)
from app.domain.errors import GroupingModelError
from app.domain.ports.grouping_model import NewTopic, StatementIn, TopicIn, TopicMatch


class Messages:
    def __init__(self, parsed: Any = None, error: Exception | None = None) -> None:
        self.parsed, self.error = parsed, error
        self.kwargs: dict[str, Any] = {}

    async def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(parsed_output=self.parsed, stop_reason="end_turn")


def model(messages: Messages) -> ClaudeGroupingModel:
    return ClaudeGroupingModel(SimpleNamespace(messages=messages), "claude-haiku-5-5")  # type: ignore[arg-type]


S = [
    StatementIn(
        "1", "cobalt ridge", "Cobalt Ridge return window is 30 days", "return_window", "30 days"
    )
]
T = [TopicIn(7, "Cobalt Ridge return window", ("30 days",))]


async def test_claude_grouping_maps_parsed_output() -> None:
    parsed = MatchList(matches=[
        MatchOut(ref="1", topic_id=7, value="30 days", stance="for"),
        MatchOut(
            ref="2", new_label="X", new_entity_type="org", new_entity="X Co", new_key="k",
            value="v", stance="against",
        ),
    ])  # fmt: skip
    m = Messages(parsed)
    out = await model(m).match(S, T, allow_new=True)
    assert out == [
        TopicMatch("1", 7, None, "30 days", "for"),
        TopicMatch("2", None, NewTopic("X", "org", "X Co", "k"), "v", "against"),
    ]
    assert m.kwargs["model"] == "claude-haiku-5-5"
    assert m.kwargs["output_format"] is MatchList
    assert '"allow_new": true' in m.kwargs["messages"][0]["content"]


async def test_new_topic_without_allow_new_is_dropped() -> None:
    parsed = MatchList(
        matches=[
            MatchOut(
                ref="1",
                new_label="X",
                new_entity_type="o",
                new_entity="e",
                new_key="k",
                value="v",
                stance="for",
            )
        ]
    )
    assert await model(Messages(parsed)).match(S, T, allow_new=False) == [
        TopicMatch("1", None, None, "v", "for")
    ]


async def test_api_errors_become_grouping_errors() -> None:
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))
    with pytest.raises(GroupingModelError):
        await model(Messages(error=err)).match(S, T, allow_new=True)


async def test_not_configured_raises() -> None:
    with pytest.raises(GroupingModelError, match="ANTHROPIC_API_KEY"):
        await NotConfiguredGroupingModel().match(S, T, allow_new=True)


async def test_invalid_model_output_becomes_a_grouping_error() -> None:
    from pydantic import ValidationError

    try:
        MatchOut.model_validate({"ref": "1"})
    except ValidationError as exc:
        error = exc
    with pytest.raises(GroupingModelError):
        await model(Messages(error=error)).match(S, T, allow_new=True)
