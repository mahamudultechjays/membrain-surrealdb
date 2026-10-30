# Membrain SurrealDB POC

Proof of concept evaluating SurrealDB for Membrain. React + Vite frontend, FastAPI backend, SurrealDB, all running in Docker.

## Prerequisites

- Docker Desktop (Compose v2.24+)
- `make`

No local Python or Node install is needed; every command runs in a container.

## Quick start

```bash
make up          # creates .env, builds images, starts everything, waits for health
```

| Service | URL |
|---|---|
| Frontend (Vite, HMR) | http://localhost:5174 |
| Backend API docs | http://localhost:8000/docs |
| SurrealDB (RPC) | ws://localhost:8001/rpc |

Edits under `backend/` and `frontend/` reload automatically. Host ports are set in `.env`; the frontend defaults to 5174 so this stack runs alongside membrain's.

## Common commands

```bash
make help        # list everything
make logs s=backend
make check       # lint + type-check + tests, backend and frontend
make format
make shell-db    # SurrealQL REPL
make prod        # production-shaped images (nginx on :8080)
make down        # stop (data kept)
make clean       # stop and delete SurrealDB data
```

## Layout

```
backend/    FastAPI app (hexagonal: api -> composition -> adapters -> services -> domain)
frontend/   React 19 + TypeScript + Vite
sources/    reference material for research write-ups
drafts/     working drafts
published/  approved write-ups (write-protected for Claude via .claude/settings.json)
```

See `backend/README.md` for the backend's layering rules.
