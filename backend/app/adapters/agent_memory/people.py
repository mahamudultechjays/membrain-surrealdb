"""MemoryPeople adapters for SurrealDB Agent Memory."""

import logging
import re
from typing import Any

from surrealdb_memory import AsyncMemory

from app.domain.errors import MemoryNotConfiguredError, MemoryUnavailableError
from app.domain.ports.memory_people import MemoryPerson

logger = logging.getLogger(__name__)


class AgentMemoryPeople:
    """`GET /principals` (paged) with the admin key, which holds grant:manage.

    Read raw: the pinned SDK's `principals.list()` cannot decode the response.
    Only humans named by an email are kept; service principals such as
    "admin" and "system" are not people to grant scopes to.
    """

    def __init__(self, client: AsyncMemory) -> None:
        self._client = client

    async def list(self) -> list[MemoryPerson]:
        transport = self._client.scopes._transport
        url = self._client.scopes._base.rsplit("/", 1)[0] + "/principals"
        people: dict[str, MemoryPerson] = {}
        cursor: str | None = None
        try:
            while True:
                page: dict[str, Any] = await transport.request(
                    "GET", url, params={"cursor": cursor} if cursor else None
                )
                for principal in page.get("principals", []):
                    email = str(principal.get("displayName") or "").strip().lower()
                    if principal.get("kind") == "human" and "@" in email:
                        people[email] = MemoryPerson(
                            email=email,
                            name=name_from(email),
                            grants=_grants(principal.get("grants")),
                        )
                more = page.get("page") or {}
                cursor = more.get("nextCursor")
                if not (more.get("hasMore") and cursor):
                    return list(people.values())
        except Exception as exc:
            logger.warning("Agent Memory principal listing failed", exc_info=True)
            raise MemoryUnavailableError(str(exc)) from exc


def _grants(raw: Any) -> dict[str, list[str]]:
    """{permission: [scope pattern, …]}, dropping anything not in that shape."""
    if not isinstance(raw, dict):
        return {}
    return {
        str(permission): [str(p) for p in patterns]
        for permission, patterns in raw.items()
        if isinstance(patterns, list)
    }


def name_from(email: str) -> str:
    """A readable name from an email, e.g. stephen.howard@x.com → Stephen Howard."""
    words = [w for w in re.split(r"[._\-+]+", email.split("@", 1)[0]) if w]
    return " ".join(w.capitalize() for w in words) or email


class NotConfiguredPeople:
    """Stands in when AGENT_MEMORY_* settings are missing."""

    async def list(self) -> list[MemoryPerson]:
        raise MemoryNotConfiguredError
