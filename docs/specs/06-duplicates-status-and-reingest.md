# 06 — Duplicates, status across Sources, and re-ingest

Status: ready-for-agent
Blocked by: 03, 05
Requirements: FR-9, FR-10, FR-11, FR-12 (merge/done counts)

## Problem Statement

The same commitment is repeated across several meetings with small wording changes ("send the revised quote to Acme" → "send revised quote to Acme — by Friday"), sometimes with a new deadline, and is eventually ticked off in a later note. If every repeat becomes a new item, lists fill with copies, people get chased several times for one task, and ticking it off in one place leaves the copies open.

## Solution

Repeats of the same Action Item (same Owner(s), same task once wording noise is removed) become one item with many Sources. The latest meeting sets the Due Date. A check mark in any Source marks it Done, and Done is final. Re-ingesting is always safe: ids never change, and when a correction makes two existing items the same, they merge into the lower id and the higher id keeps working.

## User Stories

1. As a meeting organiser, I want an item repeated in later meetings to stay one Action Item, so that the list shows each commitment once.
2. As a meeting organiser, I want repeats with small wording differences (case, punctuation, "the"/"a"/"an", a different Due Phrase) recognised as the same item, so that natural rewording doesn't create copies.
3. As a meeting organiser, I want items with the same task but different Owners kept separate, so that two people doing similar work are both tracked.
4. As a meeting organiser, I want genuinely reworded tasks kept separate rather than guessed, so that different tasks are never wrongly merged.
5. As a meeting organiser, I want each repeat recorded as another Source of the item, so that I can see every meeting it came up in.
6. As a meeting organiser, I want the Due Date taken from the latest meeting that mentions the item, so that a re-committed deadline replaces the old one.
7. As a meeting organiser, I want a later mention without a Due Phrase to leave the existing Due Date unchanged, so that "Priya to send the revised quote" (no date) doesn't erase a deadline.
8. As a meeting organiser, I want an item checked in any Source to be Done, so that ticking it off in a later meeting closes it.
9. As a meeting organiser, I want a Done item to stay Done when a later note lists it unchecked, so that people aren't chased for finished work.
10. As a meeting organiser, I want an item I marked done with the CLI to stay Done after re-ingest, so that my updates are never lost.
11. As a meeting organiser, I want ingesting the same folder twice to change nothing, so that I can re-run ingest whenever I like.
12. As a meeting organiser, I want ingesting a folder that overlaps a previous one to add only the new occurrences, so that adding notes over time is safe.
13. As a meeting organiser, I want ids never renumbered or reused, so that ids I wrote down stay valid.
14. As a meeting organiser, I want a correction (note edit or roster change) that makes two existing items the same to merge them into the lower id, so that copies disappear.
15. As a meeting organiser, I want a merged item to be Done if either part was Done, so that merging never reopens work.
16. As a meeting organiser, I want using a merged id to still work and tell me "#14 was merged into #9", so that old references don't break.
17. As a meeting organiser, I want the ingest report to count items merged as Duplicates and items newly marked Done, so that I can see what each run changed.
18. As a meeting organiser, I want Ambiguous and Unknown items compared on their written owner name, so that repeats of an unclear item also collapse.
19. As a meeting organiser, I want Unassigned items compared on their task alone, so that repeated unowned work also collapses.
20. As a script author, I want `list --json` to include all Sources of each item in date order, so that I can trace its history.

## Implementation Decisions

- **Dedupe key** (computed in the `items` module, pure): owner kind + sorted resolved Person names (or the lowercased written owner for Ambiguous/Unknown, empty for Unassigned) + the normalised task. The task is normalised by lowercasing, removing punctuation, dropping the words `a`/`an`/`the`, collapsing whitespace, and excluding the Due Phrase (already split off in spec 02).
- **Store:** live items are unique on the dedupe key, counting only items that haven't been merged. Ingest order per occurrence: (1) known Source (note path + line key)? → update its item in place, re-resolving owner and due; (2) else live item with the same key? → attach a new Source; (3) else insert a new item.
- **Due Date and task text** come from the Source with the latest Meeting Date that has a Due Phrase (task text from the latest Source overall). Ties go to the later file name.
- **Done** is set once (Done-at, Done-by = note or cli) and never cleared.
- **Merge:** after updates, any two live items with the same key merge. The higher id gets merged-into = lower id; its Sources and owner rows move to the lower id; Done carries over. Merged items are excluded from every listing.
- **Report:** fills `items_merged` (repeats attached + merges) and `items_done`.

## Testing Decisions

- Through the CLI seam: multi-note scenarios in the temp folder, asserting on `list --json` and the ingest report, with re-runs inside the same test.
- **Cases:** wording-noise duplicates merge; different Owners don't; a later Due Phrase wins and a later no-phrase mention keeps the date; `[x]` in a later Source → Done; a later `[ ]` doesn't reopen (CLI-done surviving re-ingest is tested in spec 08); identical re-ingest → zero new items and identical JSON; an overlapping folder adds only the new; a roster change that makes an Unknown item equal to an existing Person item merges into the lower id and the higher id resolves to it.
- **Sample fixture** (FRD §6): "send (the) revised quote to Acme" → one item, three Sources (09-01, 09-08, 09-15), due 2026-09-11, Done; "estimate (the) SSO work" → one item, Rahul Verma, due 2026-09-28; "approve the Q4 cloud spend" → one item, Done from `[X]` on 2026-10-02; "freeze invoice edits from 9 Oct" → one item, two Sources, no Due Date.
- **Prior art:** specs 01–05 harness.

## Out of Scope

- Fuzzy or similarity-based matching.
- Reporting near-miss duplicates.
- Un-merging items.
- Removing Sources when a note or line is deleted (known limitation, technical_details §8).

## Further Notes

- Glossary terms used: Duplicate, Source, Open, Done.
