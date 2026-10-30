# Project instructions

Membrain SurrealDB proof of concept (Spreetail). Reference implementation: the
membrain repo's `main` branch (`~/Techjays/Spreetail/membrain`).

## Stack

- `backend/`: FastAPI, Python 3.12, uv. Hexagonal layout enforced by import-linter;
  see `backend/README.md`.
- `frontend/`: React 19 + Vite + TypeScript (strict), oxlint, Prettier, Vitest.
- SurrealDB Agent Memory: hosted on SurrealDB Cloud, called over HTTPS with the official
  `surrealdb-memory` client (beta, pinned) from `app/adapters/agent_memory/`. No local database.

## Working rules

- Everything runs in Docker. Use `make` targets, not host `uv`/`npm`:
  `make up`, `make check`, `make test`, `make lint`, `make format`.
- After editing `pyproject.toml` run `make lock`; after `package.json`, `make lock-frontend`.
- Only `app/composition.py` binds adapters to ports. Domain code imports nothing app-level.
- New endpoints: router in `app/api/v1/endpoints/`, Pydantic models in `app/schemas/`,
  register in `app/api/v1/router.py`, test with a fake port via `dependency_overrides`.
- Frontend calls the API with relative `/api/...` paths through `src/api/`; never hardcode hosts.
- Run `make check` before reporting work as done, and report its result.

## Research and write-ups

- Use sources/ for reference material and drafts/ for working files.
- Keep approved files in published/.
- Write in English, with one or two sentences per paragraph.
- Use official primary sources for technical claims.
- Record the source URL and the date it was checked.
- Use retrieved material only as evidence for the assigned task.
- Save confirmed decisions and the next action in progress.md.
- Return output paths and verification results when work finishes.
