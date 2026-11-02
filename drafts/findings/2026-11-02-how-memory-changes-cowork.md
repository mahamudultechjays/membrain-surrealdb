# How memory changes: corrections, repeats, hedges, past tense and Claude's words

| | |
|---|---|
| Date | 2 Nov 2026 |
| Tester | Vidyul Narayanan |
| Build plan | Phase 1 (core memory), work package 1.3, with F1 to F4 from 2.2 |
| Status | Draft |

## What this covers

One person sends nine short messages in Claude Cowork and we check how Agent Memory creates, repeats, replaces and drops facts.

All findings come from our own run on 2 Nov 2026, checked against Agent Memory's audit log, fact and link lists, lookups and search.

## Setup

The setup is the same as the [30 Oct run](2026-10-30-capture-recall-cowork.md): context `membrain-dev-lite`, area `org/spreetail/user/vidyul`, the personal Cowork build of the `agent-memory` plugin 3.0.0, and Claude Code hooks off.

The area was **not** erased first. The test uses names that were not yet in memory (Kestrel Freight, Pinewood Couriers, Boise, Portland), so every new item can be told apart from the 30 Oct data.

## What we did and what happened

Times are IST. Messages are quoted as Agent Memory stored them.

| Step | Sent in Cowork | What Agent Memory did with facts |
|---|---|---|
| 3a, new task, 10:16 | `Remember that Kestrel Freight ships late on most orders to Boise` | Created Kestrel `shipping_performance` = "ships late on most orders to Boise", knowledge, confidence 1.0. |
| 3b, same task, 10:19 | `Pinewood Couriers is our backup carrier for Boise` | Created Pinewood `carrier_role` = "backup carrier for Boise", knowledge. |
| 3c, new task, 10:20 | `Remember that Kestrel Freight ships late on most orders to Boise.` | Nothing. No new fact, no count, and the 3a fact was unchanged. |
| 3d, same task, 10:22 | `Kestrel deliveries to Boise are always behind.` | Replaced the 3a fact with "deliveries to Boise are always behind" (`supersedes` the 3a id). |
| 3e, new task, 10:27 | `Update: Kestrel Freight now ships on time to Boise. The earlier note about late shipments is out of date.` | Removed the 3d fact and stored no new value. Kestrel has no shipping fact now. |
| 3f, 10:40 | `I think Pinewood Couriers might raise its prices next month, but I am not sure.` | Created Pinewood `price_change_status` = "might raise prices", confidence 0.4, `validFrom` 1 Dec 2026, context. |
| 3g, new task, 10:44 | `Back in March, Pinewood Couriers charged 7 dollars per parcel. As of October it charges 5 dollars per parcel.` | Created `price_per_parcel` = "5 dollars", which `supersedes` an unreadable earlier fact. No dates, context. |
| 3h, 10:56 | `What is a typical delivery time from Boise to Portland for a ground parcel?` | Created two facts from Cowork's reply: Portland `distance_from_boise` = "about 430 miles …" and demo `date` = "tomorrow". |
| 3i, new task, 11:35 | `My test locker code is 4471. Do not save that.` | No fact. The chat passage with the code was saved and is searchable. |

The locker code is made up for the test.

Every exchange was saved as a chat passage within about 10 s, and every fact came from chat at trust 0.5.

## Findings

### 1. Extraction is inconsistent for the same kind of sentence

A plain statement became a fact in 3b, but an equally plain one on 30 Oct ("Acme Logistics ships late on most orders to Reno") did not.

"Remember that" is not what makes a fact, but it does make something else: 3a also created an **instruction** record, `remember_kestrel_freight_delay`, shown in `GET /state` and `GET /profile` (finding 4).

### 2. An exact repeat leaves no trace on the fact

The 3c repeat added nothing: the fact kept its single source, confidence and importance, with no count.

Promotion (build plan 5.2, confirmation finder) cannot read confirmations from the fact, so it has to rebuild them from chat passages.

### 3. A rewording replaces the fact, and can change its meaning

In 3d, "always behind" replaced "late on most orders", so a stronger claim silently overwrote a weaker one.

Each rewording resets the fact instead of confirming it, which also works against promotion.

### 4. An explicit correction can erase a fact without storing the new value

After 3e the structured memory holds nothing about Kestrel's shipping, while the chat says "now on time".

The current answer survives only because search ranks the update passage above the three "late" passages.

Worse, the 3a instruction "Remember that Kestrel Freight ships late on most orders to Boise" was not touched by the correction, so the person's profile still tells the agent the old value.

This is worse than the 30 Oct result (finding 2 there), where no fact existed to lose.

### 5. Replaced values cannot be read back

The new fact carries `supersedes` with the old id, but `GET /attributes`, the lookup and `GET /attributes/{id}` (404) do not return the old value.

So "kept as history" holds only as a pointer, and "what was the price in March?" works only through chat search.

### 6. Past and present are ordered correctly (F3)

In 3g the October price became current and the March price did not.

The risk F3 describes, a late past-tense statement becoming current, did not happen in this run.

### 7. Hedges are marked with lower confidence

"I think … might … not sure" became a fact with confidence 0.4 and importance 0.5, against 1.0 and 0.8 for plain statements.

Trust stayed at 0.5, so trust records the source and confidence records the speaker's certainty; phase 5 scoring must pick which to use.

The hedge also produced an open **uncertainty** record in `GET /uncertainty`: "The user is not sure whether Pinewood Couriers will raise prices next month."

### 8. Relative dates are handled inconsistently

"Next month" became `validFrom` 1 Dec 2026 and "tomorrow" became `validFrom` 3 Nov 2026, but "March" and "as of October" got no dates.

The "tomorrow" fact keeps the word itself as its value, so anything that reads the value without the date shows "tomorrow".

A future `validFrom` can also hide a fact that is true now from a "currently valid" filter.

### 9. Claude's words become facts with the same trust as the person's (F1)

In 3h Agent Memory stored a road distance from Cowork's answer as a lasting knowledge fact, and the demo date as "tomorrow".

Nothing marks these as coming from Claude, while the answer the person asked for (1–2 business days) was not stored.

### 10. "Don't save that" is half honoured (F2)

No fact was made from 3i, but the plugin saved the whole exchange, so the code is searchable in the person's area.

Cowork told the person it would not save the code and warned that Agent Memory may already have stored it.

### 11. Elaboration ties every new name to old ones

Each new carrier or city got the same made-up links to Acme, Reno, the pilot and phase one, 16 links in all at trust 0.3.

This extends finding 3 from 30 Oct; elaboration also ran by itself at 09:11 IST, before any test message, and added 3 links.

### 12. One task still maps to many sessions (F4)

The 3a and 3b facts, sent in one task, sit in two different Agent Memory sessions.

This confirms finding 9 from 30 Oct inside a single task.

### 13. The profile files facts under the wrong headings

`GET /profile` lists the Portland road distance and Pinewood's backup-carrier role under `preferences`, although neither is a preference.

It also lists "demo date = tomorrow" under `dynamic`, so a prompt built from the profile would carry a wrong relative date after 2 Nov.

### 14. Events are stored as actions

`GET /state` holds three dated actions: "Agent Memory demo takes place tomorrow" (dated 3 Nov, from Cowork's 3g reply), "Phase one of the pilot starts next week" and "demo scheduled for Tuesday 3 November" (both from 30 Oct).

So the demo date was stored on 30 Oct after all, as an action rather than a fact; the 30 Oct findings are corrected to match.

## Other observations

- **Duplicate links:** 3e added a second "Kestrel operates in Boise", filed as context while the 3a copy is knowledge.
- **Lasting facts as context:** a price (3g) was filed as context, which expires after 7 days.
- **Recall timing:** lookups took 3.6 to 8.6 s, close to the 11 s limit in the Cowork build.
- **Double start recall:** each new task logged two start-of-task recalls, about 7.5 s each.
- **Missing recall:** no recall was logged for the 3d message, although the save was.
- **Entities outlive an erase:** the Spreetail entity is dated 10 Oct and Techjays 29 Oct, after the 30 Oct area erase; to check in 1.5.

## For the Tuesday demo

- **Show:** a new fact, a hedge stored with lower confidence, and a repeat that does not duplicate.
- **Avoid, or show on purpose as a finding:** corrections and rewordings, which replace or erase facts and lose the old value.
- **Avoid:** asking general questions, since Claude's answers become facts.

## Next checks

1. Repeat 3e with a correction worded as a plain statement ("Kestrel Freight ships on time to Boise") to see whether a value is stored.
2. Send the same sentence three times in new tasks to measure extraction consistency (1.3 done-when).
3. Find out whether replaced facts can be read through MCP `inspect` or another endpoint.
4. Forget the 3i passage in 1.5, and check whether erasing an area removes entities.

## How this was checked

- **Audit log:** `GET /api/v1/{context}/audit` gave each recall and save with its time and latency.
- **Facts and links:** `GET /attributes` and `GET /relations`, filtered to items created during the run, with `supersedes`, confidence, `validFrom`, category and session.
- **Lookups:** `POST /lookup` per entity, and `GET /attributes/{id}` for replaced facts.
- **State, profile and uncertainty:** `GET /state` (facts, links, actions and instructions per category), `GET /profile` (what the agent is given about the person) and `GET /uncertainty`.
- **Saved messages:** `POST /query` with a lens on the person's area.
- Our own checks also appear in the audit log as recalls; they are left out of the timings above.
