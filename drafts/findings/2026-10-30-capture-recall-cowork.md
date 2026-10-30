# Capture and recall through Cowork: first run

| | |
|---|---|
| Date | 30 Oct 2026 |
| Tester | Vidyul Narayanan |
| Build plan | Phase 1 (core memory), Claude side: work packages 1.1 and 1.5 |
| Status | Draft |

## What this covers

One person chats in Claude Cowork with the Agent Memory plugin, and we check what Agent Memory stores, what it recalls in a new task, and who else can see it.

All findings come from our own run on 30 Oct 2026, checked against Agent Memory's audit log, traces, entity lookups and search.

## Setup

- **Context:** `membrain-dev-lite` (SurrealDB Cloud, region aws-usw2).
- **Area under test:** `org/spreetail/user/vidyul`, erased just before the run, so it started empty.
- **Plugin:** SurrealDB's `agent-memory` plugin 3.0.0 ([source](https://github.com/surrealdb/ai-claude-plugin), installed copy compared with it on 29 Oct 2026), rebuilt as a personal upload for Cowork.
- **Changes in that build:** the memory URL and the person's key are built into the hook script, because Cowork cannot read Windows environment variables. The per-call time limit is 11 s instead of the plugin's 8 s, and the recall hooks' outer limit is 15 s instead of 12 s.
- **Key:** the person's key reads and writes only `org/spreetail/user/vidyul/*`. It is not in this repo.
- **Claude Code:** its memory hooks were turned off (`AGENT_MEMORY_HOOKS=off`) so only Cowork wrote to the area.
- **Second test person:** area `org/spreetail/user/testuser2`, with its own key limited to that area, used only by scripts.

## What we did and what happened

Times are IST. Messages are quoted as Agent Memory stored them.

| Step | What was sent in Cowork | Result |
|---|---|---|
| 2b-1, new task, 15:38 | `Hi, I am Vidyul. I lead the Agent Memory proof of concept for Spreetail, and our demo is on Tuesday 3 November.` | Saved to the person's area within 10 s. |
| 2b-2, same task, 15:39 | `Acme Logistics ships late on most orders to Reno.` | Saved within 10 s. |
| 2c, new task, 15:40 | `What do you know about me and about Acme Logistics?` | Recall worked. Cowork listed the name, employer, role, demo date and "ships late to Reno". |
| 2d, same task, 15:41 | `Actually, Acme Logistics now ships on time to Reno.` | The exchange was saved, but no stored fact was replaced (finding 2). |
| 2c again, new task, 15:42 | `What do you know about me and about Acme Logistics?` | Recall returned both the old and the new statement. Cowork picked "on time" only because of the word "Actually" (finding 2). |
| 2e, same task, 15:44 | `Our pilot — phase one · starts next week, and the team said “go”.` | Saved with every character intact (finding 6). |
| 2f, script | Searched for all of the above with the second person's key | Nothing found (finding 7). |

Lookups took 3.5 to 9.3 s each, and every exchange was saved.

## What Agent Memory stored

After the run the area held 10 saved message chunks, 8 entities, 2 attribute facts and 19 links.

The entities are `Agent Memory demo`, `Reno`, `Acme Logistics`, `Spreetail`, `Techjays`, `Agent Memory`, `phase one` and `pilot`.

Only three of the six exchanges produced facts, seven in all:

| Exchange | Fact stored | Category |
|---|---|---|
| 2b-1 "Hi, I am Vidyul ..." | first name = Vidyul | identity |
| 2b-1 | the person leads project Agent Memory | context (expires after 7 days) |
| 2b-1 | Agent Memory is a project for Spreetail | context |
| 2b-1 | Agent Memory demo is a demo for Agent Memory | context |
| 2c "What do you know ..." | the person works at Techjays, **taken from Cowork's reply** (finding 4) | identity |
| 2e "Our pilot ..." | phase one: `status = "go"` | context |
| 2e | phase one is part of pilot | context |

All seven came from the chat at trust 0.5.

Nothing else became a fact:

- 2b-2, 2d and the second 2c produced no facts.
- Nothing about Acme shipping late or on time was stored as a fact.
- The demo date, 3 November, was not stored as a fact.
- The other 14 links came from Agent Memory's own elaboration at trust 0.3 (finding 3).

## Findings

### 1. Chat capture and recall work in Cowork

Every exchange was saved to the person's own area, and a new task recalled it without being told again.

This is the core demo path, and it works with the plugin as built for Cowork.

### 2. Statements can stay as chat text and never become facts

"Acme Logistics ships late on most orders to Reno" was not stored as a fact on Acme Logistics; it exists only in the saved message.

So the correction had nothing to replace. Both messages stay searchable, and recall returns both, without timestamps or a "replaced" marker.

In the second recall Cowork chose "on time" only because of the word "Actually". In its own reply it warned that a shorter correction could put the old value in front of the user.

Related: build plan F3, which covers a late past-tense statement becoming current.

### 3. Agent Memory adds links nobody said

Elaboration added 14 links at trust 0.3.

Several are false, for example "Acme Logistics partnered with Spreetail", "Agent Memory demo located in Reno", "Spreetail operates in Reno" and "Acme Logistics participates in pilot".

They are stored beside what the person said, so recall and any job that counts facts must tell them apart (build plan G4).

### 4. Claude's own replies are stored and recalled

Every assistant reply is saved with the user's message, including long commentary such as Cowork's notes on demo risks.

These replies came back in later recalls, and the second recall even returned an earlier answer that still said "ships late" (build plan F1).

Replies also become facts. The person never mentioned Techjays in this run, but Cowork's answer in 2c said "You're Vidyul, at Techjays", and Agent Memory stored "works at Techjays" as a lasting identity fact about the person.

### 5. Lasting facts can be filed to expire

"Leads project Agent Memory" was stored in the `context` category, which expires after 7 days.

The demo date was not stored as a fact at all, although recall still found it in the saved message.

### 6. Special characters work in Cowork

The em dash, middle dot and curly quotes were saved exactly as typed.

The same plugin in Claude Code on Windows rejects such messages, or saves them with the characters turned into "?". That is a Windows command-line encoding problem in the plugin's hook, not in Agent Memory, so Cowork avoids it.

### 7. Isolation between people holds

The second person's key found none of these items, whether searching the person's area or everything it can reach.

In step 1 the same key was refused when it tried to write into the person's area: "write scope `org/spreetail/user/vidyul/` is outside the caller's write region".

The person's key also could not find a note the second person saved in their own area.

### 8. Open: searches by another identity, before the run

Between 15:20 and 15:29 IST, before the first test message, an identity other than the plugin's key searched memory for "Which carrier is late to Reno?" and "Vidyul Narayanan Techjays".

Those searches returned 50 to 62 results while the person's area was still empty, so they read beyond that area.

It may be the Agent Memory connector, which signs in as the user rather than with the area-limited key. If so, Claude in Cowork can search the whole context, which would weaken finding 7 for chat. This needs checking.

### 9. Saves do not share a session

The seven facts came from three different Agent Memory sessions, one per save that produced facts.

The plugin's save hook sends no session id, so Agent Memory starts a new session for each save ([hook source](https://github.com/surrealdb/ai-claude-plugin), `hooks/agent-memory.sh`, checked 29 Oct 2026). One Cowork task therefore never maps to one Agent Memory session (build plan F4).

## For the Tuesday demo

- **Show:** saving, recall in a new task, special characters, and isolation between two people.
- **Avoid, or show on purpose as a finding:** a correction, because recall returns the old and the new value side by side.
- **Explain if asked:** the extra links come from Agent Memory's elaboration, not from the person.

## Next checks

1. Confirm which identity made the 15:20 to 15:29 searches, and whether the connector is enabled in Cowork.
2. Repeat 2b with "Remember that ..." and with a plainer fact, to see when a statement becomes a fact.
3. Confirm F4 inside one task: send several messages in one Cowork task and count the sessions their saves create.
4. Run the "don't save that" check (F2).

## How this was checked

- **Audit log:** `GET /api/v1/{context}/audit` gave each save and lookup with its time and latency.
- **Traces:** `GET /api/v1/{context}/traces/{id}` gave each lookup's query text and how many items it returned. For example, trace `twtrgswjzujne8yx3lzf` is the elaboration that followed the 2e save.
- **Entities and facts:** `GET /entities`, `GET /attributes` and `GET /relations` listed every entity, fact and link with its category, source, trust and session. `POST /lookup` per entity returned only some of them, so the lists are the complete record.
- **Saved messages:** `POST /query` with a lens on the person's area returned the stored chunks with their times.
- **Isolation:** the same searches run with the second person's key.
