# Membrain SurrealDB POC

Proof of concept evaluating SurrealDB Agent Memory for Membrain. React + Vite frontend and FastAPI backend, running in Docker. Agent Memory itself is hosted on SurrealDB Cloud and reached over HTTPS.

## Prerequisites

- Docker Desktop (Compose v2.24+)
- `make`
- A SurrealDB Cloud Agent Memory Context and API key

No local Python or Node install is needed; every command runs in a container.

## Quick start

```bash
make up          # creates .env, builds images, starts everything, waits for health
```

Then fill in `AGENT_MEMORY_ENDPOINT`, `AGENT_MEMORY_CONTEXT` and `AGENT_MEMORY_API_KEY` in `.env` and run `make restart`. Until then the app runs and reports Agent Memory as not configured.

| Service | URL |
|---|---|
| Frontend (Vite, HMR) | http://localhost:5174 |
| Backend API docs | http://localhost:8000/docs |

Edits under `backend/` and `frontend/` reload automatically. Host ports are set in `.env`; the frontend defaults to 5174 so this stack runs alongside membrain's.

## Common commands

```bash
make help        # list everything
make logs s=backend
make check       # lint + type-check + tests, backend and frontend
make format
make prod        # production-shaped images (nginx on :8080)
make down        # stop (data kept)
make clean       # stop and remove volumes
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
