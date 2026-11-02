Task: Fix the Nov 2 build plan where it conflicts with Agent Memory (review from Arun).
Outputs: drafts/build-plan-nov2-synchronized.md
Completed: Checked the five review points against the docs and the pinned surrealdb-memory SDK on 2026-11-02; all hold. Updated the plan's contracts, task lists and logging notes.
Decisions: Capture mode values are `triples` and `full`. No confidence, trust or token-cost fields. Ask hits expose `hit_kind`, `text` and `score`; `scope` maps to `lens`, result count to `k` (max 50). `preview_id` lives in an in-process cache. Sources: https://surrealdb.com/docs/agent-memory/ingest/experiential/remember and https://surrealdb.com/docs/agent-memory/retrieve/recall (checked 2026-11-02).
Open issues: Plan also had `documents.upload(infer=...)`, which the SDK does not accept; fixed in the plan.
Next action: Apply the "Changes Needed on feat/capture-ak-scoping-api" checklist in the plan on that branch, then run make check.
