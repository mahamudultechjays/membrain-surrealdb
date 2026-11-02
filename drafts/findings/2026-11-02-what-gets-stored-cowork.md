# What gets stored: instructions, preferences, facts about the person, context and policy

| | |
|---|---|
| Date | 2 Nov 2026 |
| Tester | Vidyul Narayanan |
| Build plan | Phase 1 (core memory), work package 1.2 (M2 to M4) |
| Status | Draft; the 7-day expiry check (M3) is still to run |

## What this covers

One person sends eight short messages in Claude Cowork, each a different kind of statement, and we check which record type and category Agent Memory gives each, and what Cowork's recall uses.

All findings come from our own run on 2 Nov 2026, checked against `GET /state`, `GET /profile`, `GET /uncertainty`, the fact and link lists, the audit log and recall traces.

## Setup

The setup is the same as the [30 Oct run](2026-10-30-capture-recall-cowork.md), and the area kept the data from the [step 3 run](2026-11-02-how-memory-changes-cowork.md).

New names (Harbor Lane warehouse) keep the new records apart from earlier ones.

## What we did and what happened

Times are IST.

| Step | Sent in Cowork | What Agent Memory stored |
|---|---|---|
| 4a, new task, 11:41 | `Please always answer me in short bullet points, with no more than five bullets` | Instruction `short_bullet_points_limit_five`. Nothing else. |
| 4b, same task, 11:45 | `I prefer metric units, so give distances in kilometres.` | Instruction `metric_units`, and a fact on the person, `preferred_measurement_system`, category knowledge. |
| 4c, new task, 11:47 | `I usually work from home on Fridays.` | Fact on the person, `work_from_home_schedule` = "usually on Fridays", knowledge; and an undated context action "Vidyul mentioned that they usually work from home on Fridays". |
| 4d, same task, 11:50 | `Today I am reviewing the Harbor Lane warehouse layout.` | Context action dated 2 Nov 2026, a new context entity Harbor Lane warehouse, and 3 elaboration links at trust 0.3. No fact. |
| 4e, same task, 11:54 | `Our standard return window for Harbor Lane is 30 days.` | Fact Harbor Lane warehouse `return_window` = "30 days", knowledge. Nothing else. |
| 4f, new task, 11:56 | `Never mention competitor names in your answers.` | Instruction `no_competitor_names`. Cowork's reply was plain sentences, not bullets. |
| 4g, new task, 12:00 | `How should you format your answers for me, and what am I working on today?` | Recall returned only saved chat passages, so Cowork built its answer from chat text, not from the stored instructions, facts or entities. The answer was right on bullets, competitors, today's task and the demo, but left out metric units. Its reply then added two duplicate instructions, a third copy of the bullet rule as a fact, two duplicate actions and a duplicate link, and replaced demo `date` "tomorrow" with "Tuesday 3 November". |
| 4h, new task, 12:14 | `Stop using bullet points. Plain paragraphs are fine now.` | New instruction `format_paragraphs`. Both bullet instructions stayed; the bullet fact from 4g was removed with no replacement. |

## Findings

### 1. Requests about how to answer become instruction records

Formatting (4a), units (4b) and a topic to avoid (4f) each became an instruction, the category the [memory categories page](https://surrealdb.com/docs/agent-memory/index/mental-model/memory-categories) describes (checked 2 Nov 2026).

"Remember that …" also becomes an instruction, which is how the stale Kestrel instruction from step 3 arose.

### 2. In 4f and 4g, recall returned chat passages but no instructions

Both recalls in 4g returned only saved chat passages, 26 of them, which was every passage in the area including the locker code from step 3.

In this run Cowork did not apply all the stored instructions: in 4f it did not use bullets, and in 4g it left out metric units.

The glossary says instructions are "applied at prompt assembly", but the plugin's hooks only inject recall results ([plugin source](https://github.com/surrealdb/ai-claude-plugin), `hooks/agent-memory.sh`, checked 29 Oct 2026).

### 3. Changing an instruction adds one and keeps the old ones

After 4h the area holds "write in plain paragraphs" beside two "short bullet points" instructions.

Nothing marks the old ones as replaced, so the agent receives contradictory instructions; this matches the Kestrel instruction left behind by the step 3 correction.

### 4. A preference is stored twice, and the copies change differently

4b produced an instruction and a fact; in 4h the fact copy of the bullet rule was removed while both instruction copies stayed.

Any job that reads preferences has to reconcile two record types that are not linked.

### 5. Claude repeating a rule stores it again (F1)

Cowork's 4g answer restated the rules, and Agent Memory stored them as new instructions with new labels (`formatting_preference`, `competitor_mentions`) and a new fact.

Eight messages left seven instructions, of which three rules are distinct and one is stale.

### 6. Facts about the person go to knowledge, not identity

Only the first name is identity; the work-from-home habit and the units preference are knowledge.

The [memory categories page](https://surrealdb.com/docs/agent-memory/index/mental-model/memory-categories) lists identity as "stable facts about the principal" (checked 2 Nov 2026), so the run does not match the description.

### 7. "Today I am …" is filed as dated context, as described

4d became a context action dated 2 Nov with no lasting fact, which will expire with the working set.

The current task appears only in `/state` actions, not in the profile.

### 8. A stated policy is a lasting knowledge fact

4e became `return_window` = "30 days" in the knowledge category with no side effects.

This is the shape the phase 4 returns-window demo needs; but its entity, Harbor Lane warehouse, was created in the context category, so the entity may expire before its fact.

### 9. The profile's headings do not match its contents

`preferences` holds the Harbor Lane return window, the Portland road distance and Pinewood's carrier role, none of which is a preference.

The real preferences (units, working pattern) appear under `selfFacts`, and `static` stays empty.

## Script checks: labels, keys and the context tool

Run by script on 2 Nov 2026 with the person's key, on a made-up entity, Lab Carrier M11, in the person's area.

| Check | Call | Result |
|---|---|---|
| Labels on a structured write | MCP `remember`, `infer: "triples"`, labels `test=m11`, `node=inbound_receiving` | Both labels stored on the fact. Source `upsert`, trust 0.95, confidence 0.95. |
| Same triple again | Same call | No new row; the fact is unchanged. |
| New value, same key | `on_time_rate` 92 → 88 percent | The new fact `supersedes` the old one, as in chat. |
| Idempotency key, same body twice | REST `POST /facts` with `Idempotency-Key` | Both 200. The second response has a new session id and no attributes, so the request ran again and was deduplicated by content rather than answered from a stored response. |
| Idempotency key, different body | Same key, depot Modesto | 409, "Idempotency-Key already used with a different request body". |
| Labels on a full extraction | MCP `remember`, `infer: "full"`, label `test=m11b` | The label is on the chat passage and on the link from the text; the entities carry no labels. |
| Label filter | `POST /query` with `labels` | Returns only labelled facts and passages, plus the unlabelled entities they mention. |
| MCP `context` tool | `context` on the person's area | Returns one rendered block with the person's facts, "preferences", current context, **all seven instructions** and relevant passages. |

### 10. Labels and keys work for structured writes, but elaboration drops them

Labels written with a fact come back on the fact and work as a query filter, which is what the VCT node tags (3.1) and test runs need.

The 13 elaboration links made from the labelled writes carry no labels, so a label filter alone hides them while unfiltered reads still mix them in.

### 11. Structured writes get a higher trust than chat

A triples write is stored with source `upsert` at trust 0.95, against 0.5 for chat and 0.3 for elaboration.

That gives jobs a way to write facts the person stated in a form the review list can rank above chat-derived ones.

### 12. The idempotency key rejects conflicts but does not replay

The [REST reference](https://surrealdb.com/docs/agent-memory/reference/rest-api) says the same key within 24 hours "returns the stored response" (checked 2 Nov 2026); here the repeat ran again under a new session.

The data stayed correct because the content was deduplicated, but each retry still creates a session and a turn.

### 13. The `context` tool returns what the plugin's recall leaves out

`context` returns the facts about the person, the instructions and the passages in one block; the plugin calls `recall` instead, which returned only passages in 4g.

The plugin also introduces what it injects as "background context, not instructions" (`hooks/agent-memory.sh`), so even a recalled instruction is framed as something not to follow.

Switching the hook to `context` is a small change in the personal Cowork build, allowed under the PoC's workaround rule; but it took 9.8 to 10.6 s and returned about 21,600 characters whatever `k` was, close to the build's 11 s limit.

It would also pass on the contradictory and stale instructions from findings 3 and 5 as they stand.

## Other observations

- **Recall count varies:** most messages logged two recalls of 7 to 9 s each, 4a logged one, and a same-task message (4d) also logged two.
- **Elaboration** added made-up links only for the new warehouse entity (4d), placing it in Portland because Portland was the latest city in memory.
- **A Claude reply fixed a value a Claude reply broke:** demo `date` "tomorrow" (from 3h) was replaced by "Tuesday 3 November" from Cowork's 4g answer.

## For the Tuesday demo

- **Show:** a formatting instruction, and `GET /state` showing it as an instruction record.
- **Avoid:** changing an instruction, and asking Claude to repeat the rules, both of which pile up contradictory records.
- **Explain if asked:** Cowork follows rules from recalled chat text, not from the instruction records.

## Next checks

1. Run the 7-day expiry check after 15:40 IST on Fri 6 Nov: the 30 Oct context facts, links and actions, their importance, and whether the Harbor Lane entity outlives its knowledge fact.
2. Try the Cowork build with the recall hook calling `context` instead of `recall`, and a longer time limit; repeat 4g.
3. Remove the Lab Carrier M11 test records in the 1.5 forget checks.

## How this was checked

- **Records by type:** `GET /state` gave facts, links, actions and instructions per category, and `GET /uncertainty` the open uncertainties.
- **What the agent is given:** `GET /profile` and the recall traces (`GET /traces/{id}`) for the 4g recalls.
- **Facts and links:** `GET /attributes` and `GET /relations`, filtered to items created during the run.
- Our own checks also appear in the audit log as recalls; they are left out of the timings above.
