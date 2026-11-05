from pathlib import Path

from app.adapters.sqlite import SqliteOnboarding, SqliteUserScopes
from app.domain.ports.onboarding import MappedNode, OnboardingRecord


def _record(nodes: list[MappedNode]) -> OnboardingRecord:
    return OnboardingRecord(
        email="Priya.Shah@X.com", primary_work="I run receiving", team="Ops", nodes=nodes
    )


async def test_unknown_user_has_no_onboarding() -> None:
    assert await SqliteOnboarding(":memory:").get("nobody@x.com") is None


async def test_save_then_replace_on_a_file_shared_with_grants(tmp_path: Path) -> None:
    db = tmp_path / "data" / "user_scopes.db"
    SqliteUserScopes(db)  # both stores live in one file
    repo = SqliteOnboarding(db)

    chosen = [MappedNode("sc4", 1, True, "user"), MappedNode("sc6", 2, False, "user")]
    await repo.save(_record(chosen))
    first = await repo.get("priya.shah@x.com")
    await repo.save(_record([MappedNode("fi4", 1, True, "admin")]))
    second = await repo.get("PRIYA.SHAH@x.com")

    assert first is not None and second is not None
    assert first.email == "priya.shah@x.com"
    assert first.team == "Ops"
    assert first.onboarded_at
    assert [n.node_id for n in first.nodes] == ["sc4", "sc6"]
    assert second.nodes == [MappedNode("fi4", 1, True, "admin")]
