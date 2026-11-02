# What memory does by itself: elaboration, reflection and consolidation

| | |
|---|---|
| Date | 2 Nov 2026 |
| Tester | Vidyul Narayanan |
| Build plan | Phase 1 (core memory), work package 1.4 (M6 to M8), input to gate decision G4 |
| Status | Draft |

## What this covers

We check what Agent Memory writes or works out without being asked to, and how a job can tell those records apart from what the person said.

All checks ran by script on 2 Nov 2026 with the person's key, against the area `org/spreetail/user/vidyul` as left by the [30 Oct run](2026-10-30-capture-recall-cowork.md) and the 2 Nov runs on [how memory changes](2026-11-02-how-memory-changes-cowork.md) and [what gets stored](2026-11-02-what-gets-stored-cowork.md).

## Where the records came from

The area held 12 facts and 59 links before consolidation.

| Source kind | Trust | Session id | Labels | Facts | Links |
|---|---|---|---|---|---|
| `turn` (chat, the person's or Claude's words) | 0.5 | Yes | Only if the write set them | 10 | 10 |
| `upsert` (structured write by script) | 0.95 | Yes | Yes | 2 | 0 |
| `elaboration` (Agent Memory's own guesses) | 0.3 | No | Never | 0 | 49 |

## What we did and what happened

| Check | Call | Result |
|---|---|---|
| Elaboration count | `GET /relations` | 49 links from 13 elaboration runs, all trust 0.3 and confidence 0.3, none with a session or labels. 37 are context, 11 knowledge, 1 identity. |
| Reflection, no saving | MCP `reflect`, 3 questions | Each answer took 9.8 to 14.1 s and cited chat passages as evidence. |
| Reflection, saving | MCP `reflect` and REST `POST /reflect` with `persist: true`, 4 calls | `persisted_attributes` was empty every time; nothing was written. |
| Consolidation | REST `POST /consolidate` | 200 in 13.2 s: 9 created, 0 updated, 0 superseded, `dryRun: false`. The fact, link, instruction, action and entity counts did not change. |

## Findings

### 1. Most of the graph is Agent Memory's guesses

49 of 59 links came from elaboration, and nearly all are false, for example "Spreetail operates in Reno", "Kestrel Freight collaborates with Acme Logistics" and "Lab Carrier M11 operates in Portland".

Each new entity is linked to whatever is already in the area, so the share of guessed links grows with every new name.

### 2. Elaboration can be filtered out by its source

Every elaboration link has `source.kind` = `elaboration`, trust 0.3 and no session id, so a job can drop them with one rule.

Labels do not help, because elaboration never copies the labels of the write that set it off.

### 3. Elaboration also runs without a new message

At 09:11 IST on 2 Nov, before any test message that day, elaboration added 3 links.

It is not clear what set it off, so the guessed links can change between two reads with no new input.

### 4. Reflection answers from chat passages and resolves some conflicts

Asked about Kestrel, reflection said the 2 Nov update ("now ships on time") replaced the earlier delays, which the fact list cannot say because that fact was erased.

Asked about answer format, one run described the bullet and paragraph requests as conflicting, while another said the paragraphs request was the latest.

### 5. Reflection adds claims nobody made

Reflection called Kestrel Freight the "primary" carrier for Boise; nobody said so, it followed only from Pinewood being the backup.

It did not repeat the elaboration links, so its guesses come from its own reasoning, not from the guessed graph.

### 6. Reflection cannot save with a personal key

`persist: true` wrote nothing in four calls, through MCP and REST.

The [REST reference](https://surrealdb.com/docs/agent-memory/reference/rest-api) says persist stores lower-trust derived facts "when permitted by key type" (checked 2 Nov 2026), so a personal key appears not to be permitted; this is a guess from the docs, not confirmed.

### 7. Consolidation writes records we cannot read, and merges nothing

`POST /consolidate` reported 9 new persisted observations restating current facts (phase one status, Pinewood's role and prices, the Portland distance, the Harbor Lane return window and others), each listed with `proofCount` 1 in the outcomes shown.

None of them appears in `GET /attributes`, `GET /state` or MCP `inspect`, and its trace id returned 404, so their effect cannot be checked.

The duplicate link, instructions and actions from the earlier runs were left as they were.

### 8. Proof counts do not reflect repeats

The Kestrel shipping fact was stated three times in step 3, but it no longer exists, and every observation consolidation made has a proof count of 1.

Promotion (build plan 5.2) cannot take its confirmation counts from consolidation as it behaves here.

## Input to G4: telling Agent Memory's records from what people said

| Source kind | What it is | Treat as |
|---|---|---|
| `turn` | Extracted from chat; mixes the person's and Claude's words (F1) | What was said, at trust 0.5, unverified as to speaker |
| `upsert` | Written by our own jobs with labels | Authoritative for that job, trust 0.95 |
| `elaboration` | Agent Memory's guesses | Leave out of answers, counts and promotion |
| `reflect` | Not written with a personal key | Show only as a labelled suggestion, never store |
| consolidation | Not readable through the APIs we use | Ignore until it can be read |

The open part of G4 is the `turn` row: nothing separates the person's words from Claude's.

## For the Tuesday demo

- **Show:** reflection answering "is Kestrel late?" correctly from the chat history, with its evidence.
- **Avoid:** showing the link graph unfiltered, since most of it is made up.

## Next checks

1. Find out what started the 09:11 IST elaboration run.
2. Ask SurrealDB which key type may persist reflections, and how to read consolidation observations.

## How this was checked

- **Links and facts by source:** `GET /relations` and `GET /attributes`, grouped by `source.kind`, trust, session and labels.
- **Reflection:** MCP `reflect` and REST `POST /reflect`, timed by script.
- **Consolidation:** REST `POST /consolidate`, with counts of facts, links, instructions, actions and entities read before and after.
- **Entity detail:** MCP `inspect` on `entity:organisation/Pinewood Couriers`.
