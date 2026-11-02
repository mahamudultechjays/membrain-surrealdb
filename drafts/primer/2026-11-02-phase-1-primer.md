# Phase 1 primer: how Agent Memory behaves

| | |
|---|---|
| Date | 2 Nov 2026 |
| Author | Vidyul Narayanan |
| Build plan | Phase 1 (core memory), work package 1.6: primer and gate |
| Status | Draft for review |

## What this is

One section per concept, written from our own runs on 30 Oct and 2 Nov 2026 in Claude Cowork and by script.

Each section says what Agent Memory does, what it means for our build, and which findings file has the evidence.

The findings files are in `drafts/findings/`:

| File | Covers |
|---|---|
| [2026-10-30-capture-recall-cowork.md](../findings/2026-10-30-capture-recall-cowork.md) | 1.1: first chat, recall, isolation by key |
| [2026-11-02-how-memory-changes-cowork.md](../findings/2026-11-02-how-memory-changes-cowork.md) | 1.3: repeats, rewording, corrections, hedges, past tense, Claude's words |
| [2026-11-02-what-gets-stored-cowork.md](../findings/2026-11-02-what-gets-stored-cowork.md) | 1.2: record types, categories, instructions, labels, keys, the `context` tool |
| [2026-11-02-what-memory-does-itself.md](../findings/2026-11-02-what-memory-does-itself.md) | 1.4: elaboration, reflection, consolidation |
| [2026-11-02-forgetting-isolation-cowork.md](../findings/2026-11-02-forgetting-isolation-cowork.md) | 1.5: forget, purge, area erase, the Cloud connector, isolation |

## 1. Where memory lives and who can reach it

Memory sits in one Context (`membrain-dev-lite`), split into areas such as `org/spreetail/user/vidyul`.

An area-limited key reads and writes only its own area: reads, writes, reflection, consolidation and elaboration all stayed inside it in our tests.

The SurrealDB Cloud connector in Cowork is different: it signs in as the person, and for an organisation admin it read every context in the organisation, including another person's.

**For the build:** isolation between people depends on every caller using an area-limited key; an admin's own sign-in bypasses it.

## 2. What gets stored

Every exchange the plugin saves becomes a **chat passage**, split if long; the passages are the most complete record.

From each passage, extraction may also make:

| Record | Example from our runs |
|---|---|
| Fact (attribute) | Harbor Lane warehouse · `return_window` = "30 days" |
| Link (relation) | Pinewood Couriers operates in Boise |
| Dated action | "self is reviewing the Harbor Lane warehouse layout today", dated 2 Nov |
| Instruction | "Always answer in short bullet points, with no more than five bullets." |
| Uncertainty | "The user is not sure whether Pinewood Couriers will raise prices next month." |

Facts, links and actions carry a category: identity (only the first name in our runs), knowledge (lasting facts) or context (expires after 7 days).

Extraction is inconsistent: the same kind of plain sentence became a fact once and nothing another time, and lasting facts such as a price were filed as context.

**For the build:** treat the passages as the record of what was said, and the extracted records as an index that may be incomplete.

## 3. Where a record came from

Every record carries a source:

| Source | Trust | Who made it |
|---|---|---|
| `turn` | 0.5 | Extraction from chat, from the person's words **or Claude's reply** |
| `upsert` | 0.95 | A structured write, such as our own scripts |
| `elaboration` | 0.3 | Agent Memory's own guesses, with no session and no labels |

Claude's replies are stored and extracted like the person's words: a road distance from Cowork's answer, "works at Techjays" and restated instructions all became records at trust 0.5.

Elaboration made 49 of the 59 links in the area, nearly all false, such as "Spreetail operates in Reno".

**For the build:** filter on source; nothing yet separates the person's words from Claude's.

## 4. How memory changes

| What was said | What happened |
|---|---|
| The same sentence again | Nothing: no duplicate and no count |
| The same fact in other words | The fact was replaced, and "most orders" became "always" |
| "Update: … now ships on time" | The old fact was removed and **no new value stored** |
| A past and a current price | The current price kept; the past price unreadable |
| "I think … might …" | Stored with confidence 0.4 and an uncertainty record |
| A changed instruction | Added beside the old ones, which stayed |

Replaced values point to their predecessor by id, but no endpoint we use returns the old value.

**For the build:** promotion cannot count confirmations from facts (repeats leave no trace and rewordings reset), and corrections need a check that a new value was actually stored.

## 5. What memory does by itself

**Elaboration** adds guessed links after writes, and once with no new message at all.

**Reflection** answers from chat passages, sometimes better than the facts (it knew Kestrel now ships on time after the fact was erased), but it also adds claims nobody made; with a personal key it saves nothing.

**Consolidation** reported new observations we cannot read through any endpoint, with proof count 1, and merged none of the duplicates.

**For the build:** none of the three produces something we can rely on without a filter or a review.

## 6. What reaches the agent

The plugin's recall hook calls `recall`, which returns the top matches: in 4f and 4g only chat passages, in 6c facts as well.

The plugin introduces what it injects as "background context, not instructions", so stored instructions are not applied as instructions.

The `context` tool returns the person's facts, all instructions and the passages in one block, but took about 10 s and passes on stale and contradictory instructions as they stand.

**For the build:** the cited-answer service (2.4) should build its own context from facts and passages rather than rely on the plugin's recall.

## 7. Forgetting

| Action | What it removed | Audited |
|---|---|---|
| `forget` (soft), area key | One chat passage; never a fact, in four wordings | No |
| `forget` with `purge`, Cloud connector | One chat passage, matched by wording, with no area limit | No |
| Area erase (`POST /scopes/forget`), area key | Everything in that area, entities included; nothing elsewhere | No |

Facts extracted from a forgotten passage stay and keep answering, and the agent's answer stores them again.

An agent chose `purge` by itself when asked only to "forget".

**For the build:** forgetting a person's statement needs us to find and remove its facts too, and we need our own log of erasures.

## Gate: result for each M check

The build plan names M1 to M14 by work package but not one by one; this mapping follows the order of topics in each WBS line and should be confirmed against Binu's list.

| Check | Topic (from the WBS) | Result | Where |
|---|---|---|---|
| M1 | First chat, areas and keys | Pass: a chat is recalled in a new task; the other key cannot see it | 30 Oct, findings 1, 7 |
| M12 | Sessions | Finding: every save starts a new session, so a task never maps to one session | 30 Oct finding 9; 2 Nov (changes) finding 12 |
| M2 | Payload shapes | Pass: triples, full extraction and chat saves each tested with one example | What gets stored, script checks |
| M3 | Categories and 7-day expiry | Partly: categories recorded; expiry check skipped | What gets stored, findings 6–8 |
| M4 | Preferences and instructions | Finding: stored as instructions and as facts; old ones never replaced | What gets stored, findings 1, 3, 4 |
| M11 | Labels and keys | Pass with gaps: labels persist and filter; elaboration drops them; idempotency keys rerun repeats | What gets stored, findings 10–12 (script checks) |
| M5 | Extraction | Finding: inconsistent; corrections can erase without replacing; Claude's words extracted | How memory changes, findings 1–4, 9 |
| M9 | History and time | Finding: old values unreadable; relative dates resolved inconsistently | How memory changes, findings 5, 8 |
| M10 | Trust and confidence | Pass: trust by source (0.95, 0.5, 0.3); hedges get lower confidence | How memory changes, finding 7 |
| M6 | Elaboration | Finding: mostly false guesses, filterable by source | What memory does by itself, findings 1–3 |
| M7 | Consolidation | Finding: writes unreadable observations, merges nothing | What memory does by itself, findings 7, 8 |
| M8 | Reflection | Finding: useful answers with invented claims; cannot persist with a personal key | What memory does by itself, findings 4–6 |
| M13 | Forget, purge, delete area (T-1) | Finding: forget removes passages not facts; area erase is complete; nothing audited | Forgetting, findings 3–10, 12, 13 |
| M14 | Second identity, scope leak (T-2) | Pass for keys; fail for an admin's Cloud connector sign-in | Forgetting, findings 1, 11 |

## Gate: G4 decision (proposed)

**Proposed rule:** our jobs and answers use records with source `turn` or `upsert`, leave out `elaboration`, never store `reflect` output, and ignore consolidation until it can be read.

**Open part:** `turn` mixes the person's words with Claude's; until that can be told apart, a fact from chat is shown as "from conversation", not "the person said".

This needs sign-off from Binu before phase 2.

## Asks for SurrealDB

1. Return the replaced value of a superseded fact, and record a new value when a correction is extracted.
2. Mark records extracted from assistant turns, or let us switch that off.
3. Let `forget` reach facts, and audit forget, purge and area erase.
4. Explain which key types may persist reflections, and how to read consolidation observations.
5. Confirm whether the Cloud connector's whole-organisation reach for admins is intended.

## How this was written

Every statement here is taken from the five findings files listed above, each of which records its own method and sources.
