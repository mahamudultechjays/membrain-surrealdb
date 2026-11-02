from pathlib import Path

from app.adapters.sqlite import SqliteUserScopes
from app.domain.ports.user_scopes import ScopeGrant


async def test_grants_persist_in_the_file_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "grants.db"
    first = SqliteUserScopes(db)
    await first.put(ScopeGrant("A@X.com", "A", "org/x/user/a", "write", "personal"))

    second = SqliteUserScopes(db)

    assert await second.grants_for("a@x.com") == [
        ScopeGrant("a@x.com", "A", "org/x/user/a", "write", "personal")
    ]


async def test_put_updates_access_and_remove_reports(tmp_path: Path) -> None:
    repo = SqliteUserScopes(tmp_path / "g.db")
    await repo.put(ScopeGrant("a@x.com", "A", "org/x", "read", "org"))
    await repo.put(ScopeGrant("a@x.com", "A", "org/x", "write", "org"))
    await repo.put(ScopeGrant("b@x.com", "B", "org/x", "read", "org"))

    assert [g.access for g in await repo.grants_for("a@x.com")] == ["write"]
    assert [g.email for g in await repo.all_grants()] == ["a@x.com", "b@x.com"]
    assert await repo.remove("a@x.com", "org/x") is True
    assert await repo.remove("a@x.com", "org/x") is False
    assert await repo.grants_for("a@x.com") == []
