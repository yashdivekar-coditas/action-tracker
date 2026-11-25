# 05 — Owners: resolving written names to Persons

Status: done
Blocked by: 02, 04
Requirements: FR-7, FR-12 (owner sections of the report), FR-13 (owner column)

## Problem Statement

Notes name owners loosely: "Priya", "Priya N.", "@anita", "Anita & Rahul", "Team", "TBD", or nobody at all. We have two Priyas (Nair and Shah) and two Rahuls (Mehta and Verma). Guessing the wrong person sends a reminder to someone who never agreed to the task. Silently dropping unclear owners loses the item.

## Solution

Each written owner is resolved against that meeting's Attendees first, then the People Roster. The result is one of: one or more Persons (a shared item for "A & B"), a Team Item owned by every Attendee, an Ambiguous Owner when more than one Person fits, an Unknown Owner when nobody fits, or Unassigned when no real owner was written. Unclear outcomes are kept, shown and reported, but never guessed.

## User Stories

1. As a meeting organiser, I want "Priya" resolved to Priya Nair when she is the only Priya at that meeting, so that most first-name items need no extra work.
2. As a meeting organiser, I want "Priya N." resolved to Priya Nair using the surname initial, so that notes that disambiguate are understood.
3. As a meeting organiser, I want a full name ("Priya Nair") matched directly, so that precise notes are honoured.
4. As a meeting organiser, I want matching to ignore case (`@anita` → Anita Desai), so that handles and lowercase names work.
5. As a meeting organiser, I want "Anita & Rahul to agree on the component API" to be one shared item owned by Anita Desai and Rahul Mehta, so that both are accountable and one `done` closes it.
6. As a meeting organiser, I want names joined by `,` or `and` treated the same way as `&`, so that writing style doesn't matter.
7. As a meeting organiser, I want "Team to decide on the launch date" owned by every Attendee of that meeting, so that the whole group is reminded.
8. As a meeting organiser, I want `Everyone` and `All` treated like `Team`, so that synonyms work.
9. As a meeting organiser, I want a Team Item in a note with no Attendees to be Unassigned, so that it isn't silently given to no one.
10. As a meeting organiser, I want "TBD", "Someone", "Somebody", "Anyone", "?" or no owner at all to make the item Unassigned, so that unowned work is visible and claimable.
11. As a meeting organiser, I want a bare "Priya" in a meeting both Priyas attended to be an Ambiguous Owner listing both candidates, so that nobody is wrongly chased.
12. As a meeting organiser, I want a name that matches no Attendee to fall back to the People Roster when a config exists, so that people who missed the meeting can still own items.
13. As a meeting organiser, I want a roster alias (e.g. `Priya N.` or `anita`) to count as a match, so that house nicknames work.
14. As a meeting organiser, I want a name that matches nobody to be an Unknown Owner that keeps the written name, so that I can see who was meant and fix the roster or the note.
15. As a meeting organiser, I want the ingest report to list every Ambiguous Owner with its candidates and note, every Unknown Owner, and every Unassigned item, so that I can fix them in one pass.
16. As a meeting organiser, I want `list` to show resolved Person names, or "Priya (ambiguous: Priya Nair, Priya Shah)", "Karan (unknown)" or "unassigned", so that unclear owners stand out.
17. As a meeting organiser, I want Ambiguous, Unknown and Unassigned items never sent in follow-ups, so that emails only reach people who are sure to own the work.
18. As a meeting organiser, I want fixing a note or the roster and re-ingesting to update the owner of existing items in place, keeping their ids, so that corrections don't create duplicates.
19. As a script author, I want `list --json` to include the owner kind, the resolved Persons, the written name and the candidates, so that I can audit resolution.
20. As a meeting organiser, I want table rows' Owner column and `ACTION:` lines resolved by the same rules, so that every shape behaves the same.

## Implementation Decisions

- **New module `owners`** (pure): given an owner part, the meeting's Attendees and the People Roster (possibly empty), it returns a resolution with a kind (`person`, `team`, `ambiguous`, `unknown`, `unassigned`), the resolved Persons, the written name and the candidates.
- **Order of rules** (FR-7): split on `&` / `,` / `and` → placeholders (`Team`-style, `TBD`-style) → Attendees (full name, first name, first name + surname initial, case-insensitive, leading `@` dropped) → roster names and aliases → one match / several (Ambiguous) / none (Unknown).
- **Multi-name owner parts:** each name is resolved on its own. If every name resolves to a Person, the item is a shared `person` item. If any name is Ambiguous or Unknown, the whole item takes that kind (Ambiguous wins over Unknown), keeping the full written owner part.
- **Persons are identified by full name.** Known Persons are the distinct Attendees across ingested notes plus the roster. There is no separate Person table.
- **Storage:** an item-owners table holds one row per Person per item. The item stores its owner kind, written owner and candidates (JSON list). Re-ingesting a seen Source re-resolves and updates the item in place (FR-11).
- **Report:** fills `ambiguous_owners`, `unknown_owners` and `unassigned_items`.

## Testing Decisions

- Through the CLI seam: notes with chosen Attendees plus an optional config roster; assert on `list --json` owner fields and the `ingest --json` report.
- **Cases:** one test per FR-7 step; `Priya N.` disambiguation; `@anita`; `A & B` shared; `A and B`; Team with and without Attendees; each placeholder; Ambiguous via Attendees; roster fallback with and without a config; alias match; Unknown; re-ingest after adding a roster entry changes the owner and keeps the id.
- **Sample fixture** (FRD §6): 2026-09-01 "Priya" → Priya Nair; 2026-09-03 "Priya" → Priya Shah; 2026-09-18 "Anita & Rahul" → Anita Desai + Rahul Mehta; 2026-09-18 "@anita" → Anita Desai; 2026-09-18 "TBD" and 2026-09-10 "Someone" → Unassigned; 2026-10-01 "Team" → Priya Nair, Rahul Mehta, Anita Desai, Sam Okafor, Meera Iyer; 2026-10-08 "Priya" and 2026-09-30 "Rahul" → Ambiguous with both candidates.
- **Prior art:** specs 01–04 harness and config fixtures.

## Out of Scope

- Reassigning owners from the CLI (fix the note or roster and re-ingest).
- Interactive prompts during ingest.
- Fuzzy name matching or nickname guessing beyond roster aliases.

## Further Notes

- Glossary terms used: Owner, Attendee, Person, People Roster, Ambiguous Owner, Unknown Owner, Unassigned, Team Item.
