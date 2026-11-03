# Handoff: feat/capture-ak-scoping-api

**For:** Arun Das · **From:** Mahamudul Hasan · **Date:** 3 Nov 2026
**Branch:** `feat/capture-ak-scoping-api` (all work pushed; last commit `3f92e2b`)

The backend for the Nov 2 demo is done and tested.
What is left is mostly frontend: the Capture, Ask, Admin and Findings screens on top of the API below.

---

## 1. What changed after the Nov 2 sync

We now use **one admin Agent Memory key** for everyone.
Users never hold Agent Memory keys.

**Our backend is the governance layer.** A SQLite table records which scopes each user may read or write.
Every Agent Memory read passes a `lens`, and every write passes `scopes`, taken from that table.

We tested this live with the admin key:

- A recall with `lens=[a]` never returned a fact stored in scope `b`.
- A recall with **no lens returns everything**, so the backend never calls recall without one.
- A lens matches its **exact path only**, not the paths below it.
- Entity reads and entity search take **no lens**, so `/graph` and `/documents` are admin-only.

Users sign in with **Microsoft Entra ID SSO**, the same flow as membrain.
On first sign-in a user gets:

| Scope | Access | Layer |
|---|---|---|
| `org/spreetail/user/<firstname>_<lastname>` (created in Agent Memory if missing) | read + write | personal |
| `org/spreetail` | read | org |

Teams (for example `org/spreetail/team/ops`) are granted by an admin.

---

## 2. Run it

```bash
git checkout feat/capture-ak-scoping-api && git pull
make up          # frontend http://localhost:5174, API http://localhost:8000, docs /docs
make check       # lint + types; make test for tests
```

Ask Mahamudul for the `.env` values. The settings are:

| Setting | Purpose |
|---|---|
| `AGENT_MEMORY_ENDPOINT`, `AGENT_MEMORY_CONTEXT`, `AGENT_MEMORY_API_KEY` | The one admin key |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` | Entra SSO (membrain's app registration) |
| `SESSION_SECRET_KEY` | Signs the session cookie |
| `ADMIN_EMAILS` | Comma-separated admin emails |
| `DEV_LOGIN_ENABLED` | `true` shows an email-only login for testing several users. **Set `false` for the demo.** |
| `ORG_SCOPE`, `USER_SCOPE_ROOT` | Default `org/spreetail` and `org/spreetail/user` |

The Entra app registration already accepts `http://localhost:5174/api/v1/auth/callback`; SSO sign-in was confirmed on 2 Nov.

---

## 3. Frontend rules

- Call the API with **relative `/api/...` paths** through `src/api/` (Vite proxies `/api` to the backend).
- Auth is a **session cookie**. There are no tokens to store, and same-origin `fetch` sends the cookie automatically.
- Any **401** means signed out: show the login screen.
- **403** means the user lacks a grant or is not an admin: show the message from `detail`.
- `src/api/client.ts` has `apiGet` and `apiPost`; `src/api/auth.ts` has `getMe`, `getAuthConfig`, `devLogin` and `logout`.
- `App.tsx` already shows `Login` until `/auth/me` succeeds, then `Account` (name, admin badge, scopes).
- Build the new screens behind that.

---

## 4. API reference

Every endpoint except health, findings and the auth login routes needs a session.

### Auth
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/auth/config` | `{sso_enabled, dev_login_enabled}`: which login to show |
| GET | `/api/v1/auth/login` | Full-page navigation (`window.location`), not fetch. Redirects to Entra. |
| GET | `/api/v1/auth/callback` | Entra returns here; the backend sets the cookie and redirects to the frontend |
| POST | `/api/v1/auth/dev-login` | `{email, name}`. Only when dev login is on. |
| POST | `/api/v1/auth/logout` | 204 |
| GET | `/api/v1/auth/me` | `{email, name, is_admin, grants: [{scope_path, access, layer}]}` |

### Capture (writes)
`POST /api/v1/capture/preview` is a dry run: nothing is saved for text.
```json
{
  "scope": null,
  "input_type": "text",
  "config": { "mode": "triples", "memory_category": "knowledge" },
  "content": "Northwind Traders ships furniture to the Dallas warehouse.",
  "file_name": null
}
```
- `scope: null` means the user's personal scope. Any other scope must be one the user can **write** (else 403).
- For a document, send `input_type: "document"`, the file **base64** in `content`, and `file_name`.
- A document is uploaded once during preview, because Agent Memory has no dry run for files. Poll its status.
- Documents over 2000 words are previewed from the first 500 words (`truncated: true`).

The response:
```json
{
  "preview_id": "prev_…",
  "scope": "org/spreetail/user/arun_das",
  "extracted": [{ "id": "e1", "fact": "Northwind Traders · ships_to → Dallas warehouse", "type": "knowledge", "source": "text", "note": null, "storable": true }],
  "stats": { "total": 1, "uncertain": 0, "corrections": 0 },
  "truncated": false, "truncated_reason": null, "doc_id": null, "corrections": [], "trace_id": "t-…"
}
```

`POST /api/v1/capture/store`:
```json
{ "preview_id": "prev_…", "scope": null, "kept": ["e1"], "config": { "mode": "triples", "memory_category": "knowledge" }, "trace_tags": null }
```
- Mode `triples` stores **only the kept facts**.
- Mode `full` re-extracts the whole source and stores everything; `kept` is ignored.
- `storable: false` means Agent Memory's preview did not say which entity the fact belongs to. Only mode `full` can save it.
- A `preview_id` lives in backend memory: it is lost on restart (404 means preview again), and only its creator can store it.

`GET /api/v1/capture/document/{doc_id}/status` returns `{doc_id, status, finished, chunks, keywords, created_at, updated_at, message}`.
Poll it every 2 seconds until `finished`. Only the uploader (or an admin) can see it.

### Ask (reads)
`GET /api/v1/ask?q=…` searches every scope the user may read, one lens per scope, in parallel.

| Parameter | Use |
|---|---|
| `q` | The question (required) |
| `scope` | Repeatable or comma-separated. Narrows to some readable scopes (403 if not readable). |
| `as_user` | **Admin only.** Repeatable or comma-separated emails: ask as those users, for example two at once. |

The response:
```json
{
  "q": "Northwind Traders", "scopes": ["org/spreetail", "org/spreetail/user/arun_das"], "answered_at": "…",
  "layers": [
    { "layer": "org", "area": "org/spreetail", "owner": null, "facts": [], "error": null },
    { "layer": "personal", "area": "org/spreetail/user/arun_das", "owner": "Arun Das",
      "facts": [{ "fact": "…", "source": { "kind": "memory", "hit_kind": "attribute", "hit_id": "…", "title": null, "date": null, "text": "…", "score": 0.82 } }],
      "error": null }
  ],
  "metadata": { "total_facts": 1, "resolution_tier": "escalated", "latency_ms": 11000, "include_inferred": false, "trace_ids": [] },
  "trace_id": "t-…"
}
```
- `score` is the **recall rank score, not trust**. Label it "match score".
- A layer with `error` set failed on its own. Show the other layers.
- Ask takes **10–20 seconds**, so it needs a loading state.

### Admin (admin session only)
| Method | Path | Body or parameters |
|---|---|---|
| GET | `/api/v1/admin/users` | Users with their grants |
| POST | `/api/v1/admin/users/{email}/grants` | `{"scope_path": "org/spreetail/team/ops", "access": "read", "layer": "team"}`. `name` is needed only for a user who never signed in. 201. |
| DELETE | `/api/v1/admin/users/{email}/grants?scope_path=…` | 204. Returns 404 if the user does not hold that grant. |
| GET | `/api/v1/admin/scopes?prefix=org/spreetail/team` | Registered scopes |
| POST | `/api/v1/admin/scopes` | `{"path": "org/spreetail/team/eng"}` registers a new scope |

Scopes must sit under `org/spreetail`.
**A grant registers any new path**, so a typo silently creates an empty scope: pick paths from `GET /admin/scopes` in the UI, never free text.

### Findings (static, no session)
`GET /api/v1/findings/tests` (153 claims), `/capabilities` and `/gaps` (40 rows).
Each file carries `source` and `checked`.

### Admin-only, lens-free
`/api/v1/graph/*` and `/api/v1/documents*` see every scope through the admin key, so they are admin-only.
Use them for an admin Explorer view only.

### Removed
`/api/v1/scopes/list`, `/scopes/switch` and `/scopes/active` are gone.
`/auth/me` returns the user's grants, and admins manage them.

---

## 5. What is left for you

In priority order for the demo:

1. **Capture screen**
   - text: preview, a facts table with checkboxes (disable `storable: false`), store, then show `created_facts` and `history`;
   - document: base64 upload, the truncation warning, and polling the status.
2. **Ask screen**: the question box, results grouped by layer (org, team, personal) with owner names, a source drawer (`hit_kind`, `text`, match `score`), and a loading state.
3. **Admin screen** (when `is_admin`):
   - users and their grants;
   - grant and revoke with a scope picker from `/admin/scopes` and a read/write choice;
   - register a team scope;
   - "ask as" one or two users (`as_user`).
4. **Findings screen**: three tabs over `/findings/*`.
5. **Navigation**: Capture, Ask, Admin (admins only), Findings, and Sign out.

**The old frontend prototype (`Capture.tsx`, `Explorer.tsx`, `GraphView.tsx` and `src/api/capture.ts`, `documents.ts`, `graph.ts`) is not on this branch.**
It was written against the old API and also fails `tsc`.
It sits uncommitted in Mahamudul's working copy; reuse its UI, but rebuild its API calls on this contract.

---

## 6. Demo script (role play)

Turn dev login on only for rehearsal; use real SSO in the demo.

1. **Arun** stores "Northwind Traders ships furniture to the Dallas warehouse." through preview, then store.
2. **Arun** asks "Northwind Traders": the fact is in his personal layer.
3. **Vidyul** asks the same: nothing.
4. **Admin** grants Vidyul read on `org/spreetail/user/arun_das`.
5. **Vidyul** asks again: Arun's fact appears.
6. **Admin** asks as Arun + Vidyul: one view across both.
7. **Admin** revokes: Vidyul's next ask shows nothing.

`docker compose logs -f backend | grep -E "\[AUTH\]|\[CAPTURE\]|\[ASK\]|\[ADMIN\]"` shows who did what, live.

---

## 7. Known limits

- **There is no per-fact confidence or token cost.** Agent Memory reports neither, so the API has neither.
- **Ask sources have no title, location or date** (recall hits carry none).
- **Preview attributes often have no entity link**, so they are `storable: false`. Keep demo sentences to one company each.
- **The personal scope comes from the name.** Two emails with the same name share a scope, and a different spelling gives a different scope.
- **Scope deletion does not purge data.** Agent Memory's `scopes.forget` fails with "Connection failed"; `scopes.delete` works but only tombstones.
- **Previews live in memory**, so they are lost on restart and won't work across several backend instances.
- **SQLite file:** `backend/data/user_scopes.db` (gitignored). Deleting it resets all grants.
- **`make check` fails on the frontend** only because of the untracked prototype files above. Without them it is clean.

## 8. Where things live

| Area | File |
|---|---|
| Grants table (SQLite) | `backend/app/adapters/sqlite/user_scopes.py` |
| Default scopes, write/read rules | `backend/app/services/access.py` |
| SSO and session | `backend/app/api/v1/endpoints/auth.py`, `backend/app/core/oauth.py` |
| Capture flow | `backend/app/services/capture_flow.py`, `endpoints/capture.py` |
| Ask flow | `backend/app/services/ask_flow.py`, `endpoints/ask.py` |
| Admin | `backend/app/api/v1/endpoints/admin.py` |
| Agent Memory calls | `backend/app/adapters/agent_memory/` |
| Login UI | `frontend/src/components/Login.tsx`, `Account.tsx`, `App.tsx` |
| Decisions and status | `progress.md` |

**Tests:** 137 backend tests, 98% coverage (`make test`).
**Questions:** Mahamudul.
