# 02 — Action Items: shapes, Decoys and the owner / task / Due Phrase split

Status: ready-for-agent
Blocked by: 01
Requirements: FR-4, FR-5, FR-6, FR-10 (single Source), FR-11 (same-line idempotency), FR-13 (basic listing)

## Problem Statement

Action items in our notes are written in many shapes: checkbox bullets with `-`, `*` or `+`, nested sub-items, `@name:` prefixes, an Owner/Action/Due table, and `ACTION:` lines. Some lines that look like action items are not agreed actions at all, such as a quoted wish from another team or an example inside a code block. If the tool misses real items or picks up fake ones, nobody will trust the list.

## Solution

During ingest, every agreed Action Item in a valid Meeting Note is found in any of the supported shapes. Decoys are ignored. Each item is split into its written owner part, its task and its Due Phrase, and stored with a stable id. A first, unfiltered `actiontrack list` shows the stored items so they can be checked.

Owner names are stored as written until spec 05 resolves them, and Due Phrases are stored raw until spec 03 resolves them.

## User Stories

1. As a meeting organiser, I want `- [ ] Priya to send the revised quote by Friday` to become an Action Item, so that our standard checkbox items are tracked.
2. As a meeting organiser, I want `*` and `+` checkbox bullets recognised as well as `-`, so that different editors' bullet styles all work.
3. As a meeting organiser, I want checkbox items at any indent recognised, so that items written under a sub-heading or inside a list are not lost.
4. As a meeting organiser, I want a nested checkbox (`  - [ ] Karan to validate targets…` under another item) to be its own Action Item, so that sub-tasks with different owners are tracked separately.
5. As a meeting organiser, I want `[x]` and `[X]` treated the same, so that capitalisation never changes meaning.
6. As a meeting organiser, I want a checked item to be stored as Done, so that work already finished in the meeting isn't chased.
7. As a meeting organiser, I want `- [ ] @anita: audit colour contrast by Mon` recognised with `anita` as the owner part, so that @-mention style notes work.
8. As a meeting organiser, I want each row of a table whose header has Owner, Action and Due columns to become an Action Item, so that items written as a table are tracked.
9. As a meeting organiser, I want the table's columns to be found by their header names, in any order and any case, so that slightly different tables still work.
10. As a meeting organiser, I want `ACTION: Karan to circulate the offsite summary tomorrow` recognised, so that action lines written in prose sections are tracked.
11. As a meeting organiser, I want table rows and `ACTION:` lines to start Open, so that they're chased until someone marks them done.
12. As a meeting organiser, I want lines inside a blockquote ignored, so that a forwarded wish like `> - [ ] Karan to refund affected customers` is never mistaken for an agreed action.
13. As a meeting organiser, I want lines inside fenced or indented code blocks ignored, so that examples and templates in notes aren't tracked.
14. As a meeting organiser, I want the text before the first ` to ` treated as the owner part only when it is made of names (capitalised words, initials like `N.`, `&`, `,`, `and`, or `Team`/`TBD`/`Someone`-style words), so that tasks like `Book the venue` aren't given a fake owner.
15. As a meeting organiser, I want an item with no owner part to keep its whole text as the task, so that nothing written is lost.
16. As a meeting organiser, I want only a trailing `by …`, a `due …`/`results due …` clause, or the table's Due column treated as the Due Phrase, so that dates that are part of the work (e.g. `schedule cutover for Saturday 10 Oct`) aren't mistaken for deadlines.
17. As a meeting organiser, I want `— by Friday` recognised as a Due Phrase despite the dash, so that different writing styles work.
18. As a meeting organiser, I want the task trimmed of leftover separators (`—`, `,`), so that it reads cleanly in lists and emails.
19. As a meeting organiser, I want `Lena to run the customer survey, results due 15 October` stored with the task "run the customer survey" and the Due Phrase "15 October", so that the deadline and the work are separated correctly.
20. As a meeting organiser, I want each item's original line and line number kept as its Source, so that I can find it in the note.
21. As a meeting organiser, I want re-ingesting the same notes to create no new items for lines already seen, so that running ingest twice is harmless.
22. As a meeting organiser, I want the ingest report to count new items, so that I can see what each run added.
23. As a meeting organiser, I want `actiontrack list` to show the stored items with id, owner part, task, Due Phrase and status, so that I can check what was found.
24. As a script author, I want `actiontrack list --json` to output the items with their Sources, so that I can check extraction programmatically.
25. As a meeting organiser, I want items from Malformed Notes never stored, so that skipped notes stay fully skipped.

## Implementation Decisions

- **New module `items`** (pure): given a parsed Meeting Note's body, returns the list of occurrences found. Each occurrence has its line number, raw line, shape (checkbox / mention / table / action-line), checked flag, owner part (or none), task and Due Phrase (or none).
- **Decoy handling:** a single pass tracks whether the current line is inside a fenced code block, then skips lines in fences, lines indented as code blocks outside lists, and lines whose first non-space character is `>`.
- **Owner-part grammar:** tokens are capitalised words, single-letter initials with a dot, `@handle`, `&`, `,` and `and`, plus the placeholder words reserved for spec 05 (`Team`, `Everyone`, `All`, `TBD`, `Someone`, `Somebody`, `Anyone`, `?`). If the text before the first ` to ` isn't made only of these tokens, the item has no owner part.
- **Due Phrase grammar:** a trailing `by <rest>` (optionally preceded by `—`, `-` or `,`), or a `due <rest>` clause, or the table's Due cell. The Due Phrase is stored raw; resolving it is spec 03.
- **Store:** this spec adds the Action Items table (id, task, owner fields, Due Phrase, Due Date, Done-at and Done-by, merged-into) and the Sources table (note path, normalised line key, item id, line number, raw line, checked). A Source is keyed by note path + normalised line, so seeing the same line again maps to the same item (basic FR-11). In this spec each new line creates a new item; matching items across different lines and notes is spec 06.
- **Status:** a checked Source sets Done-at and Done-by = note on its item. Done is never cleared.
- **Owner storage until spec 05:** the written owner part is stored and shown as written. The owner-kind field is left unset for spec 05 to fill.
- **`list` (basic):** prints every stored item in id order, with columns id, owner (as written), task, due (raw Due Phrase or `—`) and status (`open`/`done`). `--json` prints an array of items, each with its Sources. Filters, default-open and ordering are spec 07.

## Testing Decisions

- Tests go through the CLI seam only: write a small note into the temp folder, run `ingest`, then assert on `list --json`. Use the harness from spec 01.
- **Cases:** one note per shape (checkbox with each bullet char, nested, `@name:`, table with reordered columns, `ACTION:`); `[x]`/`[X]` → done; blockquote, fenced-code and indented-code Decoys absent; owner-part edge cases (`Book the venue` → no owner part; `Priya N.`; `Anita & Rahul`; `Team`); Due Phrase edge cases (`— by Friday`, `results due 15 October`, `for Saturday 10 Oct` → none, `from 9 Oct` → none); re-ingest gives no new items and the same ids.
- **Sample fixture:** after ingesting `notes/`, the incident-review blockquote item (`Karan to refund affected customers`) is absent; the Q4 offsite note gives the table row (Anita, "Refresh the brand kit", "2026-10-09"), the `ACTION:` item and the nested Karan item.
- **Prior art:** spec 01's harness.

## Out of Scope

- Resolving owner names to Persons (spec 05) and Due Phrases to dates (spec 03).
- Merging repeated items across lines or notes (spec 06).
- List filters, ordering and Overdue (spec 07).

## Further Notes

- The table in `2026-09-30-q4-offsite.md` sits in a prose section, not under `## Action items`, so detection must not depend on headings.
- Glossary terms used: Action Item, Decoy, Due Phrase, Source, Open, Done.
