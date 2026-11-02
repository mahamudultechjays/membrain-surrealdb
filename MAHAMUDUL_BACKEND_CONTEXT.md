# Backend Build Plan: Mahamudul's Context & Tasks

**Date:** Nov 2, 2026  
**Time:** ~12:05 PM IST  
**Target:** EOD (3:30–4:30 PM) demo-ready  
**Branch:** `plans/nov2-synchronized-build` → `feat/capture-ask-scoping-api`

---

## What We're Building (Overview)

Four API-driven screens for Agent Memory integration:

1. **Capture** — text/document input → extract facts → store in Agent Memory
2. **Ask** — search memory across org/team/personal layers
3. **Scoping** — demonstrate scope isolation (Priya ≠ Arun data)
4. **Findings** — static tests, capabilities, gaps catalogue

Your job: Build the backend endpoints that these screens call.

---

## Key Decision: No SQLite Database

**Why skip SQLite?**
- Demo/POC doesn't need persistent audit trail
- Simpler scope, faster to build
- Console logging sufficient for debugging
- Reduces file I/O complexity during dev

**What we log instead:**
- Console (stdout) with structured prefixes: `[CAPTURE]`, `[ASK]`, `[SCOPING]`
- Include metadata in API responses (cost_tokens, trace_id, facts_found)
- No persistence — logs disappear when process exits (that's OK for POC)

---

## API Contract (What Frontend Expects)

### Capture Endpoints

#### POST /api/v1/capture/preview
Extract facts without writing.

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

**Response (200):**
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

---

#### POST /api/v1/capture/store
Write selected facts to Agent Memory.

**Request:**
```json
{
  "preview_id": "prev_abc123",
  "scope": "org/user/u-0001",
  "kept": ["e1", "e3", "e5"],
  "config": { "mode": "infer_text", "memory_category": "knowledge" }
}
```

**Response (200):**
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
Poll document processing status.

**Response (200):**
```json
{
  "doc_id": "doc_7f3a",
  "status": "queued" | "processing" | "ready" | "facts_readable",
  "chunks": 0,
  "keywords": 0,
  "created_at": "2026-11-02T10:00:00Z",
  "message": "Waiting in Agent Memory queue..."
}
```

---

### Ask Endpoint

#### GET /api/v1/ask?q=...&scope=...&include_inferred=false

**Response (200):**
```json
{
  "q": "What do we know about Acme?",
  "layers": [
    {
      "layer": "org",
      "facts": [
        {
          "fact": "returns policy · window_days = 30",
          "source": {
            "kind": "document",
            "title": "returns-policy-2026.pdf",
            "quote": "Customers may return items within 30 days of delivery.",
            "trust": 0.8
          }
        }
      ]
    }
  ],
  "metadata": {
    "total_facts": 5,
    "latency_ms": 812,
    "query_cost_tokens": 1100
  }
}
```

---

### Scoping Endpoints

#### GET /api/v1/scopes/list
```json
{
  "scopes": [
    { "id": "org/user/u-0001", "name": "Priya", "type": "user" },
    { "id": "org/user/u-0002", "name": "Arun", "type": "user" },
    { "id": "org/user/u-0003", "name": "Deena", "type": "user" }
  ]
}
```

#### POST /api/v1/scopes/switch
```json
{
  "active_scopes": ["org/user/u-0001", "org/user/u-0003"],
  "message": "Scope context switched (Priya + Deena)"
}
```

---

### Findings Endpoints
- GET /api/v1/findings/tests
- GET /api/v1/findings/capabilities
- GET /api/v1/findings/gaps
(Load static JSON from `backend/app/data/findings/`)

---

## Task Breakdown (B1–B7)

### B1: Infrastructure & Setup (10:00 AM)
- [ ] Add auth middleware: `backend/app/api/middleware.py`
- [ ] Create `/health` endpoint
- [ ] Set up console logger: `backend/app/services/logger.py`
- [ ] Load .env on startup

**Duration:** 30 min

---

### B2: Scope Manager (10:00–10:30 AM)
- [ ] Create `backend/app/services/scopes.py`
- [ ] Load API keys from .env
- [ ] Hardcode scope grants (demo)

**Duration:** 30 min

---

### B3: Capture Endpoints (10:30 AM – 12:00 PM)
- [ ] `POST /api/v1/capture/preview`
- [ ] `POST /api/v1/capture/store`
- [ ] `GET /api/v1/capture/document/{id}/status`
- [ ] Add to router
- [ ] Test with mock SDK

**Duration:** 90 min  
**FE Dependency:** Ready by 11:30 AM

---

### B4: Ask Endpoint (12:00 – 1:30 PM)
- [ ] `GET /api/v1/ask` (parallel layer recalls)
- [ ] Source mapping (documents + entities)
- [ ] Add to router

**Duration:** 90 min  
**FE Dependency:** Ready by 1:30 PM  
**Sync:** CHECKPOINT before lunch

---

### B5: Scoping Endpoints (1:30 – 2:30 PM)
- [ ] `GET /api/v1/scopes/list`
- [ ] `POST /api/v1/scopes/switch`
- [ ] Session/context management

**Duration:** 60 min  
**FE Dependency:** Ready by 2:30 PM

---

### B6: Findings Endpoints (2:30 – 3:00 PM)
- [ ] Create JSON files in `backend/app/data/findings/`
- [ ] Implement 3 GET endpoints
- [ ] Add to router

**Duration:** 30 min

---

### B7: Testing & Polish (3:00 – 3:30 PM)
- [ ] `make test` — all pass
- [ ] `make lint` — clean
- [ ] Manual testing of each flow
- [ ] Zero console errors

**Duration:** 30 min

---

## Timeline & Sync Points

```
10:00 AM  →  B1+B2 done
11:30 AM  →  B3 done (capture working)
1:30 PM   →  B4 done (ask working) ← SYNC CHECKPOINT
2:30 PM   →  B5 done (scoping working)
3:00 PM   →  B6 done (findings working)
3:30 PM   →  DEMO READY
```

---

## Configuration

### .env (Local Only - Do NOT commit)
```bash
MEMBRAIN_USER_PRIYA_KEY=sk_test_priya_f3a9c1d2e5
MEMBRAIN_USER_ARUN_KEY=sk_test_arun_b2e7f4a1c9
MEMBRAIN_USER_DEENA_KEY=sk_test_deena_d8c3e9f2a4
```

### Logging Pattern
```python
logger.log("[CAPTURE]", scope="org/user/u-0001", extracted=7, cost=4200)
# Output: [CAPTURE] scope=org/user/u-0001 extracted=7 cost=4200
```

---

## Directory Structure

```
backend/app/
├── api/
│   ├── middleware.py
│   └── v1/endpoints/
│       ├── capture.py
│       ├── ask.py
│       ├── scopes.py
│       └── findings.py
├── services/
│   ├── logger.py
│   └── scopes.py
├── data/findings/
│   ├── tests.json
│   ├── capabilities.json
│   └── gaps.json
└── adapters/agent_memory/
    ├── capture.py
    └── ask.py
```

---

## Critical Details

### Document Upload
- Agent Memory queues async (may take 10+ min)
- Documents > 2000 words show ~500 word preview only
- Status polling expected to take time
- FE has truncation warning (expected)

### Scope Isolation Demo
- Priya key → only reads/writes org/user/u-0001
- Arun key → only reads/writes org/user/u-0002
- When FE switches scope, backend switches API key
- Goal: Prove Priya's data invisible to Arun

---

## Success Criteria (EOD)

- [ ] All endpoints working (capture, ask, scopes, findings)
- [ ] Tests pass (`make test`)
- [ ] No lint errors (`make lint`)
- [ ] No console errors
- [ ] Scope isolation demonstrated
- [ ] FE can call all endpoints without 500 errors

---

**Branch:** `plans/nov2-synchronized-build`  
**Start command:** `git checkout -b feat/capture-ask-scoping-api`  
**First task:** B1 (middleware + logger)

Go build! 🚀
