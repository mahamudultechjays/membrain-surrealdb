"""Layer precedence for Chat and Reflect: org > team > personal.

Agent Memory compares values only within one scope, so when the same fact
holds different values in different layers it returns them as equals. The
rule that a broader layer overrides a narrower one is ours, applied here:

- Chat keeps Agent Memory's answer and tags each citation with the layer it
  came from, found by running Search's per-layer recall alongside the chat.
- Reflect reflects once per scope (each key reads only that scope), and the
  highest layer whose reflection drew on any evidence applies; the others are
  overridden. Nothing is hidden.
"""

from dataclasses import dataclass
from typing import Literal

from app.domain.ports.memory_chat import Reflection
from app.domain.ports.memory_recall import MemoryRecall
from app.domain.ports.user_scopes import LayerName, ScopeGrant
from app.services import ask_flow

LayerStatus = Literal["applies", "overridden", "empty", "failed"]


@dataclass(frozen=True, slots=True)
class LayerSource:
    layer: LayerName
    scope: str


@dataclass(frozen=True, slots=True)
class LayerReflection:
    layer: LayerName
    scope: str
    status: LayerStatus
    reflection: Reflection | None = None
    error: str | None = None


async def sources_by_id(
    recall: MemoryRecall, readable: list[ScopeGrant], scopes: tuple[str, ...], question: str
) -> dict[str, LayerSource]:
    """Record id -> the layer it was found in, for the scopes a chat reads.

    Best effort: a failing search leaves citations untagged rather than failing
    the chat. Search credits a record seen in several layers to the narrowest.
    """
    grants = [g for g in readable if g.scope_path in scopes]
    if not grants:
        return {}
    try:
        answer = await ask_flow.ask(recall, grants, q=question)
    except Exception:
        return {}
    return {
        hit.id: LayerSource(layer.layer, layer.area)
        for layer in answer.layers
        for hit in layer.hits
    }


def resolve(
    layers: list[tuple[LayerName, str]], results: list[Reflection | BaseException]
) -> list[LayerReflection]:
    """Mark each layer's reflection, in order org > team > personal.

    The first layer whose reflection drew on evidence applies; later layers
    with evidence are overridden; layers without evidence are empty.
    """
    resolved: list[LayerReflection] = []
    winner_found = False
    for (layer, scope), result in zip(layers, results, strict=True):
        if isinstance(result, BaseException):
            resolved.append(LayerReflection(layer, scope, "failed", error=str(result) or "failed"))
        elif not result.evidence:
            resolved.append(LayerReflection(layer, scope, "empty", reflection=result))
        elif not winner_found:
            winner_found = True
            resolved.append(LayerReflection(layer, scope, "applies", reflection=result))
        else:
            resolved.append(LayerReflection(layer, scope, "overridden", reflection=result))
    return resolved
