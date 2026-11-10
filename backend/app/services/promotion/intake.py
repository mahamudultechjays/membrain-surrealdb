"""Intake: list every personal scope's facts and keep new ones as statements.

Chat through the Claude plugin writes straight to Agent Memory, so listing is
the one path that sees both chat and app captures (check S5). A fact that
replaced another marks the old statement replaced; a fact missing from a
complete listing was removed, and so are statements in scopes nobody owns any
more. A capped listing marks nothing removed; a fact listed again counts again.
"""

from dataclasses import dataclass

from app.domain.ports.fact_lister import FactLister, ListedFact
from app.domain.ports.promotion import PromotionRepository, Source, Statement
from app.domain.ports.user_scopes import ScopeGrant

SOURCES: dict[str, Source] = {"turn": "chat", "upsert": "app"}


@dataclass
class IntakeStats:
    listed: int = 0
    new: int = 0
    replaced: int = 0
    skipped: int = 0
    capped: bool = False


def personal_owners(grants: list[ScopeGrant]) -> dict[str, str]:
    """scope_path -> email, for personal scopes only."""
    owners: dict[str, str] = {}
    for g in grants:
        if g.layer == "personal":
            owners.setdefault(g.scope_path, g.email)
    return owners


def _statement(fact: ListedFact, scope: str, user: str, now: str) -> Statement | None:
    source = SOURCES.get(fact.source_kind or "")
    if source is None or not fact.key or not fact.value:
        return None
    return Statement(
        user=user,
        scope=scope,
        memory_ref=fact.id,
        source=source,
        text=fact.text,
        entity=fact.entity or "",
        key=fact.key,
        value=fact.value,
        said_at=fact.created_at or now,
    )


async def intake(
    repo: PromotionRepository,
    lister: FactLister,
    owners: dict[str, str],
    *,
    now: str,
    page_size: int = 200,
    max_pages: int = 50,
) -> IntakeStats:
    stats = IntakeStats()
    scopes = sorted(owners)
    if not scopes:
        return stats
    seen: set[str] = set()
    superseded: list[str] = []
    cursor: str | None = None
    for page_no in range(max_pages):
        page = await lister.page(scopes, limit=page_size, cursor=cursor)
        rows: list[Statement] = []
        for fact in page.facts:
            scope = next((s for s in fact.scopes if s in owners), None)
            row = _statement(fact, scope, owners[scope], now) if scope else None
            if row is None:
                stats.skipped += 1
                continue
            stats.listed += 1
            seen.add(fact.id)
            rows.append(row)
            if fact.supersedes:
                superseded.append(fact.supersedes)
        stats.new += await repo.add_statements(rows)
        cursor = page.cursor
        if cursor is None:
            break
        if page_no == max_pages - 1:
            stats.capped = True
    # Listed again after a short listing marked it removed: it counts again.
    await repo.revive(sorted(seen - set(superseded)))
    stats.replaced += await repo.mark_replaced(superseded, now)
    if not stats.capped:
        gone = sorted(await repo.live_refs(scopes) - seen)
        stats.replaced += await repo.mark_replaced(gone, now)
        # Scopes nobody owns any more (the person lost their personal scope).
        orphaned = sorted(await repo.live_refs_except(scopes))
        stats.replaced += await repo.mark_replaced(orphaned, now)
    return stats
