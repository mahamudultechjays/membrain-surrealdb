# Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Facts that several people hold in their personal scopes become team rules after a team admin approves them. A background job finds and scores these facts, and Admin › Promotion is where the admin reviews them.

**Architecture:**
- **Job.** Every `PROMOTION_JOB_EVERY` the backend job does four things. It lists the facts in every personal scope (Agent Memory `GET /attributes`) and saves new ones as statements in SQLite. It groups the statements into topics with a small Claude model, using the same subject first and the full topic list second. It recomputes scores with a pure function, then updates the review list.
- **Approval.** Approving is the only code path that writes to Agent Memory's team scope.
- **Pattern.** The job copies the VCT tagger's pattern on this branch: a lock, `start()`, `loop()` and the last run kept in memory.

**Tech Stack:** FastAPI, Python 3.12, sqlite3 via `SqliteStore`, `surrealdb-memory` (raw transport calls as elsewhere), `anthropic` Python SDK (new dependency), React 19 + Vitest.

**Spec:** `drafts/promotion/promotion-build-spec.html` (published at https://claude.ai/artifact/NmVJYF7ejuJebZ3kMXuPqh). Read sections 3 to 7 before any task.

## Global Constraints

- **Running commands.** Everything runs in Docker:
  - one backend test: `docker compose run --rm --no-deps backend pytest <path> -v`
  - one frontend test: `docker compose run --rm --no-deps frontend npm test -- --run <path>`
  - the full gate: `make check`
- **Dependencies.** After editing `backend/pyproject.toml`, run `make lock`.
- **Layering.**
  - Only `app/composition.py` binds adapters to ports.
  - `app/domain/` imports nothing from the app.
  - New endpoints follow the CLAUDE.md pattern: a router in `endpoints/`, Pydantic models in `schemas/`, registration in `router.py`, and tests that swap in fakes with `dependency_overrides`.
- **Settings.** Every number in spec section 3 is a setting in `app/core/config.py`, with these defaults:
  - `PROMOTION_ENABLED=False`
  - `PROMOTION_TEAM_SCOPE="org/spreetail/team/common"`
  - `PROMOTION_PERSONAL_RULE_AT=1.75`
  - `PROMOTION_CANDIDATE_AT=3.0`
  - `PROMOTION_FLAG_AT=2.0`
  - `PROMOTION_FIRST_WEIGHT=1.0`
  - `PROMOTION_REPEAT_FACTOR=0.5`
  - `PROMOTION_BATCH_SIZE=20`
  - `PROMOTION_GENERIC_SUBJECTS="spreetail,our team,we,the company"`
  - `PROMOTION_MODEL="claude-haiku-5-5"`
  - `PROMOTION_JOB_EVERY_MINUTES=240`
  - `ANTHROPIC_API_KEY: str | None = None`
- **Test profile.** Values for `.env` only, not code: `PROMOTION_PERSONAL_RULE_AT=1.5`, `PROMOTION_CANDIDATE_AT=2`, `PROMOTION_FLAG_AT=1`, `PROMOTION_BATCH_SIZE=5`, `PROMOTION_JOB_EVERY_MINUTES=5`.
- **Agent Memory writes.**
  - The job writes nothing to Agent Memory.
  - Only the approve and close paths write, and only to `PROMOTION_TEAM_SCOPE`, through a key minted for write on that one scope.
  - No key is ever given `memory:forget`.
- **Who counts.** Only statements from personal scopes add to a score. Team and org scopes never count.
- **Closing text.** A closed rule's value is exactly `no longer a team rule (closed by {email} on {d Mon})`, for example `no longer a team rule (closed by ana@spreetail.com on 12 Nov)`. It carries the labels `kind=closed` and `closed_by={email}`.
- **Approved rule labels.** `kind=rule` and `approved_by={email}`, sent on every write (check S3: labels are not inherited).
- **Secrets.** Never commit `.env` or keys. Run `git grep -n "sp-\|sk-ant"` before each commit and expect no hits.
- **Commits.** Commit or push only when the user asks. Each task's "Commit" step means: stage, then wait for the user's go-ahead.

## Review Focus

1. **The model's answer is malformed or partly wrong.** Examples: an unknown statement ref, a topic id that doesn't exist, a missing statement, or the API call fails. Expected: those statements stay unprocessed and are retried next run, and nothing crashes. Test in Task 5: `test_bad_model_answers_leave_statements_unprocessed`.
2. **A capped or failed listing.** Expected: nothing is marked removed just because a page wasn't read. Only a complete listing may mark missing facts replaced. Test in Task 4: `test_capped_listing_marks_nothing_removed`.
3. **A rejected value, or a kept flag, would reopen every run.** Expected: it reopens only when its score climbs above `score_when_listed` from the time of that decision. Test in Task 6: `test_rejected_value_relists_only_above_old_score`.
4. **Two statements in one batch both create the "same" new topic.** Expected: one topic is created and both join it. Test in Task 5: `test_same_new_label_in_one_batch_creates_one_topic`.
5. **Approve or close on an item in the wrong state, or two admins at once.** Examples: approving a dropped item, or closing an item that is already closed. Expected: a 409 with a reason, and nothing is written to Agent Memory. Test in Task 8: `test_approve_wrong_status_is_409_and_writes_nothing`.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/domain/promotion.py` | Pure types and functions: `Stance`, `Weights`, `ScoredStatement`, `ValueScore`, `score()`, `clean_subject()` |
| `backend/app/domain/ports/promotion.py` | `Statement`, `FactGroup`, `ReviewItem`, `PromotionRepository` |
| `backend/app/domain/ports/grouping_model.py` | `StatementIn`, `TopicIn`, `NewTopic`, `TopicMatch`, `GroupingModel` |
| `backend/app/domain/ports/team_rules.py` | `TeamRuleWriter` |
| `backend/app/adapters/sqlite/promotion.py` | `SqlitePromotion(SqliteStore)`: the three tables |
| `backend/app/adapters/sqlite/user_scopes.py` | Adds the `user_roles` table and `roles_for` / `set_role` |
| `backend/app/adapters/agent_memory/fact_lister.py` | Adds entity, key, value, source kind and created time to `ListedFact`; the key holder becomes configurable |
| `backend/app/adapters/agent_memory/team_rules.py` | `AgentMemoryTeamRules`: writes a labelled triple to the team scope |
| `backend/app/adapters/anthropic/grouping.py` | `ClaudeGroupingModel`, `NotConfiguredGroupingModel` |
| `backend/app/services/promotion/intake.py` | Listing to statements |
| `backend/app/services/promotion/grouping.py` | The two-pass grouping and aliases |
| `backend/app/services/promotion/review.py` | Pure `plan_review()` and `apply_review()` |
| `backend/app/services/promotion/service.py` | `PromotionService`: run, lock, loop, status |
| `backend/app/services/promotion/decisions.py` | Approve, reject, keep and close |
| `backend/app/schemas/promotion.py`, `backend/app/api/v1/endpoints/promotion.py` | The API |
| `frontend/src/api/promotion.ts`, `frontend/src/api/mock/promotion.ts`, `frontend/src/components/admin/PromotionPanel.tsx`, `frontend/src/components/admin/promotion.css` | The Promotion tab |

---

### Task 1: Settings and the scoring function

**Files:**
- Modify: `backend/app/core/config.py` (the settings in Global Constraints, plus `promotion_generic_subjects() -> frozenset[str]`, which splits on commas, lowercases and strips)
- Create: `backend/app/domain/promotion.py`
- Test: `backend/tests/test_promotion_scoring.py`

**Interfaces:**
- Produces:
  ```python
  Stance = Literal["for", "against"]
  @dataclass(frozen=True, slots=True)
  class Weights: first: float; repeat_factor: float
  @dataclass(frozen=True, slots=True)
  class ScoredStatement: user: str; group_id: int; value: str; stance: Stance; said_at: str
  @dataclass(frozen=True, slots=True)
  class ValueScore:
      group_id: int; value: str
      for_score: float; against_score: float; team_score: float
      holders: tuple[str, ...]                 # users with a "for" statement, sorted
      personal: dict[str, float]               # user -> own for minus own against
      personal_rule_since: dict[str, str]      # user -> said_at that pushed them over the threshold
  def weight(n: int, w: Weights) -> float      # n-th statement (1-based): first * repeat_factor**(n-1)
  def score(statements: Iterable[ScoredStatement], w: Weights, *, personal_rule_at: float) -> list[ValueScore]
  def same_value(a: str, b: str) -> bool        # casefold, collapse spaces, strip trailing .;,
  def clean_subject(name: str) -> str           # lower, drop "type/" prefixes, "_"->" ", collapse spaces
  ```
- **Scoring rules (spec 5.2 and 6).** Within a group:
  - A "for" statement of value V counts for V.
  - It also counts against every other value in the group.
  - An "against" statement of V counts against V only.
  - For each user, the n-th statement for (or against) one value weighs `weight(n)`, in `said_at` order.
  - `team_score` is the sum over users of `for_u - against_u`.

- [ ] **Step 1: Write the failing tests**

```python
W = Weights(1.0, 0.5)

def s(user, value, at, stance="for", group=1):
    return ScoredStatement(user, group, value, stance, at)

def by_value(scores):
    return {(v.group_id, v.value): v for v in scores}

def test_worked_example_from_the_spec():
    rows = [s("a", "30 days", "1"), s("b", "30 days", "2"), s("c", "30 days", "3")]
    assert by_value(score(rows, W, personal_rule_at=1.75))[(1, "30 days")].team_score == 3
    rows.append(s("d", "60 days", "4"))
    v = by_value(score(rows, W, personal_rule_at=1.75))[(1, "30 days")]
    assert (v.for_score, v.against_score, v.team_score) == (3, 1, 2)
    rows.append(s("a", "30 days", "5"))
    v = by_value(score(rows, W, personal_rule_at=1.75))[(1, "30 days")]
    assert (v.for_score, v.team_score) == (3.5, 2.5)
    rows.append(s("e", "30 days", "6"))
    v = by_value(score(rows, W, personal_rule_at=1.75))[(1, "30 days")]
    assert (v.for_score, v.against_score, v.team_score) == (4.5, 1, 3.5)

def test_one_person_adds_at_most_about_two():
    rows = [s("a", "30 days", str(i)) for i in range(10)]
    assert by_value(score(rows, W, personal_rule_at=1.75))[(1, "30 days")].team_score < 2

def test_personal_rule_at_third_statement_with_default_and_second_with_test_profile():
    rows = [s("a", "30 days", "t1"), s("a", "30 days", "t2"), s("a", "30 days", "t3")]
    assert by_value(score(rows, W, personal_rule_at=1.75))[(1, "30 days")].personal_rule_since == {"a": "t3"}
    assert by_value(score(rows, W, personal_rule_at=1.5))[(1, "30 days")].personal_rule_since == {"a": "t2"}

def test_opposing_values_count_against_each_other():
    v = by_value(score([s("a", "30 days", "1"), s("b", "60 days", "2")], W, personal_rule_at=1.75))
    assert v[(1, "30 days")].team_score == 0 and v[(1, "60 days")].team_score == 0

def test_explicit_against_counts_only_against_that_value():
    v = by_value(score([s("a", "30 days", "1"), s("b", "30 days", "2", "against")], W, personal_rule_at=1.75))
    assert v[(1, "30 days")].team_score == 0 and (1, "") not in v

def test_values_compare_loosely_and_groups_stay_apart():
    v = by_value(score([s("a", "30 days", "1"), s("b", "30 Days.", "2"), s("c", "30 days", "3", group=2)], W, personal_rule_at=1.75))
    assert v[(1, "30 days")].for_score == 2 and v[(2, "30 days")].for_score == 1

def test_clean_subject():
    assert clean_subject("organisation/Cobalt_Ridge") == "cobalt ridge"
    assert clean_subject("  Cobalt   Ridge ") == "cobalt ridge"
```

(Self-correction is covered in Task 4: replaced statements never reach `score()`.)

- [ ] **Step 2: Run the tests and see them fail.** `docker compose run --rm --no-deps backend pytest tests/test_promotion_scoring.py -v`. Expect an `ImportError` for `app.domain.promotion`.
- [ ] **Step 3: Implement** the settings, then `weight`, `same_value`, `clean_subject` and `score` in `app/domain/promotion.py`.
  - The `value` reported for a group is the first spelling seen.
  - Floats are compared after `round(x, 6)`.
- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Commit.** `feat: promotion settings and scoring`

---

### Task 2: The promotion store (SQLite)

**Files:**
- Create: `backend/app/domain/ports/promotion.py` and `backend/app/adapters/sqlite/promotion.py`
- Modify: `backend/app/adapters/sqlite/__init__.py` (export `SqlitePromotion`)
- Test: `backend/tests/adapters/test_sqlite_promotion.py`

**Interfaces:**
- Consumes: `Stance` from Task 1.
- Produces:
  ```python
  Source = Literal["chat", "app"]
  ReviewKind = Literal["candidate", "flag"]
  ReviewStatus = Literal["open", "active", "closed", "rejected", "dropped", "kept"]
  @dataclass(frozen=True, slots=True)
  class Statement:
      user: str; scope: str; memory_ref: str; source: Source; text: str
      entity: str; key: str; value: str; said_at: str
      id: int | None = None; group_id: int | None = None; stance: Stance | None = None
      norm_value: str | None = None; replaced_at: str | None = None; processed_at: str | None = None
  @dataclass(frozen=True, slots=True)
  class FactGroup:
      label: str; subject: str; rule_entity_type: str; rule_entity: str; rule_key: str
      aliases: tuple[str, ...] = (); id: int | None = None; created_at: str | None = None
  @dataclass(frozen=True, slots=True)
  class ReviewItem:
      kind: ReviewKind; group_id: int; value: str; score_when_listed: float; status: ReviewStatus
      id: int | None = None; decided_by: str | None = None; decided_at: str | None = None
      memory_ref: str | None = None; rule_id: int | None = None; closed_ref: str | None = None
      created_at: str | None = None
  class PromotionRepository(Protocol):
      async def known_refs(self, refs: list[str]) -> set[str]
      async def add_statements(self, rows: list[Statement]) -> int          # ignores memory_refs already stored
      async def mark_replaced(self, refs: list[str], at: str) -> int        # only rows not yet replaced
      async def live_refs(self, scopes: list[str]) -> set[str]              # memory_refs not replaced, in these scopes
      async def unprocessed(self, limit: int) -> list[Statement]            # not replaced, processed_at NULL, oldest first
      async def set_grouping(self, rows: list[tuple[int, int, str, Stance]], at: str) -> None  # (statement_id, group_id, norm_value, stance)
      async def counted(self) -> list[Statement]                            # grouped and not replaced
      async def groups(self) -> list[FactGroup]
      async def groups_for_subjects(self, subjects: set[str]) -> list[FactGroup]  # subject or any alias matches
      async def add_group(self, group: FactGroup) -> int
      async def add_alias(self, group_id: int, alias: str) -> None          # no duplicates, never the subject itself
      async def update_rule(self, group_id: int, *, label: str, entity_type: str, entity: str, key: str) -> None
      async def review_items(self) -> list[ReviewItem]
      async def add_review_item(self, item: ReviewItem) -> int
      async def set_status(self, item_id: int, status: ReviewStatus, *, expect: set[ReviewStatus],
                           by: str | None = None, at: str | None = None,
                           memory_ref: str | None = None, closed_ref: str | None = None) -> ReviewItem
      async def closed_rule_refs(self) -> frozenset[str]                    # memory_ref and closed_ref of closed candidates
  ```
- **What `set_status` does.**
  - It runs `UPDATE ... WHERE id = ? AND status IN (expect)` in one transaction.
  - It raises `PromotionStateError(item_id, current_status)` (new, in `app/domain/errors.py`) when no row changed. That is the guard for two admins acting at once.
- **Schema.**
  - The three spec tables (section 4) live in the same file as the grants (`settings.USER_SCOPES_DB_PATH`).
  - `aliases` is stored as a JSON text column.
  - The spec's fields are extended by four columns: `statement.norm_value` (the model's normalised value), `fact_group.rule_entity_type`, `review_item.closed_ref` (the closing value's id) and `review_item.created_at`.

- [ ] **Step 1: Write the failing tests.** Use `SqlitePromotion(":memory:")`.
  - `test_add_statements_skips_known_refs`: add the same `memory_ref` twice, so 1 is returned the second time and 0 rows are added.
  - `test_mark_replaced_and_live_refs`: add 2 rows in scope `s` and mark one replaced. `live_refs(["s"])` returns only the other, and `counted()` excludes the replaced row once both are grouped.
  - `test_unprocessed_then_set_grouping`: `set_grouping` sets `group_id`, `norm_value`, `stance` and `processed_at`, after which `unprocessed()` is empty.
  - `test_groups_for_subjects_matches_aliases`: add a group with subject `cobalt ridge`, then `add_alias(id, "cobalt ridge returns")`. `groups_for_subjects({"cobalt ridge returns"})` returns it, and a second identical `add_alias` stores nothing new.
  - `test_set_status_guards_expected_status`: open goes to active with `expect={"open"}`. Repeating it raises `PromotionStateError`.
  - `test_closed_rule_refs`: close an item that has `memory_ref="a1"` and `closed_ref="a2"`, so the result is `{"a1", "a2"}`.
- [ ] **Step 2: Run the tests and see them fail.** `docker compose run --rm --no-deps backend pytest tests/adapters/test_sqlite_promotion.py -v`. Expect an `ImportError`.
- [ ] **Step 3: Implement** `SqlitePromotion(SqliteStore)` with `_SCHEMA` and the methods above. Follow `adapters/sqlite/fact_tags.py`.
- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Commit.** `feat: promotion SQLite store`

---

### Task 3: The common team scope and the team-admin role

**Files:**
- Modify:
  - `backend/app/adapters/sqlite/user_scopes.py` (adds a `user_roles(email, role, created_at, PRIMARY KEY(email, role))` table and these methods: `roles_for(email) -> set[str]`, `set_role(email, role, on: bool) -> None`, `emails_with_role(role) -> list[str]`)
  - `backend/app/domain/ports/user_scopes.py` (adds those three methods to `UserScopeRepository`)
  - `backend/app/services/access.py`: putting a grant with `access="write"` on `settings.PROMOTION_TEAM_SCOPE` raises the new `TeamScopeWriteError`
  - `backend/app/api/v1/endpoints/admin.py`: `PUT` and `DELETE /admin/team-admins/{email}` (org admins only) and `GET /admin/team-admins`
  - `backend/app/api/deps.py`:
    - `async def is_team_admin(email) -> bool`
    - `require_promotion_admin`, which returns 403 unless the user is an org admin or a team admin
    - `PromotionAdminDep`
  - `backend/app/schemas/auth.py` and `endpoints/auth.py`: `/auth/me` adds `is_team_admin: bool`
- Test: `backend/tests/test_access.py`, `backend/tests/test_admin.py`, `backend/tests/test_auth.py` (new cases)

**Interfaces:**
- Produces: `ROLE_TEAM_ADMIN = "team_admin"` (in `domain/ports/user_scopes.py`), `PromotionAdminDep`, and `me.is_team_admin`.

- [ ] **Step 1: Write the failing tests.**
  - `test_write_grant_on_team_scope_is_refused`: granting write on `PROMOTION_TEAM_SCOPE` through the Admin grant endpoint returns 400 with the message `The team scope is written only by promotion approval.`
  - `test_read_grant_on_team_scope_is_allowed`: the same call with read access succeeds.
  - `test_team_admin_role_round_trip`: org admin calls `PUT /admin/team-admins/x@s.com`. Then `GET /admin/team-admins` returns `["x@s.com"]`, and `/auth/me` for x returns `is_team_admin: true`. After `DELETE` it returns `false`.
  - `test_team_admin_endpoints_need_org_admin`: a team admin calling `PUT /admin/team-admins/...` gets 403.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement.** Map `TeamScopeWriteError` to 400 in the admin endpoint.
- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Commit.** `feat: common team scope guard and team-admin role`

The scope itself is created, and members are given read access, from Admin › Access in Task 11. There is no code for it.

---

### Task 4: Intake — new and changed facts from personal scopes

**Files:**
- Modify:
  - `backend/app/domain/ports/fact_lister.py`: `ListedFact` adds `entity_type: str | None = None`, `entity: str | None = None`, `key: str | None = None`, `value: str | None = None`, `created_at: str | None = None`, `source_kind: str | None = None`
  - `backend/app/adapters/agent_memory/fact_lister.py`:
    - fill those fields from the raw `entity`, `key`, `value`, `createdAt` and `source.kind`
    - `entity` comes from `"['organisation', 'cobalt_ridge']"` or `"entity:organisation/organisation/cobalt_ridge"` and gives type `organisation`, name `cobalt_ridge`
    - the constructor takes `holder: str = "vct-tagger"` and `prefix: str = "membrain-tagger"`
- Create: `backend/app/services/promotion/__init__.py` and `backend/app/services/promotion/intake.py`
- Test: `backend/tests/adapters/test_agent_memory_fact_lister.py` (new case) and `backend/tests/test_promotion_intake.py`

**Interfaces:**
- Consumes: `PromotionRepository` (Task 2), `FactLister`.
- Produces:
  ```python
  @dataclass
  class IntakeStats: listed: int = 0; new: int = 0; replaced: int = 0; skipped: int = 0; capped: bool = False
  def personal_owners(grants: list[ScopeGrant]) -> dict[str, str]   # scope_path -> email, layer == "personal" only
  async def intake(repo: PromotionRepository, lister: FactLister, owners: dict[str, str], *,
                   now: str, page_size: int = 200, max_pages: int = 50) -> IntakeStats
  ```
- **Rules.**
  - Read pages until `cursor is None` or `max_pages` is reached; reaching `max_pages` sets `capped`.
  - Each fact's owner is the first of its scopes found in `owners`. A fact in no personal scope is skipped.
  - `source_kind == "turn"` becomes "chat" and `"upsert"` becomes "app". Any other kind (consolidation and the like) is skipped and counted in `skipped`.
  - `fact.supersedes` marks that older ref replaced.
  - Only when not capped: `live_refs(scopes) - listed ids` are marked replaced, because they were removed.
  - `said_at = created_at or now`, and `text = fact.text`.

- [ ] **Step 1: Write the failing tests.** Use a fake `FactLister` that returns fixed pages, and the real `SqlitePromotion(":memory:")`.
  - `test_chat_and_app_facts_become_statements_for_the_owner`: a turn fact in `org/spreetail/user/ana` and an upsert fact in `.../ben` give 2 statements. Their users are `ana@s.com` and `ben@s.com`, and their sources are chat and app.
  - `test_consolidated_and_foreign_scope_facts_are_skipped`.
  - `test_second_run_adds_nothing_new`: `new == 0`.
  - `test_correction_marks_old_statement_replaced`: run 2 lists fact `f2` with `supersedes="f1"`, so `f1` has `replaced_at` set and `counted()` excludes it.
  - `test_removed_fact_is_marked_replaced`: `f1` is missing from a complete run 2.
  - `test_capped_listing_marks_nothing_removed` (Review Focus 2): with `max_pages=1` and a cursor still returned, `f1` stays live.
  - Adapter test `test_listing_keeps_entity_key_value_and_source_kind`, on the raw shape from `drafts/findings/promo-checks/personal-listing.json`.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and see them pass.** Also run `tests/test_tagger.py`: the tagger must stay green.
- [ ] **Step 5: Commit.** `feat: promotion intake from personal scope listings`

---

### Task 5: Grouping with a small Claude model

**Files:**
- Modify:
  - `backend/pyproject.toml`: add `anthropic`, pinned the way `surrealdb-memory` is, then run `make lock`
  - `backend/app/core/config.py`: `ANTHROPIC_API_KEY` (already listed in Task 1, if not added there)
- Create:
  - `backend/app/domain/ports/grouping_model.py`
  - `backend/app/adapters/anthropic/__init__.py` and `backend/app/adapters/anthropic/grouping.py`
  - `backend/app/services/promotion/grouping.py`
- Test: `backend/tests/test_promotion_grouping.py` and `backend/tests/adapters/test_anthropic_grouping.py`

**Interfaces:**
- Consumes: `clean_subject`, `same_value` (Task 1); `PromotionRepository`, `FactGroup`, `Statement` (Task 2).
- Produces:
  ```python
  @dataclass(frozen=True, slots=True)
  class StatementIn: ref: str; subject: str; text: str; key: str; value: str
  @dataclass(frozen=True, slots=True)
  class TopicIn: id: int; label: str; values: tuple[str, ...]
  @dataclass(frozen=True, slots=True)
  class NewTopic: label: str; entity_type: str; entity: str; key: str
  @dataclass(frozen=True, slots=True)
  class TopicMatch: ref: str; topic_id: int | None; new_topic: NewTopic | None; value: str; stance: Stance
  class GroupingModel(Protocol):
      async def match(self, statements: list[StatementIn], topics: list[TopicIn], *, allow_new: bool) -> list[TopicMatch]
  @dataclass
  class GroupingStats: sent: int = 0; first_pass: int = 0; full_list: int = 0; new_topics: int = 0; aliases: int = 0; left: int = 0; error: str | None = None
  async def group_new(repo: PromotionRepository, model: GroupingModel, *, batch_size: int,
                      generic_subjects: frozenset[str], now: str, max_batches: int = 20) -> GroupingStats
  ```
- **The algorithm** (spec 5.1). It runs per batch of `unprocessed(batch_size)`:
  1. **Same subject first.** `subject = clean_subject(statement.entity)`. Statements whose subject is in `generic_subjects` skip this pass. For the rest, call `topics = groups_for_subjects(subjects)`. If there are topics, call `match(..., allow_new=False)` and keep the answers that name a known topic id.
  2. **Full list.** Everything left goes to `match(..., allow_new=True)` with `groups()`. The answer's `new_topic` is created with `add_group`; topic labels are compared with `same_value` within the run, so a label is created only once. The new group's `subject` is the statement's subject.
  3. **Aliases.** A full-list match to an existing topic whose subject differs from the statement's subject (and isn't generic) calls `add_alias`.
  4. **Save.** Matched statements go to `set_grouping` with `(id, group_id, match.value, match.stance)`.
  5. **Failures.** Statements with no valid answer stay unprocessed and count in `left`. If the model raises, set `error`, stop and leave the batch unprocessed.
  6. **Stop condition.** Batches repeat until `unprocessed` returns nothing new or `max_batches` is reached.
- **`TopicIn.values`** are the distinct `norm_value`s already in the group, so the model can return the value "in the form the topic already uses".
- **`ClaudeGroupingModel(client: anthropic.AsyncAnthropic, model: str)`.**
  - It uses `await client.messages.parse(model=..., max_tokens=4096, output_config={"effort": "low"}, system=..., messages=[...], output_format=MatchList)`, where `MatchList` is a Pydantic model `{matches: list[MatchOut]}`.
  - The system prompt states the rules: match by meaning; return the value in the topic's existing form; say none when nothing fits; create a new topic only when `allow_new`; stance is "against" only when the statement denies a value.
  - The statements and topics go as JSON in the user message.
  - It raises `MemoryUnavailableError`-style `GroupingModelError` (new, in `domain/errors.py`) on `anthropic.APIError`.
- **`NotConfiguredGroupingModel.match`** raises `GroupingModelError("ANTHROPIC_API_KEY is not set")`.

- [ ] **Step 1: Write the failing tests.** The service tests use a scripted fake `GroupingModel` that records its calls and returns preset `TopicMatch`es.
  - `test_conflict_notes_land_in_one_group_with_three_values`: Cobalt Ridge statements with 30 / 45 / 60 days give 1 group with 3 `norm_value`s.
  - `test_same_subject_pass_runs_before_full_list`: with an existing "cobalt ridge" topic, the first call has `allow_new=False` and only that topic. There is no second call when all match.
  - `test_unmatched_go_to_full_list_and_may_create_topic`: the second call has `allow_new=True` and every topic, and `new_topics == 1`.
  - `test_generic_subject_skips_first_pass`: entity "Spreetail" goes straight to `allow_new=True`.
  - `test_cross_subject_match_learns_alias`: subject "cobalt ridge returns" matched in pass 2 to "cobalt ridge" saves the alias. The next run's first pass finds it.
  - `test_same_new_label_in_one_batch_creates_one_topic` (Review Focus 4).
  - `test_bad_model_answers_leave_statements_unprocessed` (Review Focus 1): an unknown ref, an unknown topic id, an omitted statement and a raised `GroupingModelError`. Check `left` and `error`, and that `unprocessed()` still returns those statements.
  - Adapter test `test_claude_grouping_maps_parsed_output`: a fake `client.messages.parse` returns `parsed_output`, which maps to `TopicMatch`es and sends `model == "claude-haiku-5-5"`.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement** the port, service and adapter.
- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Commit.** `feat: promotion grouping with a small Claude model`

---

### Task 6: Scores, stages and the review list

**Files:**
- Create: `backend/app/services/promotion/review.py`
- Test: `backend/tests/test_promotion_review.py`

**Interfaces:**
- Consumes: `score`, `ValueScore`, `ScoredStatement`, `Weights`, `same_value` (Task 1); `ReviewItem`, `PromotionRepository` (Task 2).
- Produces:
  ```python
  @dataclass
  class ReviewChanges:
      open: list[ReviewItem]                    # new candidates and flags, status "open"
      drop: list[int]                           # open candidate ids whose score fell below candidate_at
  def plan_review(scores: list[ValueScore], items: list[ReviewItem], *, candidate_at: float, flag_at: float) -> ReviewChanges
  async def apply_review(repo: PromotionRepository, changes: ReviewChanges) -> None   # set_status(..., "dropped", expect={"open"})
  def to_scored(rows: list[Statement]) -> list[ScoredStatement]   # uses norm_value, skips rows without group or stance
  ```
- **Rules.**
  - **Candidates.**
    - Open a candidate when `team_score >= candidate_at` and no open or active candidate exists for that (group, value).
    - Never open one for a value whose group has an active rule with the same value.
    - A (group, value) whose latest candidate was rejected reopens only when `team_score > that score_when_listed`.
    - Open candidates below the threshold are dropped. A dropped value may open again later as a new row (the worked example's "listed again").
  - **Flags.**
    - An active rule is a candidate with `status == "active"`. Its flag score is the `against_score` of its (group, value).
    - Open a flag (`kind="flag"`, `rule_id=rule.id`) when that score is at least `flag_at` and the rule has no open flag.
    - After a flag is kept, the next flag opens only when the score is above the kept flag's `score_when_listed`.

- [ ] **Step 1: Write the failing tests.**
  - `test_worked_example_lists_drops_and_relists`: replay the spec's four events with `candidate_at=3`. Check the changes after each step: open, then dropped, then nothing, then open again as a new item.
  - `test_no_candidate_when_rule_already_active`.
  - `test_rejected_value_relists_only_above_old_score` (Review Focus 3).
  - `test_flag_opens_at_flag_at_once_per_rule`: two people say 60 against an active 30 with `flag_at=2`, which gives 1 flag. The next run opens no second flag.
  - `test_kept_flag_reopens_only_above_kept_score`.
  - `test_to_scored_skips_ungrouped_rows`.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Commit.** `feat: promotion review list from scores`

---

### Task 7: The promotion job — run, lock, schedule, status

**Files:**
- Create: `backend/app/services/promotion/service.py`
- Modify:
  - `backend/app/composition.py`: these functions, each with `@lru_cache`:
    - `get_promotion_repository()`
    - `get_promotion_lister()`: an `AgentMemoryFactLister(..., holder="promotion-job", prefix="membrain-promotion")`
    - `get_grouping_model()`: Claude when `ANTHROPIC_API_KEY` is set, otherwise NotConfigured
    - `get_promotion_service()`
  - `backend/app/main.py`: start `get_promotion_service().loop(settings.PROMOTION_JOB_EVERY_MINUTES * 60)` when `PROMOTION_ENABLED` is set and Agent Memory is configured; cancel it on shutdown like the tagger
  - `backend/app/domain/errors.py`: `PromotionBusyError`
- Test: `backend/tests/test_promotion_service.py`

**Interfaces:**
- Consumes: Tasks 2, 4, 5 and 6, plus `UserScopeRepository.all_grants()`.
- Produces:
  ```python
  @dataclass
  class PromotionRun:
      started_at: str; finished_at: str | None = None
      intake: IntakeStats = field(default_factory=IntakeStats); grouping: GroupingStats = field(default_factory=GroupingStats)
      opened: int = 0; dropped: int = 0; error: str | None = None
  class PromotionService:
      def __init__(self, repo, lister, model, grants: UserScopeRepository, *, weights: Weights,
                   personal_rule_at: float, candidate_at: float, flag_at: float,
                   batch_size: int, generic_subjects: frozenset[str]) -> None
      running: bool (property); last: PromotionRun | None; next_run_at: str | None
      def start(self) -> bool                    # False when already running
      async def run(self) -> PromotionRun        # raises PromotionBusyError when locked
      async def loop(self, interval_seconds: float) -> None
      async def scores(self) -> list[ValueScore] # recomputed from repo.counted(), for the API
  ```
- **The order of one run:** intake, then group_new, then score, then plan_review and apply_review.
  - An Agent Memory error in intake sets `error` and skips the rest.
  - A grouping error sets `error`, but scoring and review still run on what is already grouped.

- [ ] **Step 1: Write the failing tests.** Use fakes for lister, model and grants, and the real in-memory store.
  - `test_run_goes_from_listing_to_open_candidate`: three users' "30 days" facts with test-profile thresholds give one open candidate, and `last.opened == 1`.
  - `test_second_run_while_running_is_busy`: hold the lock, then `run()` raises `PromotionBusyError` and `start()` returns False.
  - `test_listing_failure_is_recorded_not_raised`: `last.error` is set and the store is unchanged.
  - `test_grouping_failure_still_rescores`.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement** the service, composition and lifespan.
- [ ] **Step 4: Run the tests and see them pass**, plus `tests/test_composition.py`.
- [ ] **Step 5: Commit.** `feat: promotion job with lock and schedule`

---

### Task 8: Team rule writes, decisions and the Promotion API

**Files:**
- Create:
  - `backend/app/domain/ports/team_rules.py`
  - `backend/app/adapters/agent_memory/team_rules.py`
  - `backend/app/services/promotion/decisions.py`
  - `backend/app/schemas/promotion.py`
  - `backend/app/api/v1/endpoints/promotion.py`
- Modify: `backend/app/api/v1/router.py`, `backend/app/api/deps.py` (add `PromotionServiceDep`, `PromotionRepositoryDep`, `TeamRuleWriterDep`), `backend/app/composition.py` (add `get_team_rule_writer()`)
- Test: `backend/tests/test_promotion_api.py` and `backend/tests/adapters/test_agent_memory_team_rules.py`

**Interfaces:**
- Consumes: `PromotionAdminDep` (Task 3); `PromotionService` (Task 7); `PromotionRepository.set_status` and `update_rule` (Task 2).
- Produces:
  ```python
  class TeamRuleWriter(Protocol):
      async def write(self, *, entity_type: str, entity: str, key: str, value: str, labels: list[str]) -> str  # attribute id
  @dataclass(frozen=True, slots=True)
  class RuleEdit: label: str; entity_type: str; entity: str; key: str; value: str
  async def approve(repo, writer, item_id: int, *, by: str, edit: RuleEdit | None, today: date) -> ReviewItem
  async def reject(repo, item_id: int, *, by: str) -> ReviewItem
  async def keep(repo, item_id: int, *, by: str) -> ReviewItem                  # flag: open -> kept
  async def close(repo, writer, item_id: int, *, by: str, today: date) -> ReviewItem
  def closing_text(by: str, today: date) -> str   # "no longer a team rule (closed by {by} on {d Mon})"
  ```
- **What each decision does.**
  - **Approve.**
    1. Check the item is an open candidate before writing; otherwise raise `PromotionStateError`.
    2. Apply `edit` with `update_rule`.
    3. Write `{"entity": {"name": entity, "type": entity_type}, "key": key, "value": value}`, labelled `kind=rule` and `approved_by={by}`.
    4. Call `set_status(id, "active", expect={"open"}, memory_ref=ref)`.
  - **Close.** It accepts an active candidate, or an open or kept flag.
    - For a flag, it closes the flag and its rule (`rule_id`).
    - For the rule, it writes `closing_text` with labels `kind=closed` and `closed_by={by}`, then calls `set_status(rule, "closed", expect={"active"}, closed_ref=ref)`.
  - **Reject and keep** set the status only (rejected, kept).
- **`AgentMemoryTeamRules(admin, connect, *, scope)`.** It mints a key through `ScopedKeys` for `{"memory:write": [scope], "memory:read": [scope]}` with holder `promotion-approval`. It calls `client.remember(infer="triples", triples=[...], scopes=[scope], memory_category="knowledge", labels=labels)` and returns `response.extraction.attributes[0].id` (the shape in `drafts/findings/promo-checks/s3.json`).
- **Endpoints.** All are under `/promotion` and use `PromotionAdminDep`. `PromotionStateError` maps to 409 and `PromotionBusyError` to 409 with "already running".
  - `GET /promotion` returns a `PromotionStatus`:
    - `enabled`, `running`, `next_run_at`
    - `last_run` (a `PromotionRun` view)
    - `team_scope`
    - `items: list[ReviewItemOut]`. Each item has id, kind, status, group label, entity_type, entity, key, value, `score_when_listed`, the current `team_score`, `for_score` and `against_score`, `holders` (emails), the decision by/at, and `rule_id`.
    - The `items` list covers open, active and kept items, plus the last 20 closed, rejected or dropped ones.
  - `POST /promotion/run` returns 202 `{started: true}`, or 409.
  - `POST /promotion/items/{id}/approve` takes an optional `RuleEditIn` body.
  - `POST /promotion/items/{id}/reject`, `/keep` and `/close`.

- [ ] **Step 1: Write the failing tests.** The API tests use `dependency_overrides` with the in-memory store, a recording fake `TeamRuleWriter` and a fake service.
  - `test_get_promotion_lists_items_with_scores`.
  - `test_approve_writes_labelled_rule_and_activates`: the writer gets `labels == ["kind=rule", "approved_by=admin@s.com"]` and the item becomes active with a `memory_ref`.
  - `test_approve_with_edit_uses_edited_entity_key_value`.
  - `test_approve_wrong_status_is_409_and_writes_nothing` (Review Focus 5).
  - `test_close_flag_closes_rule_with_closing_value`: the writer gets `value == "no longer a team rule (closed by admin@s.com on 12 Nov)"` and `labels == ["kind=closed", "closed_by=admin@s.com"]`. Both items end up closed.
  - `test_team_admin_can_decide_and_other_users_get_403`.
  - `test_run_now_twice_is_409`.
  - Adapter test `test_team_rule_write_uses_team_scope_key_and_returns_id`: a fake client checks the scopes and labels.
- [ ] **Step 2: Run the tests and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and see them pass.**
- [ ] **Step 5: Commit.** `feat: promotion decisions and API`

---

### Task 9: Ask skips closed rules

**Files:**
- Modify:
  - `backend/app/services/ask_flow.py`: `ask(recall, grants, *, q, skip: frozenset[str] = frozenset())` drops hits whose bare id (`hit.id.split(":", 1)[-1]`) is in `skip`
  - `backend/app/api/v1/endpoints/ask.py`: pass `skip=await promotion_repo.closed_rule_refs()`
- Test: `backend/tests/test_ask.py` (new case)

**Interfaces:**
- Consumes: `PromotionRepository.closed_rule_refs()` (Task 2).

- [ ] **Step 1: Write the failing test.** `test_ask_drops_closed_rule_hits`: the fake recall returns `attribute:a1` (the closed rule), `attribute:a2` (its closing value) and `attribute:b1`, while the store has the closed refs `{"a1", "a2"}`. The response facts hold only `b1`, in both the Default and Value-driven columns.
- [ ] **Step 2: Run the test and see it fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `tests/test_ask.py` and see it pass.**
- [ ] **Step 5: Commit.** `feat: Ask skips closed team rules`

Chat and Reflect answer through Agent Memory and cannot be filtered. There, the closing value's wording carries the meaning (spec section 4).

---

### Task 10: Admin › Promotion tab

**Files:**
- Create:
  - `frontend/src/api/promotion.ts`: types that mirror `PromotionStatus` and `ReviewItemOut`, plus `promotionApi.status()`, `.run()`, `.approve(id, edit?)`, `.reject(id)`, `.keep(id)` and `.close(id)`, called on relative `/api/v1/promotion...` paths through `client.ts`
  - `frontend/src/api/mock/promotion.ts`
  - `frontend/src/components/admin/PromotionPanel.tsx` and `promotion.css`
  - `frontend/src/components/admin/PromotionPanel.test.tsx`
- Modify:
  - `frontend/src/pages/AdminPage.tsx`:
    - `SECTIONS` becomes `['access', 'lab', 'vct', 'promotion']` with the label `Promotion`
    - a team admin who is not an org admin sees only `promotion`, and it is their default
  - `frontend/src/App.tsx`: the Admin route shows when `me.is_admin || me.is_team_admin`
  - `frontend/src/api/auth.ts`: adds `is_team_admin: boolean`
  - the Access section: a "Team admin" checkbox per person, which calls `PUT` or `DELETE /admin/team-admins/{email}` from Task 3
- Test: `frontend/src/pages/AdminPage.test.tsx` (new cases)

**Interfaces:**
- Consumes: the endpoints from Tasks 3 and 8.
- **Layout.** Follow the screenshot `drafts/promotion/admin-promotion-mock.png` and spec section 7:
  - a header line with the last run, the next run and a Run now button
  - sections Candidates, Flags and Team rules
  - each row shows the label, value, team score against the threshold, holders, and its actions
  - Approve opens inline fields (wording, entity type, entity, key, value) filled from the item, with Confirm and Cancel
  - no `confirm()` dialogs

- [ ] **Step 1: Write the failing tests.**
  - `PromotionPanel` renders the mock items in the right sections.
  - Approve with edited fields calls `approve(id, {...edited})`.
  - Run now while running shows "already running" from a 409.
  - Close on an active rule calls `close(id)`.
  - `AdminPage`: a team admin sees only the Promotion tab, and an org admin sees all four.
- [ ] **Step 2: Run the tests and see them fail.** `docker compose run --rm --no-deps frontend npm test -- --run src/components/admin/PromotionPanel.test.tsx src/pages/AdminPage.test.tsx`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and see them pass, then `make check`.** It must be green; report the backend and frontend test counts.
- [ ] **Step 5: Commit.** `feat: Admin › Promotion tab`

---

### Task 11: End-to-end run (spec step 7)

**Files:**
- Create: `drafts/findings/promotion-e2e/` (JSON snapshots and `README.md` with the write-up)
- Modify: `progress.md` (record the result and the next action)

This is a live test against Agent Memory, run with the test profile in `.env` and `PROMOTION_ENABLED=true`. It can't be unit-tested.

- [ ] **Step 1: Set up.**
  - Create `PROMOTION_TEAM_SCOPE` (or a lab team scope) from Admin › Access.
  - Grant every test user read on it, and mark one user team admin.
  - Check in Capture that no user is offered the team scope.
- [ ] **Step 2: Save facts as at least 3 test users.**
  - Agreeing facts: "Cobalt Ridge return window is 30 days", some through Claude chat with the Agent Memory plugin and some through Capture.
  - One conflicting fact: 60 days.
  - One unrelated fact.
- [ ] **Step 3: Click Run now and save `GET /promotion`.** Expect the conflict notes in one topic with two values, the unrelated fact in its own topic, and a 30-day candidate at the test threshold.
- [ ] **Step 4: Approve the candidate as the team admin.** Ask "Cobalt Ridge return window" as a member: the team rule shows, and the decision shows who approved it and when.
- [ ] **Step 5: Close the rule.** Ask again: the rule and the closing value are both left out of Search. Check Chat's wording too.
- [ ] **Step 6: Wait about an hour after the first rule (check S7).** List the team scope and confirm it holds only approved rules and closing values.
- [ ] **Step 7: Write it up.** Put timings, counts, how often the full-list call ran, and any wrong topic picks in `README.md`. Record the decisions and next action in `progress.md`, then run `make check`.

---

## Self-review notes

- **Spec coverage.**
  - Settings (§3): Task 1. Tables (§4): Task 2. Grouping (§5.1): Task 5. Agree and disagree, plus self-correction (§5.2): Tasks 1 and 4. Scoring (§6): Tasks 1 and 6. The tab and who sees it (§7): Tasks 3, 8 and 10.
  - Build steps 1 to 7: Tasks 1, 3, 4, 5, 6 and 7, then 8 and 10, then 11. The closing value and Ask skip: Tasks 8 and 9. The one-run lock: Task 7.
  - The last-run line is kept only in memory: `PromotionService.last`.
- **Changes from the spec's table fields.**
  - These columns are added: `statement.norm_value`, `fact_group.rule_entity_type`, `review_item.closed_ref` and `review_item.created_at`.
  - `PROMOTION_JOB_EVERY` becomes `PROMOTION_JOB_EVERY_MINUTES`, to match the tagger's numeric setting.
  - `PROMOTION_MODEL` is set to `claude-haiku-5-5`, the spec's "small Claude model".
- **Not in this plan** (per the spec): the org step and recall counting.
