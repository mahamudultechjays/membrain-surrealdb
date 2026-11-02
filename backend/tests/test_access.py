import pytest

from app.adapters.sqlite import SqliteUserScopes
from app.domain.errors import ScopeNotGrantedError
from app.services.access import AccessService

JANE = "Jane.Doe@Spreetail.com"


class FakeRegistry:
    def __init__(self) -> None:
        self.ensured: list[str] = []

    async def list(self, prefix: str = "") -> list[str]:
        return [p for p in self.ensured if p.startswith(prefix)]

    async def ensure(self, path: str) -> None:
        self.ensured.append(path)


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry()


@pytest.fixture
def access(registry: FakeRegistry) -> AccessService:
    return AccessService(
        SqliteUserScopes(":memory:"),
        registry,
        org_scope="org/spreetail",
        user_root="org/spreetail/user",
    )


@pytest.mark.parametrize(
    ("name", "email", "expected"),
    [
        ("Arun Das", "a@x.com", "org/spreetail/user/arun_das"),
        ("Md. Mahamudul Hasan", "m@x.com", "org/spreetail/user/md_hasan"),
        ("Priya", "p@x.com", "org/spreetail/user/priya"),
        ("", "deena.k@x.com", "org/spreetail/user/deena_k"),
    ],
)
def test_personal_scope_is_first_and_last_name(
    access: AccessService, name: str, email: str, expected: str
) -> None:
    assert access.personal_scope(name, email) == expected


async def test_first_sign_in_creates_personal_and_org_grants(
    access: AccessService, registry: FakeRegistry
) -> None:
    grants = await access.sign_in(JANE, "Jane Doe")

    assert [(g.scope_path, g.access, g.layer) for g in grants] == [
        ("org/spreetail", "read", "org"),
        ("org/spreetail/user/jane_doe", "write", "personal"),
    ]
    assert grants[0].email == "jane.doe@spreetail.com"
    assert registry.ensured == ["org/spreetail/user/jane_doe"]


async def test_second_sign_in_changes_nothing(
    access: AccessService, registry: FakeRegistry
) -> None:
    await access.sign_in(JANE, "Jane Doe")
    again = await access.sign_in(JANE, "Jane Doe")

    assert len(again) == 2
    assert registry.ensured == ["org/spreetail/user/jane_doe"]


async def test_write_scope_defaults_to_personal_and_checks_grants(access: AccessService) -> None:
    await access.sign_in(JANE, "Jane Doe")

    assert await access.write_scope(JANE, None) == "org/spreetail/user/jane_doe"
    assert await access.write_scope(JANE, "org/spreetail/user/jane_doe/") == (
        "org/spreetail/user/jane_doe"
    )
    with pytest.raises(ScopeNotGrantedError):
        await access.write_scope(JANE, "org/spreetail")  # read only
    with pytest.raises(ScopeNotGrantedError):
        await access.write_scope("nobody@x.com", None)


async def test_grant_registers_and_revoke_removes(
    access: AccessService, registry: FakeRegistry
) -> None:
    await access.sign_in(JANE, "Jane Doe")

    await access.grant(JANE, "Jane Doe", "org/spreetail/team/ops", "read", "team")
    readable = {g.scope_path for g in await access.readable(JANE)}

    assert "org/spreetail/team/ops" in readable
    assert registry.ensured[-1] == "org/spreetail/team/ops"
    assert await access.revoke(JANE, "org/spreetail/team/ops") is True
    assert await access.revoke(JANE, "org/spreetail/team/ops") is False
    assert len(await access.all_grants()) == 2
