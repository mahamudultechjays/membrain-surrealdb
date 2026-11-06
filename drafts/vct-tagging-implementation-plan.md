# VCT tagging: implementation plan

Branch: `feat/vct-mapping` (built on `feat/capture-admin-ux`).
Design: [VCT Tagging Plan](https://claude.ai/artifact/UvHDx6Bx326thaYNpXfj9f), version 5.
Each phase ends with `make check` green, a commit and a push.

## Decisions this plan builds on

- Every fact gets both node and goal tags, matched separately by Agent Memory recall, with no LLM.
- Tags live only in our database as fact id + tags; fact text stays in Agent Memory.
- Matcher scopes: `org/spreetail/vct/nodes` (41) and `org/spreetail/vct/goals` (42), settings `VCT_SCOPE` and `VCT_GOALS_SCOPE`.
- The tagger runs every 3 hours and reads the `GET /attributes` listing, newest first, so `tag_queue` is dropped.
- A superseded fact gets a new id; the listing gives `supersedes`, so user tags carry over to the new version.
- A tag fix applies to everyone who can read the fact's scope.
- Pilot (Mahamudul, 6 Nov): the tagger first runs only on `org/spreetail/user/mahamudul_hasan`. We evaluate retrieval there, then widen to other scopes.

## Phase 1 · Tag storage

Goal: tables and a repository, with no Agent Memory calls.

- Port `app/domain/ports/fact_tags.py`:
  - `FactTag(fact_id, scope, kind: node|goal, tag, rank, source: auto|user, tagger_version, updated_by, updated_at)`.
  - `TagChange(fact_id, kind, action: change|remove|accept|add, old, new, tagger_version, user, at)`.
  - `FactTagRepository`: `tags_for(fact_ids)`, `tagged_ids(fact_ids)`, `save_auto(fact_id, scope, nodes, goals, version)`, `set_user_tag(fact_id, kind, tag, user)`, `remove(fact_id, kind, user)`, `accept(fact_id, kind, user)`, `copy_user_tags(old_id, new_id)`, `counts(scopes)`, `without_goal(scopes, limit, offset)`, `feedback_stats(since)`.
- Adapter `app/adapters/sqlite/fact_tags.py` on `SqliteStore`, in the same file as `user_scopes`:
  - `fact_tags`, primary key `(fact_id, kind, tag)`, index on `(kind, tag, rank)` and `scope`.
  - `tag_feedback`, insert only.
  - `tagged_facts(fact_id, scope, tagger_version, tagged_at)`: one row per fact the tagger has handled. It keeps a fact from being re-tagged after a person removes all its tags, and gives its scope for access checks.
- Rules enforced in the adapter:
  - `save_auto` never overwrites rows with source `user`.
  - Every user edit writes `fact_tags` and `tag_feedback` in one transaction.
  - A user change makes the new tag rank 1 and clears that kind's other rows.
- Wire in `composition.py`. Tests in `tests/adapters/test_sqlite_fact_tags.py`.

## Phase 2 · Tagger

Goal: tag every untagged fact, on a schedule and on demand.

- Port `FactLister` with `newest(limit, cursor)`, returning `id`, `value`, `summary`, `scopes`, `supersedes`.
  - Adapter: reuse the paging in `adapters/agent_memory/brain.py` (`GET /attributes`).
- Service `app/services/tagger.py`, `TaggerService.run()`:
  1. Page newest first and stop at a page where every fact is already tagged (cap: 50 pages).
  2. For each new fact: if `supersedes` has user tags, copy them first.
  3. Recall the fact's summary (or `value`) against the nodes scope and the goals scope, k=10, and keep the first 3 distinct ids of each.
  4. Save them as `auto` with `TAGGER_VERSION`.
- Limits:
  - 4 recalls at a time.
  - One run at a time, guarded by a lock.
  - A fact that fails is skipped and retried next run.
- Which scopes get tagged: setting `TAGGER_SCOPES`, a comma-separated allowlist, default `org/spreetail/user/mahamudul_hasan`.
  - Only facts whose scope is in the list are tagged; sub-scopes are not included.
  - The listing runs with a key minted for read on exactly those scopes (the existing `ScopedKeys` helper), so Agent Memory returns only their facts.
  - Widening later is a settings change, with no code change.
  - The matcher scopes and `org/spreetail/lab/*` are never tagged, even if listed.
- Last run (start, end, read, tagged, failed) is kept in memory for the admin panel.
- Schedule: an asyncio loop started in `main.py` lifespan, every `TAGGER_INTERVAL_HOURS` (3), off when `TAGGER_ENABLED=false`.
- Admin endpoints:
  - `POST /api/v1/admin/vct/tagger/run`
  - `GET /api/v1/admin/vct/tagger`
  - `POST /api/v1/admin/vct/seed` also seeds goals.
- Tests use a fake lister and a fake recall.
- Pilot run: tag `org/spreetail/user/mahamudul_hasan` live and record counts and timing in `progress.md`.
- Pilot eval (after phase 3): ask real questions in Ask with and without goal and node filters, note wrong tags and fix them in the editor, and record the results before widening `TAGGER_SCOPES`.

## Phase 3 · Ask filter and tags on results

Goal: Ask can keep only facts with a chosen goal or node, and shows tags.

- `GET /api/v1/ask` gains `goal`, `node` and `domain` query params, each repeatable.
- `ask_flow.py`:
  - With a filter, raise each scope's recall `k`, 3× the layer limit, so enough facts survive.
  - Look up rank-1 tags for all hit ids in one call. Hit ids drop their `attribute:` prefix.
  - Keep a hit only if it matches every chosen filter. Domain is checked through the node's `domain_id`.
  - Return `removed` counts, so the UI can show what the filter dropped.
- Every hit in the response carries `tags: {node, goal}`, with node, section and domain names from the map.
- The answer step reads only the kept facts.
- Tests: a fake recall plus an in-memory tag store; no filter gives exactly today's result.

## Phase 4 · Edit tags

Goal: anyone who can read a fact's scope can fix its tags.

- `GET /api/v1/facts/{fact_id}/tags`: current tags plus the rank 2 and 3 alternatives.
- `PUT /api/v1/facts/{fact_id}/tags` with `{kind, action: change|remove|accept, tag?}`.
- Access: the fact's scope from `fact_tags` must be in the user's granted scopes, otherwise 403. A fact with no row is 404.
- Tag ids are checked against the map, and an unknown tag is 422.
- Logged as `[TAG]` lines.

## Phase 5 · Coverage, gaps and tagger stats

- `GET /api/v1/vct/coverage`: fact counts per node and goal, rolled up to domain and section, over the caller's readable scopes only.
- `GET /api/v1/vct/untagged?kind=goal`: facts without a goal, newest first, paged. The text comes from the listing, never from our tables.
- `GET /api/v1/admin/vct/tagger` adds:
  - total tagged
  - correction rate, last 7 days: changed or removed ÷ tags shown
  - top 5 confused pairs, for example `mo1 → fi4`

## Phase 6 · Frontend

Built on the current pages and styles (`pages/*.css`, `index.css`, existing components); no new UI library.

1. Ask (`AskPage`, `components/ask/`):
   - Goal, node and domain filter chips. The goal picker is grouped by the 7 sections and shows each goal's weight.
   - "Compare with no filter" shows removed facts crossed out.
   - Each `FactRow` shows its node and goal tags.
2. Tag editor, a shared component used in Ask and Brain:
   - top 3 for node and goal, a searchable picker of all nodes or goals, Remove, Accept;
   - green for tags a person confirmed, "tagging within 3 h" for untagged facts.
3. Brain (`BrainPage`): tags and the editor on each fact.
4. Brain "VCT coverage":
   - the domain × section grid, with dashed cells for gaps;
   - the "Facts without a goal" list with "+ add goal".
5. Admin (`AdminPage`):
   - a tagger panel with last and next run, facts tagged last run, total tagged, correction rate, confusions, "Run now" and "Re-tag auto tags";
   - Onboard / Re-onboard per user, from the 5 Nov standup.
- API modules in `src/api/` (`vct.ts`, `tags.ts`) use relative `/api/...` paths. Vitest for each new component.

## Order and size

| Phase | Depends on | Size |
|---|---|---|
| 1 Tag storage | none | S |
| 2 Tagger | 1 | M |
| 3 Ask filter | 1 | M |
| 4 Edit tags | 1 | S |
| 5 Coverage and stats | 1, 2 | S |
| 6 Frontend | 3, 4, 5 | L |

Phases 3 and 4 can start as soon as phase 1 lands.

## Risks

- Tagging time: about 2 recalls of 12 s per fact with 4 in parallel, so 1,000 facts take about 100 minutes. The pilot keeps the first run to one personal scope, and each run is capped at 500 facts when we widen.
- Recall always returns a match, so off-topic facts get tags; users remove them.
- The listing order (newest first by `created_at`) was seen in one test. If it changes, the stop rule falls back to a full scan.
- The scheduler runs in the API process, so restarts reset the timer and the last-run stats. That's fine for the POC; membrain would use its job runner.
