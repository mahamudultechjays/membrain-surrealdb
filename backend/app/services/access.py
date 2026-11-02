"""Access: which Agent Memory scopes each user may read or write.

Our backend is the governance layer. Agent Memory is reached with one admin
key, so every read must carry a lens and every write a scope taken from these
grants; Agent Memory itself would let the admin key touch anything.

A user seen for the first time gets a personal scope,
<user root>/<firstname>_<lastname> (read and write), registered in Agent Memory
if missing, plus read on the org scope. Teams are granted by an admin.
"""

import re

from app.domain.errors import ScopeNotGrantedError
from app.domain.ports.scope_registry import ScopeRegistry
from app.domain.ports.user_scopes import Access, LayerName, ScopeGrant, UserScopeRepository


class AccessService:
    def __init__(
        self,
        grants: UserScopeRepository,
        registry: ScopeRegistry,
        *,
        org_scope: str,
        user_root: str,
    ) -> None:
        self._grants = grants
        self._registry = registry
        self._org_scope = org_scope.strip("/")
        self._user_root = user_root.strip("/")

    def personal_scope(self, name: str, email: str) -> str:
        """'Arun Das' -> <user root>/arun_das; a one-word name or none falls back sensibly."""
        words = [w for w in (re.sub(r"[^a-z0-9]", "", w) for w in name.lower().split()) if w]
        if words:
            slug = "_".join([words[0], words[-1]] if len(words) > 1 else words)
        else:
            slug = re.sub(r"[^a-z0-9]+", "_", email.split("@")[0].lower()).strip("_") or "user"
        return f"{self._user_root}/{slug}"

    async def sign_in(self, email: str, name: str) -> list[ScopeGrant]:
        """The user's grants, creating the defaults the first time they appear."""
        held = await self._grants.grants_for(email)
        if not any(g.layer == "personal" for g in held):
            personal = self.personal_scope(name, email)
            await self._registry.ensure(personal)
            await self._grants.put(ScopeGrant(email, name, personal, "write", "personal"))
        if not any(g.scope_path == self._org_scope for g in held):
            await self._grants.put(ScopeGrant(email, name, self._org_scope, "read", "org"))
        return await self._grants.grants_for(email)

    async def grants_for(self, email: str) -> list[ScopeGrant]:
        return await self._grants.grants_for(email)

    async def readable(self, email: str) -> list[ScopeGrant]:
        """Every grant reads; write implies read."""
        return await self._grants.grants_for(email)

    async def writable(self, email: str) -> list[ScopeGrant]:
        return [g for g in await self._grants.grants_for(email) if g.access == "write"]

    async def write_scope(self, email: str, requested: str | None) -> str:
        """The scope a write goes to: the one asked for if the user may write it,
        else their personal scope. Raises ScopeNotGrantedError otherwise."""
        writable = await self.writable(email)
        if requested is None:
            personal = next((g for g in writable if g.layer == "personal"), None)
            if personal is None:
                raise ScopeNotGrantedError("no personal scope to write to")
            return personal.scope_path
        if not any(g.scope_path == requested.strip("/") for g in writable):
            raise ScopeNotGrantedError(requested)
        return requested.strip("/")

    async def all_grants(self) -> list[ScopeGrant]:
        return await self._grants.all_grants()

    async def grant(
        self, email: str, name: str, scope_path: str, access: Access, layer: LayerName
    ) -> ScopeGrant:
        """Give a user a scope, registering it in Agent Memory first if needed."""
        path = scope_path.strip("/")
        await self._registry.ensure(path)
        grant = ScopeGrant(email.strip().lower(), name, path, access, layer)
        await self._grants.put(grant)
        return grant

    async def revoke(self, email: str, scope_path: str) -> bool:
        return await self._grants.remove(email, scope_path.strip("/"))
