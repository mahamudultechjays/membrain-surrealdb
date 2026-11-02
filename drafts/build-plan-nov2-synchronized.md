# Build Plan: Nov 2, 2026 — Synchronized FE/BE

**Standup Date:** Nov 2, 10:30 IST  
**Target Deliverable:** 3:30–4:30 PM IST (by EOD)  
**Team:** Arun (FE), Mahamudul (BE), Binu (Lead)  

---

## Overview

Based on standup (10:30 AM) and follow-up with Arun (12:02 PM), we are building **four core screens**:

1. **Capture** — text/document input with preview, config selection, and storage *(chat deferred)*
2. **Ask** — search with layer-grouped results and source attribution
3. **Scoping/Access Control** — demonstrate scope isolation across users (NEW)
4. **Findings** — test results, capability map, and gaps catalogue

Both teams work in parallel to the **API contract** defined in Phase 0. This ensures FE can mock and BE can iterate independently.

**Deferred (Later):**
- Chat import tab (skip for MVP)
- Preferences editing (show read-only only)
- Mechanisms discovery (if time allows)

---

## Phase 0: API Contracts (Shared Interface)

### Agent Memory Constraints (checked 2026-11-02)

These limits come from the Agent Memory docs and the pinned `surrealdb-memory` Python SDK.
The contracts below are written to fit them.

| Constraint | Effect on our API | Source |
|---|---|---|
| `remember()` accepts only `infer` = `full`, `triples`, `preview` or `none`. | Our `config.mode` uses `full` or `triples`; preview always calls `infer="preview"`. | https://surrealdb.com/docs/agent-memory/ingest/experiential/remember |
| `documents.upload()` has no `infer` argument and no dry run. | A document preview uploads the file once, then previews its extracted text with `remember(infer="preview")`. | SDK `_namespaces/documents.py` `upload()` |
| A preview returns no id (`RememberResponse.preview` is a bool). | The backend creates `preview_id` and holds the preview in an in-process cache. Restarting the backend loses it, and it works only on one instance. | SDK `_models/memory.py` `RememberResponse` |
| The extraction result has no per-fact confidence. | No `confidence` field in the preview, and no `high_confidence` stat. | SDK `_models/memory.py` `ExtractionResult` |
| `recall()` has no `scopes` or `limit`. It takes `lens` (read scope, DNF) and `k` (default 10, max 50). | Our `/api/v1/ask?scope=` maps to `lens`; the result count maps to `k`. | https://surrealdb.com/docs/agent-memory/retrieve/recall |
| A recall hit carries only `id`, `score`, `source` (record kind) and `text`. The docs say `/query` exposes no per-hit trust. | No `source.location`, `source.quote` or `source.trust` in Ask. `score` is a rank score, not trust. | Recall docs above; SDK `_models/memory.py` `RecallHit` |
| No response reports token cost. | No `cost_tokens` or `query_cost_tokens` fields. | SDK `_models/memory.py` |

### Capture APIs

#### POST /api/v1/capture/preview
Extracts facts from input without writing. Returns preview for user approval.

**Request:**
```json
{
  "scope": "org/user/u-0001",
  "input_type": "text" | "document",
  "config": {
    "mode": "triples" | "full",
    "memory_category": "identity" | "knowledge" | "context"
  },
  "content": "string or base64 bytes",
  "file_name": "optional.pdf"
}
```

`config.mode` decides what `/capture/store` writes later. Preview always calls `remember(infer="preview")`.
- `triples` (default): write only the kept facts with `remember(infer="triples")`.
- `full`: rerun full extraction on the source text with `remember(infer="full")`.

**Response:**
```json
{
  "preview_id": "prev_abc123",
  "scope": "org/user/u-0001",
  "extracted": [
    {
      "id": "e1",
      "fact": "acme logistics · lead_time_days = 18",
      "type": "knowledge",
      "source": "text",
      "note": "correction: was 10",
      "storable": true
    }
  ],
  "stats": { "total": 7, "uncertain": 2, "corrections": 1 },
  "truncated": false,
  "truncated_reason": "Large document: preview shows first 500 words only",
  "doc_id": null,
  "trace_id": "d-abc123"
}
```

- `preview_id` is created by our backend, not Agent Memory. The backend keeps recent previews in memory, so an id expires on restart or after newer previews push it out.
- `storable` is false when Agent Memory doesn't link the attribute to an entity. That fact can be stored only with mode `full`.
- `stats.uncertain` counts facts Agent Memory raised an uncertainty about. There is no confidence score to count.
- `doc_id` is set for document input, because the file is uploaded during preview.

**Note:** Documents > 2000 words will show preview of first ~500 words only. UI should display truncation warning and suggest text extraction for large files.

---

#### POST /api/v1/capture/store
Writes selected facts to Agent Memory and logs to the console.

**Request:**
```json
{
  "preview_id": "prev_abc123",
  "scope": "org/user/u-0001",
  "kept": ["e1", "e3", "e5"],
  "config": { "mode": "triples", "memory_category": "knowledge" },
  "trace_tags": { "session_id": "cc-abc", "source": "plugin" }
}
```

Returns 404 when `preview_id` is unknown or expired; the UI should ask the user to preview again.

**Response:**
```json
{
  "stored_id": "store_def456",
  "written": 3,
  "created_facts": [
    { "entity": "acme logistics", "key": "lead_time_days", "value": "18", "id": "fact_1" }
  ],
  "history": [
    { "fact_id": "fact_1", "old_value": "10", "new_value": "18", "changed_at": "2026-11-02T10:06:00Z" }
  ],
  "trace_id": "d-abc123"
}
```

---

#### GET /api/v1/capture/document/{doc_id}/status
Polls document processing status (async upload).

**Response:**
```json
{
  "doc_id": "doc_7f3a",
  "status": "queued" | "processing" | "ready" | "facts_readable",
  "chunks": 0,
  "keywords": 0,
  "created_at": "2026-11-02T10:00:00Z",
  "updated_at": "2026-11-02T10:15:00Z",
  "message": "Waiting in Agent Memory queue..."
}
```

---

### Ask API

#### GET /api/v1/ask
Retrieves facts grouped by layer (org/team/personal).

**Request:**
```
GET /api/v1/ask?q=What+do+we+know+about+Acme&scope=org/user/u-0001&include_inferred=false
```

Our `scope` parameter stays. The backend maps each readable layer to an Agent Memory `lens`.

**Response:**
```json
{
  "q": "What do we know about Acme?",
  "answered_at": "2026-11-02T10:20:00Z",
  "layers": [
    {
      "layer": "org",
      "area": "org",
      "facts": [
        {
          "fact": "returns policy · window_days = 30",
          "source": {
            "kind": "document",
            "hit_kind": "chunk",
            "hit_id": "chunk:abc123",
            "text": "Customers may return items within 30 days of delivery.",
            "score": 0.82,
            "title": null,
            "date": null
          }
        }
      ]
    },
    {
      "layer": "team",
      "area": "org/team/ops",
      "facts": []
    },
    {
      "layer": "personal",
      "area": "org/user/u-0001",
      "facts": []
    }
  ],
  "metadata": {
    "total_facts": 5,
    "resolution_tier": "hybrid",
    "latency_ms": 812
  }
}
```

- `hit_kind` is Agent Memory's record kind: `entity`, `attribute`, `action`, `memory_chunk`, `chunk` or `section`.
- `text` is the hit's own text, not a verified quote from the source document.
- `score` is the recall rank score. It is not a trust value, so the UI must not label it as trust.
- `title` and `date` stay null, because recall hits don't carry them. Filling them needs a separate read per hit, which is a later item.

---

### Findings APIs

#### GET /api/v1/findings/tests
Static test catalogue.

**Response:**
```json
{
  "tests": [
    {
      "id": "F1",
      "requirement": "C2",
      "name": "Assistant words never become facts",
      "status": "pass" | "fail" | "open",
      "how": "Assistant turns sent with infer=\"none\"",
      "native_result": "fail",
      "membrain_result": "pass",
      "mark": "workaround"
    }
  ]
}
```

#### GET /api/v1/findings/capabilities
Static capability map.

**Response:**
```json
{
  "capabilities": [
    {
      "area": "Ingest",
      "name": "Preview extraction",
      "call": "remember(infer=\"preview\")",
      "mark": "native",
      "screen": "capture"
    }
  ]
}
```

#### GET /api/v1/findings/gaps
Static gaps list.

**Response:**
```json
{
  "gaps": [
    {
      "id": "SD-1",
      "name": "Chat correction loses the value",
      "status": "Broken",
      "priority": "P0",
      "membrain_workaround": "Write corrections as triples ourselves"
    }
  ]
}
```

---

### Scoping/Access Control API (NEW)

#### GET /api/v1/scopes/list
List all available scopes for demonstration.

**Response:**
```json
{
  "scopes": [
    {
      "id": "org/user/u-0001",
      "name": "Priya",
      "type": "user",
      "api_key": "sk_test_priya_xxx"
    },
    {
      "id": "org/user/u-0002",
      "name": "Arun",
      "type": "user",
      "api_key": "sk_test_arun_xxx"
    },
    {
      "id": "org/user/u-0003",
      "name": "Deena",
      "type": "user",
      "api_key": "sk_test_deena_xxx"
    }
  ]
}
```

#### POST /api/v1/scopes/switch
Switch active scope (for demo: simulate different users).

**Request:**
```json
{
  "scopes": ["org/user/u-0001", "org/user/u-0003"],
  "api_keys": ["sk_test_priya_xxx", "sk_test_deena_xxx"]
}
```

**Response:**
```json
{
  "active_scopes": ["org/user/u-0001", "org/user/u-0003"],
  "message": "Scope context switched (Priya + Deena)"
}
```

**Demo Flow:**
1. Capture as Priya → stores fact in `org/user/u-0001`
2. Ask as Priya → ✓ retrieves (owns scope)
3. Ask as Arun → ✗ retrieves nothing (no read grant)
4. Switch to Priya+Deena → ✓ both can see

---

## Frontend Build Plan (Arun)

### F1: Infrastructure & Setup (NOW)
- [ ] Verify API schema with Mahamudul
- [ ] Set up API client in `src/api/` (axios/fetch)
- [ ] Create environment config (API base URL)
- [ ] Stub auth token handling

**Blocking:** BE `/health` endpoint

---

### F2: Capture Screen (NOW – 11:30 AM)

#### F2.1: Layout & Tabs
- [ ] Create `Capture.tsx` with tabs: Text | Document | Chat
- [ ] Stepper: Input → Preview → Stored

#### F2.2: Text Tab
- [ ] Textarea + scope dropdown
- [ ] Config: mode (triples/full) + category (identity/knowledge/context)
- [ ] Disable the checkbox of a fact with `storable: false` unless mode is `full`
- [ ] On a 404 from store, show "Preview expired; run preview again"
- [ ] "Preview" → `POST /api/v1/capture/preview`
- [ ] Facts table with checkboxes
- [ ] "Store" → `POST /api/v1/capture/store`
- [ ] Show created facts + history

#### F2.3: Document Tab
- [ ] File input + drag-drop
- [ ] "Upload" → `POST /api/v1/capture/preview`
- [ ] **Poll `GET /api/v1/capture/document/{id}/status` every 2s**
- [ ] Show stepper: queued → processing → ready → facts_readable
- [ ] **Add truncation warning:** "Documents > 2000 words show first ~500 words in preview"
- [ ] Suggest: "For large files, extract text and use text tab"

**Dependency:** BE `/capture/preview` & `/capture/store` by 11:30 AM

**Note:** Chat import deferred to later release.

---

### F3: Ask Screen (NOW – 1:30 PM)
- [ ] Question input + quick-pick buttons
- [ ] `GET /api/v1/ask?q=...&scope=...`
- [ ] Group by layer (Org | Team | Personal)
- [ ] Source drawer per fact: show `hit_kind`, `text` and `score` (label it "match score", not trust)
- [ ] Checkboxes: "Show inferred", "Show context block"

**Dependency:** BE `/ask` endpoint by 1:30 PM

---

### F3.5: Scoping/Access Control Screen (1:30 – 2:30 PM)

#### Scope Selector + Demo
- [ ] Dropdown: Select user (Priya, Arun, Deena)
- [ ] Multi-select: Combine scopes (e.g., Priya + Deena)
- [ ] "Switch scope" button → calls `POST /api/v1/scopes/switch`
- [ ] Show active scope/scopes at top

#### Demo Flow
- [ ] **Step 1:** Capture text as "Priya" → store fact
- [ ] **Step 2:** Ask as "Priya" → ✓ retrieves own data
- [ ] **Step 3:** Ask as "Arun" → ✗ sees nothing (scope isolation)
- [ ] **Step 4:** Ask as "Priya + Deena" → both see Priya's data
- [ ] Display: "✓ Scope isolation working" or "✗ Cross-scope leak detected"

**Dependency:** BE `/scopes/list` & `/scopes/switch` by 2:30 PM

---

### F4: Findings Screen (2:30 – 3:00 PM)
- [ ] 4 tabs: Tests | Capabilities | Gaps | Test Data
- [ ] `GET /api/v1/findings/{tests,capabilities,gaps}`
- [ ] Tables + filter pills
- [ ] "Wipe test data" button

**Dependency:** BE `/findings/*` endpoints by 3:00 PM

---

### F5: Navigation & Polish
- [ ] Top nav (Capture | Ask | Findings)
- [ ] Persona selector (demo)
- [ ] Error toasts + loading spinners
- [ ] Responsive layout

---

## Backend Build Plan (Mahamudul)

### B1: Infrastructure & Setup (NOW – 10:00 AM)
- [ ] Add auth middleware (Bearer token → user context)
- [ ] Create `/health` endpoint
- [ ] Load API keys from .env
- [ ] Set up console logger with prefixes
- [ ] Dependency injection for Agent Memory, scope context

**Files to create:**
- `backend/app/api/middleware.py` (new - auth + scope context)
- `backend/app/services/logger.py` (new - console logger)
- `backend/app/services/scopes.py` (new - scope manager)
- `backend/app/api/v1/endpoints/capture.py` (stub)
- `backend/app/api/v1/endpoints/ask.py` (stub)
- `backend/app/api/v1/endpoints/findings.py` (stub)
- `backend/app/api/v1/endpoints/scopes.py` (stub)

---

### B2: Configuration & Logging (NOW – 10:30 AM)

**API Key Configuration (.env - Demo Only):**
```bash
# Test API keys stored in .env for demo (not production)
MEMBRAIN_USER_PRIYA_KEY=sk_test_priya_f3a9c1d2e5
MEMBRAIN_USER_ARUN_KEY=sk_test_arun_b2e7f4a1c9
MEMBRAIN_USER_DEENA_KEY=sk_test_deena_d8c3e9f2a4
```

**Logging (Console to stdout - No persistence):**
- Log every capture/preview call with: scope, input_type, config, extracted_count
- Log every ask call with: question, scope, facts_found, latency_ms
- Log every scope switch with: from_scopes, to_scopes, message
- Use structured logging: `[CAPTURE] [scope=org/user/u-0001] extracted=7`
- Agent Memory reports no token cost, so no cost field is logged.

- [ ] Load API keys from .env
- [ ] Set up console logger with prefix (CAPTURE, ASK, SCOPING)
- [ ] Include operation metadata in all API responses

---

### B3: Capture Endpoints (NOW – 11:30 AM)

#### B3.1: POST /api/v1/capture/preview
- [ ] Validate scope (user can write)
- [ ] Route by input_type → Agent Memory call
  - text: `remember(text, infer="preview", scopes=[scope])`
  - document: `documents.upload(file, scopes=[scope])` (no `infer` argument), then `remember(first_words, infer="preview", scopes=[scope])`
  - chat: deferred
- [ ] Extract facts → frontend schema (no confidence; mark `storable`)
- [ ] Create `preview_id` and keep the preview in the in-process cache
- [ ] Log to console
- [ ] Return 200 + preview

**Subtasks:**
- [ ] Create `backend/app/adapters/agent_memory/capture.py`
- [ ] Build fact mapper
- [ ] Handle errors (400, 429, 500)
- [ ] Unit tests with mocked SDK

---

#### B3.2: POST /api/v1/capture/store
- [ ] Validate scope + preview_id (404 when not in the cache)
- [ ] Mode `triples`: build triples from kept facts, call `remember(infer="triples", triples=[...], scopes=[scope], memory_category=...)`
- [ ] Mode `full`: call `remember(text, infer="full", scopes=[scope], memory_category=...)`
- [ ] Read back with `entities.get()` per fact
- [ ] Build history
- [ ] Log to console
- [ ] Return 200 + stored response

**Subtasks:**
- [ ] Build triple builder
- [ ] Build history mapper
- [ ] Unit tests

---

#### B3.3: GET /api/v1/capture/document/{doc_id}/status
- [ ] Call Agent Memory: `documents.get(doc_id)`
- [ ] Map status → enum (queued/processing/ready/facts_readable)
- [ ] Return 200 + status

---

### B4: Ask Endpoint (NOW – 2:00 PM)

#### B4.1: GET /api/v1/ask
- [ ] Parse `q`, `scope`, `include_inferred`
- [ ] Build read lens from user scope
- [ ] Parallel recalls per layer (org, team, personal)
  - `recall(q, lens=[["org"]], k=20)`
  - `recall(q, lens=[["org/team/ops"]], k=10)` (if user can read)
  - `recall(q, lens=[["org/user/<id>"]], k=10)` (if user can read)
  - `k` is capped at 50
- [ ] Map each hit to `source`: `hit_kind`, `hit_id`, `text`, `score`
  - Use `score` as a rank score only; do not call it trust
  - Leave `title` and `date` null; per-hit lookups are deferred
- [ ] Group by layer → build source drawers
- [ ] Log to console
- [ ] Return 200 + answer

**Subtasks:**
- [ ] Create `backend/app/adapters/agent_memory/ask.py`
- [ ] Build source mapper
- [ ] Parallel execution (asyncio)
- [ ] Error handling (403, 429)
- [ ] Unit tests

---

### B5: Scoping Endpoints (1:30 – 2:30 PM)

#### B5.1: GET /api/v1/scopes/list
- [ ] Load scope definitions from .env or hardcoded config
- [ ] Return list: Priya, Arun, Deena (with API keys)
- [ ] Return 200 + scopes array

#### B5.2: POST /api/v1/scopes/switch
- [ ] Accept array of scope IDs to switch to
- [ ] Load corresponding API keys from .env
- [ ] Store in request context (for next requests)
- [ ] Return 200 + confirmation message

**Subtasks:**
- [ ] Create scope manager service
- [ ] Load .env API keys into scope definitions
- [ ] Unit tests

---

### B6: Findings Endpoints (2:30 – 3:00 PM)

#### B6.1–B6.3: GET /api/v1/findings/{tests,capabilities,gaps}
- [ ] Load static JSON from `backend/app/data/findings/`
- [ ] Return 200 + data

**Subtasks:**
- [ ] Extract data from mockup HTML
- [ ] Create JSON files:
  - `backend/app/data/findings/tests.json`
  - `backend/app/data/findings/capabilities.json`
  - `backend/app/data/findings/gaps.json`
- [ ] Unit tests

---

### B7: Scope & Access Control (Throughout)

#### B7.1: Scope Manager Service
- [ ] Load API keys from .env by scope
- [ ] Helper: `load_api_keys()` → {org/user/u-0001: "sk_test_priya_...", ...}
- [ ] Helper: `get_api_key(scope)` → returns API key for scope
- [ ] Hardcode scope grants for demo (Priya can access org/user/u-0001, etc.)

#### B7.2: Middleware Integration
- [ ] Extract scope from request context (from FE scope selector)
- [ ] Load API key for scope
- [ ] Pass to Agent Memory SDK calls

#### B7.3: Endpoint Enforcement
- [ ] Capture: Validate scope is valid (in .env keys)
- [ ] Ask: Validate scope is valid (in .env keys)
- [ ] Findings: Public (no scope check)
- [ ] Scopes: Public (list available scopes)

**Subtasks:**
- [ ] Create `backend/app/services/scopes.py`
- [ ] Hardcode test scope grants in service (for demo)

---

## Synchronization Checkpoints

| Time | FE Work | BE Work | Sync Action |
|------|---------|---------|------------|
| **10:30 AM** | F1: Setup | B1: Setup + console logging | API schemas finalized ✓ |
| **11:30 AM** | F2: Capture (text tab) | B3: `/capture/preview` + `/capture/store` | **Capture E2E test** |
| **1:30 PM** | F2.3: Doc tab + F3: Ask | B4: `/api/v1/ask` + B5: `/scopes/list` | **SYNC BEFORE LUNCH** ← Review progress, plan afternoon |
| **2:30 PM** | F3.5: Scoping demo | B5: `/scopes/switch` | Scoping E2E test |
| **3:00 PM** | F4: Findings | B6: `/findings/*` | Findings E2E test |
| **3:30–4:30 PM** | Integration testing | Bugfixes | **DEMO Ready** |

---

## Risk Mitigation

| Risk | Mitigation |
|-----|-----------|
| Document upload stalls | Timeout (10 min) + "Queued longer than expected" message |
| Agent Memory 429 | Retry with exponential backoff |
| FE waits for BE | Use mock API early; code to schema first |
| Scope grants undefined | Hardcode test grants in `conftest.py` |
| Token expiry | Store refresh token; auto-refresh before 401 |

---

## Deliverable Checklist (EOD)

### Must Have (EOD Deliverable)
- [ ] **Capture screen:** Text tab (input→preview→store) ✓
- [ ] **Capture screen:** Document tab with polling + truncation warning ✓
- [ ] **Ask screen:** Question + layer-grouped results ✓
- [ ] **Scoping screen:** User/scope selector + demo isolation ✓
- [ ] **Findings screen:** Tests, capabilities, gaps tabs ✓
- [ ] Config selector on Capture (mode, category) ✓
- [ ] All API endpoints respond to correct schema ✓
- [ ] Console logging for operations (no persistence needed) ✓
- [ ] API keys loaded from .env ✓
- [ ] Scope isolation demonstrated (Priya ≠ Arun data) ✓
- [ ] No console errors ✓
- [ ] All tests pass ✓

### Nice to Have (Later Release)
- [ ] Chat import tab (deferred)
- [ ] Preferences editing (show read-only only)
- [ ] Mechanisms discovery (if time)
- [ ] Source drawer with document title, location and date (needs a per-hit read, such as `documents.chunks(doc_id, page=...)`)
- [ ] History accordion with version timeline

---

## Changes Needed on `feat/capture-ak-scoping-api` (from the Nov 2 review)

The branch already calls Agent Memory correctly. These changes bring its API in line with the contracts above.

- [ ] `capture_flow.StoreMode` and `schemas/capture.py`: rename modes `infer_text` → `triples` and `infer_full` → `full`; default `triples`. Update messages that name the old values.
- [ ] `schemas/capture.py`: remove `confidence` from extracted facts and `cost_tokens` from the preview response.
- [ ] `schemas/capture.py` and `capture_flow.Preview`: rename stat `high_confidence` → `uncertain`, counting facts with an uncertainty note.
- [ ] `schemas/ask.py` and `endpoints/ask.py`: rename `FactSource.trust` → `score`, rename `quote` → `text`, drop `location`, and drop `metadata.query_cost_tokens`.
- [ ] Update tests and `capabilities.json` entries that use the old names.
- [ ] Run `make check` and report the result.

---

**Ready to split into parallel workstreams at 10:30 AM standup.**
