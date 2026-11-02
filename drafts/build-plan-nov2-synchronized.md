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

### Capture APIs

#### POST /api/v1/capture/preview
Extracts facts from input without writing. Returns preview for user approval.

**Request:**
```json
{
  "scope": "org/user/u-0001",
  "input_type": "text" | "document",
  "config": {
    "mode": "infer_full" | "infer_text",
    "memory_category": "identity" | "knowledge" | "context"
  },
  "content": "string or base64 bytes",
  "file_name": "optional.pdf"
}
```

**Response:**
```json
{
  "preview_id": "prev_abc123",
  "extracted": [
    {
      "id": "e1",
      "fact": "acme logistics · lead_time_days = 18",
      "type": "knowledge",
      "confidence": 0.9,
      "source": "text chunk 1-50",
      "note": "correction: was 10"
    }
  ],
  "stats": { "total": 7, "high_confidence": 5, "corrections": 1 },
  "truncated": false,
  "truncated_reason": "Large document: preview shows first 500 words only",
  "cost_tokens": 4200
}
```

**Note:** Documents > 2000 words will show preview of first ~500 words only. UI should display truncation warning and suggest text extraction for large files.

---

#### POST /api/v1/capture/store
Writes selected facts to Agent Memory and logs to SQLite.

**Request:**
```json
{
  "preview_id": "prev_abc123",
  "scope": "org/user/u-0001",
  "kept": ["e1", "e3", "e5"],
  "config": { "mode": "infer_text", "memory_category": "knowledge" },
  "trace_tags": { "session_id": "cc-abc", "source": "plugin" }
}
```

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
            "title": "returns-policy-2026.pdf",
            "location": "§2 · chunk 3 of 14",
            "quote": "Customers may return items within 30 days of delivery.",
            "date": "2026-10-01",
            "trust": 0.8
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
    "latency_ms": 812,
    "query_cost_tokens": 1100
  }
}
```

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
- [ ] Config: mode (infer_full/infer_text) + category (identity/knowledge/context)
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
- [ ] Source drawer per fact
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
- Log every capture/preview call with: scope, input_type, config, extracted_count, cost_tokens
- Log every ask call with: question, scope, facts_found, latency_ms, cost_tokens
- Log every scope switch with: from_scopes, to_scopes, message
- Use structured logging: `[CAPTURE] [scope=org/user/u-0001] extracted=7 cost=4200`

- [ ] Load API keys from .env
- [ ] Set up console logger with prefix (CAPTURE, ASK, SCOPING)
- [ ] Include operation metadata in all API responses

---

### B3: Capture Endpoints (NOW – 11:30 AM)

#### B3.1: POST /api/v1/capture/preview
- [ ] Validate scope (user can write)
- [ ] Route by input_type → Agent Memory call
  - text: `remember(text, infer="preview", memory_category=...)`
  - document: `documents.upload(file, scopes=[scope], infer="preview")`
  - chat: `remember_many(chats, extract="per_message")`
- [ ] Extract facts → frontend schema
- [ ] Log to SQLite
- [ ] Return 200 + preview

**Subtasks:**
- [ ] Create `backend/app/adapters/agent_memory/capture.py`
- [ ] Build fact mapper
- [ ] Handle errors (400, 429, 500)
- [ ] Unit tests with mocked SDK

---

#### B3.2: POST /api/v1/capture/store
- [ ] Validate scope + preview_id
- [ ] Build triples from kept facts
- [ ] Call Agent Memory: `remember(infer="triples")`
- [ ] Read back with `entities.get()` per fact
- [ ] Build history
- [ ] Log to SQLite
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
  - `recall(q, scopes=["org"], limit=20)`
  - `recall(q, scopes=["org/team/ops"], limit=10)` (if user can read)
  - `recall(q, scopes=["org/user/<id>"], limit=10)` (if user can read)
- [ ] Fetch source for each hit
  - document: `documents.chunks(doc_id, chunk_id)`
  - entity: `entities.get() + entities.history()`
- [ ] Group by layer → build source drawers
- [ ] Log to SQLite
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
| **10:30 AM** | F1: Setup | B1: Setup + SQLite | API schemas finalized ✓ |
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
- [ ] Source drawer with full quote + context
- [ ] History accordion with version timeline

---

**Ready to split into parallel workstreams at 10:30 AM standup.**
