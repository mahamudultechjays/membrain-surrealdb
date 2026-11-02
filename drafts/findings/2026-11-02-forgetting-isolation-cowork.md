# Forgetting and isolation: what Cowork can reach and erase

| | |
|---|---|
| Date | 2 Nov 2026 |
| Tester | Vidyul Narayanan |
| Build plan | Phase 1 (core memory), work package 1.5 (M13, M14; T-1, T-2) |
| Status | Draft; 6a recorded, the remaining step 6 checks still to run |

## What this covers

We check how memory is forgotten and whether people stay apart, starting with a request to forget made in Cowork chat.

6a comes from our own run on 2 Nov 2026, checked against Agent Memory's audit log and search, and against the tool-call log Cowork showed for the turn.

## Setup

The setup is the same as the [30 Oct run](2026-10-30-capture-recall-cowork.md).

In addition, the **SurrealDB Cloud connector** was enabled in Cowork. It manages organisations and contexts and signs in as the person, who is an admin of the Spreetail organisation.

## What we did and what happened

Times are IST. Organisation and principal ids are left out.

| Step | Sent in Cowork | Result |
|---|---|---|
| 6a, new task, 13:26 | `Forget my test locker code.` | Cowork used the SurrealDB Cloud connector, not the plugin, and permanently erased the 3i passage. Its reply said it chose the irreversible option "because this is a code". |

The connector calls Cowork made, in order:

| # | Call | Result |
|---|---|---|
| 1 | List organisations | Spreetail (role admin) and a personal organisation |
| 2 | List contexts in Spreetail | Four contexts: membrain-dev-lite, membrain-devin-lite, membrain-stephen-test, membrain-tj-test |
| 3 | `recall` "test locker code" in each of the four contexts | Results came back from contexts other than ours, including another person's chats in membrain-stephen-test |
| 4 | `recall` in membrain-dev-lite | About 93,000 characters from the whole context, including other test areas and the 3i passage |
| 5 | `forget`, purge, "Vidyul's test locker code 4471" | `deleted: 0` |
| 6 | `forget`, purge, "My test locker code is 4471" | `deleted: 1`, with an empty trace id |
| 7 | `recall` (bm25) "test locker code 4471" | No match for "4471" remained |

Cowork also ran two shell commands in its own sandbox, after the person approved them: a search of a saved tool result for "locker", and deleting that saved result.

## Findings

### 1. The Cloud connector reaches every context in the organisation

Signed in as an organisation admin, Cowork read memory from all four contexts, including one holding another person's chats.

Area isolation holds for keys (the plugin key and the second test person's key, [30 Oct findings](2026-10-30-capture-recall-cowork.md) 7), but not for an admin's own sign-in through this connector.

### 2. The 30 Oct searches beyond the area came from this connector

The 30 Oct searches that returned 50 to 62 results from beyond the person's area match this pattern: whole-context reads by the person's own sign-in rather than the area-limited key.

This answers open finding 8 of the 30 Oct run, by matching the pattern rather than by the audit log, which does not name the identity.

### 3. An agent chose an irreversible erase by itself

Asked only to "forget", Cowork picked `purge`, which also removes history, and said so after doing it.

Nothing asked the person to confirm the permanent option.

### 4. Purge is matched by wording, across the whole context

The same intent deleted nothing with one wording and one record with another.

The call carried no area, so with an admin sign-in a looser wording could have erased matching memories from other people's areas.

### 5. Forget and purge leave no trace

Both `forget` calls returned an empty trace id, and the audit log has no entry for them, only the searches before and the save after.

There is no record afterwards of who erased what.

### 6. The erase worked for this passage

After the purge, an exact search for the 3i text found nothing, and the new 6a passage does not contain the code.

## Decision taken

Turn the SurrealDB Cloud connector off in Cowork for the rest of testing, so only the plugin's area-limited key touches memory (2 Nov 2026, Vidyul).

## How this was checked

- **Cowork's tool-call log** for the 6a turn, shared by the person.
- **Audit log:** `GET /audit`, which showed the searches and the plugin's save but no forget.
- **Search:** `POST /query` for the exact 3i text, after the purge.
