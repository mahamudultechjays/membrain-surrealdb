# Build Plan: Nov 2, 2026 — Synchronized FE/BE

**Standup Date:** Nov 2, 10:30 IST  
**Target Deliverable:** 3:30–4:30 PM IST (by EOD)  
**Team:** Arun (FE), Mahamudul (BE), Binu (Lead)  

---

## Overview

Based on today's standup discussion and the mockup (`membrain-poc-v3.html`), we are building **three core screens** with real Agent Memory integration:

1. **Capture** — text/document/chat input with preview, config selection, and storage
2. **Ask** — search with layer-grouped results and source attribution
3. **Findings** — test results, capability map, and gaps catalogue

Both teams work in parallel to the **API contract** defined in Phase 0. This ensures FE can mock and BE can iterate independently.

---

## Phase 0: API Contracts (Shared Interface)

### Capture APIs

#### POST /api/v1/capture/preview
Extracts facts from input without writing. Returns preview for user approval.

**Request:**
```json
{
  "scope": "org/user/u-0001",
  "input_type": "text" | "document" | "chat",
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
  "cost_tokens": 4200
}
```

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

#### F2.4: Chat Tab
- [ ] Transcript display (mockup)
- [ ] "Import" → `POST /api/v1/capture/preview`

**Dependency:** BE `/capture/preview` & `/capture/store` by 11:30 AM

---

### F3: Ask Screen (NOW – 2:00 PM)
- [ ] Question input + quick-pick buttons
- [ ] `GET /api/v1/ask?q=...&scope=...`
- [ ] Group by layer (Org | Team | Personal)
- [ ] Source drawer per fact
- [ ] Checkboxes: "Show inferred", "Show context block"

**Dependency:** BE `/ask` endpoint by 2:00 PM

---

### F4: Findings Screen (NOW – 3:00 PM)
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

### B1: Infrastructure & Setup (NOW)
- [ ] Create SQLite schema & wrapper
- [ ] Add auth middleware (Bearer token → user context)
- [ ] Create `/health` endpoint
- [ ] Dependency injection for Agent Memory, SQLite, user context

**Files:**
- `backend/app/adapters/db/sqlite/client.py` (new)
- `backend/app/adapters/db/sqlite/schema.sql` (new)
- `backend/app/api/middleware.py` (new)
- `backend/app/api/v1/endpoints/capture.py` (stub)
- `backend/app/api/v1/endpoints/ask.py` (stub)
- `backend/app/api/v1/endpoints/findings.py` (stub)

---

### B2: Database & Traceability (NOW – 10:30 AM)

**SQLite Schema:**
```sql
CREATE TABLE IF NOT EXISTS capture_trace (
  id TEXT PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  user_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  input_type TEXT NOT NULL,
  config_mode TEXT NOT NULL,
  config_category TEXT NOT NULL,
  content_preview TEXT,
  extracted_count INTEGER,
  stored_count INTEGER,
  cost_tokens INTEGER,
  agent_memory_trace_id TEXT,
  result_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS ask_trace (
  id TEXT PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  user_id TEXT NOT NULL,
  question TEXT NOT NULL,
  scope TEXT NOT NULL,
  facts_found INTEGER,
  latency_ms INTEGER,
  cost_tokens INTEGER,
  result_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS user_grants (
  user_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  can_read BOOLEAN DEFAULT 1,
  can_write BOOLEAN DEFAULT 0,
  PRIMARY KEY (user_id, scope)
);
```

- [ ] Create traceability service
- [ ] Log every capture/ask call

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

### B5: Findings Endpoints (NOW – 3:00 PM)

#### B5.1–B5.3: GET /api/v1/findings/{tests,capabilities,gaps}
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

### B6: Access Control (Throughout)

#### B6.1: Middleware
- [ ] Extract Bearer token → validate (assume JWT with user_id, scopes)
- [ ] Inject user_context
- [ ] Return 401 if invalid

#### B6.2: Scope Validation
- [ ] Helper: `can_user_write(user_id, scope)`
- [ ] Helper: `can_user_read(user_id, scope)`
- [ ] Check `user_grants` table

#### B6.3: Endpoint Enforcement
- [ ] Capture: Validate user can write
- [ ] Ask: Validate user can read (use as read lens)
- [ ] Findings: Public

**Subtasks:**
- [ ] Create `backend/app/services/access.py`
- [ ] Hardcode test grants in `conftest.py`

---

## Synchronization Checkpoints

| Time | FE Needs | BE Provides | Status |
|------|----------|------------|--------|
| NOW (10:30) | API schema ✓ | Shared contract ✓ | Go/no-go |
| 10:00 AM | Health check | `/health` | Required |
| 11:30 AM | Capture UI | `/capture/preview`, `/capture/store` | FE E2E |
| 12:30 PM | Document polling | `/capture/document/{id}/status` | Document E2E |
| 2:00 PM | Ask UI | `/api/v1/ask` | Ask E2E |
| 3:00 PM | Findings UI | `/api/v1/findings/*` | Full app demo |

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

### Must Have
- [ ] Capture: text tab (input→preview→store)
- [ ] Ask: question + layer-grouped results
- [ ] Findings: tests, capabilities, gaps tabs
- [ ] Scope selector on Capture
- [ ] Config selector on Capture (mode, category)
- [ ] All API endpoints respond correctly
- [ ] Traceability logged to SQLite
- [ ] No console errors
- [ ] All tests pass

### Nice to Have
- [ ] Document tab with polling
- [ ] Chat import tab
- [ ] Source drawer on Ask
- [ ] History accordion

---

**Ready to split into parallel workstreams at 10:30 AM standup.**
