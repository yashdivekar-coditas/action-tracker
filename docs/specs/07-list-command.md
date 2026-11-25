# 07 — `actiontrack list`: filters, Overdue and ordering

Status: ready-for-agent
Blocked by: 06
Requirements: FR-13, NFR-3, NFR-6

## Problem Statement

Once items are tracked, people need quick answers: what's still open, what's late, what does Priya owe, what's due before the release. A raw dump of every item, done or not, doesn't answer those questions, and overdue work has to stand out without anyone having to compare dates by hand.

## Solution

`actiontrack list` shows Open items by default, with Overdue items first and marked with how many days late they are. It can be filtered by Owner, status and due date, combined freely, and can output JSON for scripts. Overdue is always computed from today (or a pinned date), never stored.

## User Stories

1. As a meeting organiser, I want `actiontrack list` with no options to show Open items only, so that I see the work that matters.
2. As a meeting organiser, I want Overdue items listed first, most late first, so that the most urgent work is at the top.
3. As a meeting organiser, I want the rest ordered by Due Date, with undated items last, so that the list reads like a schedule.
4. As a meeting organiser, I want each Overdue item's status to say how many days late it is (`overdue (12d)`), so that I can judge urgency.
5. As a meeting organiser, I want columns for id, Owner(s), task, due, status and the latest Source meeting, so that each row has everything I need.
6. As a meeting organiser, I want `--owner "Priya Nair"` to show only her items, so that I can prepare for a 1:1.
7. As a meeting organiser, I want `--owner` to accept a roster alias or a first name that's unique among known Persons, so that I can type less.
8. As a meeting organiser, I want `--owner Priya` to fail with the list of matching Persons when there are two Priyas, so that I'm never shown the wrong person's items.
9. As a meeting organiser, I want `--owner unassigned` to show items with no Owner, so that I can hand them out.
10. As a meeting organiser, I want shared and Team Items to appear under each of their Owners, so that nobody's view is missing joint work.
11. As a meeting organiser, I want `--status open` to show every not-Done item, Overdue included, so that "open" means "still to do".
12. As a meeting organiser, I want `--status overdue` to show only Open items past their Due Date, so that I can chase late work.
13. As a meeting organiser, I want `--status done` to show finished items, so that I can review progress.
14. As a meeting organiser, I want `--all` to show every status, so that I can see the full history.
15. As a meeting organiser, I want `--due-before 2026-10-01` to show items due strictly before that date, excluding undated items, so that I can plan around a deadline.
16. As a meeting organiser, I want filters combined with AND, so that `--owner "Sam Okafor" --status overdue` means exactly that.
17. As a meeting organiser, I want an invalid `--due-before` date or `--status` value rejected with exit `2`, so that typos aren't silently ignored.
18. As a meeting organiser, I want a clear "no matching items" message with exit `0` when nothing matches, so that an empty result isn't mistaken for an error.
19. As a tester, I want `--today` to control Overdue, so that the sample notes from 2026 show predictable results.
20. As a script author, I want `--json` to print an array of items with id, owner kind, Persons, written owner, candidates, task, Due Phrase, Due Date, status, days overdue and every Source, so that I can build reports.
21. As a script author, I want the JSON field names to stay stable across versions, so that my scripts don't break.
22. As a meeting organiser, I want merged items never to appear in the list, so that I only see live items.
23. As a meeting organiser, I want long tasks to stay readable in a narrow terminal, so that the table doesn't fall apart.

## Implementation Decisions

- **The `store` query** takes filters (Owner Persons or Unassigned, status, due-before, today) and returns live items with their Owners and Sources, already ordered. Overdue = not Done and Due Date < today. Days overdue = today − Due Date.
- **`--owner` resolution** happens in the CLI against known Persons (Attendees across ingested notes plus the roster if a config is present): exact full name, then alias, then unique first name. Zero matches or several → exit `2` with the candidates. The special value `unassigned` selects Unassigned items. `--owner` never selects Ambiguous or Unknown items; they appear in unfiltered listings and in the ingest report.
- **Defaults:** no status filter means `open`; `--all` overrides any `--status`.
- **Table rendering:** fixed columns; the task is truncated with `…` to the terminal width (falling back to 100 columns when it can't be detected); `--json` is never truncated.
- **JSON contract:** the field list in story 20, with dates in ISO format. Adding fields is allowed; renaming or removing them is a breaking change (NFR-6).

## Testing Decisions

- Through the CLI seam with `--today` pinned: build state by ingesting crafted notes, then assert on `list --json` (ordering, membership, days overdue) and on the exit code for bad input. One smoke test checks the human table's header and an `overdue (Nd)` cell.
- **Cases:** default is open-only; ordering (overdue by lateness, then by date, undated last); each status value; `--all`; `--due-before` exclusive and excluding undated; owner by full name, alias, unique first name; ambiguous first name → 2 with candidates; `unassigned`; shared/Team Items under each Owner; combined filters; invalid inputs → 2; empty result → 0.
- **Sample fixture** (`--today 2026-10-15`): `--status overdue` includes "finalise the Q4 sales targets" (Meera Iyer, 12 days); `--owner "Anita Desai"` includes "agree on the component API" and "decide on the launch date"; `--owner Priya` exits 2 listing Priya Nair and Priya Shah.
- **Prior art:** specs 01–06 harness.

## Out of Scope

- Sorting options, pagination, colour output.
- Filtering by meeting or text search.
- Editing items from the list.

## Further Notes

- Glossary terms used: Open, Done, Overdue, Owner, Unassigned, Team Item, Source.
