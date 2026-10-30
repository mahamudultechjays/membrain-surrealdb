# Backend

FastAPI service for the Membrain SurrealDB POC. Python 3.12, managed with [uv](https://docs.astral.sh/uv/).

## Layout

Hexagonal, enforced by import-linter (`[tool.importlinter]` in `pyproject.toml`):

| Path | Role |
|---|---|
| `app/api/` | HTTP layer: routers, request/response wiring, `deps.py` |
| `app/composition.py` | Composition root: the only place adapters are bound to ports |
| `app/adapters/` | Concrete integrations (Agent Memory lives in `adapters/agent_memory/`) |
| `app/services/` | Use cases; depend on domain ports only |
| `app/domain/` | Entities and ports (`Protocol`s); imports nothing app-level |
| `app/schemas/` | Pydantic request/response models |
| `app/core/` | Settings and logging |

## Commands

Run from the repository root; everything executes inside the `backend` container.

```bash
make test        # pytest
make lint        # ruff + mypy + import-linter
make format      # ruff format + autofix
make lock        # refresh uv.lock after editing pyproject.toml
```

API docs: http://localhost:8000/docs
