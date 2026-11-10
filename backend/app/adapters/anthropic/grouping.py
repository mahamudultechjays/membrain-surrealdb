"""GroupingModel on a small Claude model, with structured output.

One call per batch: the statements and the topics go in as JSON; the model
returns one match per statement it can place. Anything it gets wrong (unknown
ref or topic) is filtered by the grouping service and retried next run.
"""

import json
from typing import Literal

import anthropic
from pydantic import BaseModel, ValidationError

from app.domain.errors import GroupingModelError
from app.domain.ports.grouping_model import NewTopic, StatementIn, TopicIn, TopicMatch

SYSTEM = """You group short business facts into topics for a team knowledge base.

You get statements (facts people saved) and topics (things people already make
claims about). For each statement, decide which topic it is about:
- Match by meaning, not wording: "return policy" and "returns window" for the
  same company are one topic. A different company or a different attribute is
  a different topic.
- If a topic fits, give its topic_id.
- If none fits and allow_new is true, give new_label (short, like "Cobalt Ridge
  return window"), new_entity_type (organization, person, product, policy...),
  new_entity (the proper name) and new_key (snake_case attribute name).
- Statements in this batch about the same new fact (same entity and attribute,
  even if worded differently) must get the exact same new_label, new_entity
  and new_key.
- If none fits and allow_new is false, leave topic_id and new_label empty.
- value: the statement's value written the way the topic already writes its
  values ("about two weeks" -> "14 days" when the topic uses days).
- stance: "against" only when the statement denies a value ("it is not 30
  days"); otherwise "for".
Return one entry per statement, using its ref."""


class MatchOut(BaseModel):
    ref: str
    topic_id: int | None = None
    new_label: str | None = None
    new_entity_type: str | None = None
    new_entity: str | None = None
    new_key: str | None = None
    value: str
    stance: Literal["for", "against"] = "for"


class MatchList(BaseModel):
    matches: list[MatchOut]


class ClaudeGroupingModel:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    async def match(
        self, statements: list[StatementIn], topics: list[TopicIn], *, allow_new: bool
    ) -> list[TopicMatch]:
        payload = {
            "allow_new": allow_new,
            "topics": [{"id": t.id, "label": t.label, "values": list(t.values)} for t in topics],
            "statements": [
                {"ref": s.ref, "subject": s.subject, "text": s.text, "key": s.key, "value": s.value}
                for s in statements
            ],
        }
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=4096,
                output_config={"effort": "low"},
                system=SYSTEM,
                messages=[{"role": "user", "content": json.dumps(payload)}],
                output_format=MatchList,
            )
        except anthropic.APIError as exc:
            raise GroupingModelError(f"Claude call failed: {exc}") from exc
        except ValidationError as exc:
            raise GroupingModelError(f"Claude answer did not match the schema: {exc}") from exc
        parsed = response.parsed_output
        if parsed is None:
            raise GroupingModelError(f"No grouping answer (stop_reason={response.stop_reason})")
        return [_match(m, allow_new) for m in parsed.matches]


def _match(m: MatchOut, allow_new: bool) -> TopicMatch:
    new = None
    if m.topic_id is None and allow_new and m.new_label:
        new = NewTopic(m.new_label, m.new_entity_type or "", m.new_entity or "", m.new_key or "")
    return TopicMatch(m.ref, m.topic_id, new, m.value, m.stance)


class NotConfiguredGroupingModel:
    async def match(
        self, statements: list[StatementIn], topics: list[TopicIn], *, allow_new: bool
    ) -> list[TopicMatch]:
        raise GroupingModelError("ANTHROPIC_API_KEY is not set")
