# 08 — `actiontrack done <id>`

Status: done
Blocked by: 06
Requirements: FR-14, FR-10, FR-11

## Problem Statement

Work often gets finished between meetings, and nobody will write a new note just to tick it off. Without a direct way to close an item, finished work keeps showing up as open or overdue and keeps generating reminders, which makes people stop trusting the tracker.

## Solution

`actiontrack done <id>` marks an Action Item Done immediately and permanently: re-ingesting notes never reopens it. It works with ids that were later merged into another item, says plainly when an item is already Done, and gives a clear error for an id that doesn't exist.

## User Stories

1. As a meeting organiser, I want `actiontrack done 12` to mark item 12 Done, so that finished work leaves the open list.
2. As a meeting organiser, I want the command to print the item it closed (id, Owner(s), task), so that I can confirm I closed the right one.
3. As a meeting organiser, I want the time it was marked done recorded, so that there is a record of when work finished.
4. As a meeting organiser, I want the item to stay Done after any later ingest, even if a note still shows it unchecked, so that my update is never undone.
5. As a meeting organiser, I want marking a shared or Team Item done to close it for every Owner, so that joint work is closed once.
6. As a meeting organiser, I want marking an already-Done item to say "already done" and exit `0`, so that repeating the command is harmless.
7. As a meeting organiser, I want an id that was merged into another to close the surviving item and tell me "#14 was merged into #9", so that old ids still work.
8. As a meeting organiser, I want an unknown id to give a clear error and exit `1`, so that typos don't silently do nothing.
9. As a meeting organiser, I want a non-numeric id rejected as a usage error with exit `2`, so that I see I typed it wrong.
10. As a meeting organiser, I want a Done item to drop out of `list` and out of future follow-ups, so that nobody is chased for it.
11. As a meeting organiser, I want to close Ambiguous, Unknown and Unassigned items too, so that unclear items can still be cleared.
12. As a script author, I want `done --json` to print the closed item's JSON, so that automation can confirm the change.

## Implementation Decisions

- **Store operation:** "mark done by id". It follows `merged-into` to the live item, sets Done-at = now and Done-by = cli only if Done-at is empty, and returns the item plus whether it was already Done and the original id if it was redirected.
- **Exit codes:** `0` for closed or already done; `1` for unknown id; `2` for a malformed argument.
- **Output:** human-readable confirmation by default; `--json` prints the item in the same shape as `list --json`.
- **Done-by** values: `cli` and `note`. Done is set once and never cleared by any path (stickiness guaranteed by spec 06's ingest rules).

## Testing Decisions

- Through the CLI seam: ingest a crafted folder, run `done`, then assert on `list --json` and on the output and exit code of `done`.
- **Cases:** open → done and gone from the default list; re-ingest keeps it Done; a shared item disappears for both Owners; already done → message, 0; merged id → redirected message and the survivor is Done; unknown id → 1; `done abc` → 2; `--json` shape matches `list --json`.
- **Prior art:** specs 01–07 harness.

## Out of Scope

- Reopening an item, or marking items done in bulk.
- Recording who (which person) marked it done.

## Further Notes

- Glossary terms used: Action Item, Done, Source.
