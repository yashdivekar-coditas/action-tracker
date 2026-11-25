# 03 — Due Dates: resolving Due Phrases against the Meeting Date

Status: done
Blocked by: 02
Requirements: FR-8, FR-12 (unresolved Due Phrases), NFR-3

## Problem Statement

Deadlines in notes are written the way people speak: "by Friday", "tomorrow", "end of next week", "mid-October", "Oct 3rd". Without a real calendar date nothing can be sorted, filtered or flagged as overdue. Guessing badly is worse than not guessing, because a wrong date sends someone a false overdue reminder.

## Solution

Each Due Phrase is resolved to a Due Date using fixed, predictable rules counted from the note's Meeting Date. Phrases that don't match a rule get no Due Date: their raw text is kept, they are shown as written, and they are listed in the ingest report as unresolved.

## User Stories

1. As a meeting organiser, I want "by Friday" in a Tuesday meeting to mean that week's Friday, so that weekday deadlines match what people meant.
2. As a meeting organiser, I want a weekday deadline said on that same weekday (e.g. "by Friday" in a Friday meeting) to mean the following week's day, so that a deadline is never the day it was set.
3. As a meeting organiser, I want abbreviated weekdays (`Mon`, `Wed`) understood, so that shorthand works.
4. As a meeting organiser, I want "next Tuesday" to mean Tuesday of the week after the meeting's week, so that "next" adds a week as agreed.
5. As a meeting organiser, I want "tomorrow" and "EOD tomorrow" to mean the day after the meeting, so that short deadlines are exact.
6. As a meeting organiser, I want "EOD" and "today" to mean the meeting day itself, so that same-day actions are due immediately.
7. As a meeting organiser, I want "end of next week" to mean Friday of the following week, so that it matches working weeks.
8. As a meeting organiser, I want "end of month" to mean the last day of the meeting's month, so that month-end deadlines are exact.
9. As a meeting organiser, I want "mid-October" to mean 15 October, so that loose deadlines still sort and go overdue sensibly.
10. As a meeting organiser, I want ISO dates (`2026-09-08`) used as they are, so that precise deadlines are kept.
11. As a meeting organiser, I want day-month forms (`10 Sep`, `15 October`) and month-day forms with ordinals (`Oct 3rd`, `Oct 5th`) understood, so that common styles work.
12. As a meeting organiser, I want a weekday before an explicit date (`Wed 16 Sep`) to be ignored in favour of the date, so that the date wins.
13. As a meeting organiser, I want a date with no year to take the meeting's year, or the next year if that date is before the meeting, so that "by 5 Jan" said in December lands in January of the next year.
14. As a meeting organiser, I want case and extra spaces to make no difference, so that "By FRIDAY" works.
15. As a meeting organiser, I want a phrase that matches no rule to keep no Due Date but still show its raw text, so that nothing is lost and nothing is guessed.
16. As a meeting organiser, I want unresolved Due Phrases listed in the ingest report with their note, so that I can rewrite them.
17. As a meeting organiser, I want `list` to show the Due Date, or the raw Due Phrase when there is none, or `—` when there is no phrase, so that I always see the best available deadline.
18. As a script author, I want `list --json` to include both the raw Due Phrase and the ISO Due Date, so that I can audit the resolution.
19. As a tester, I want resolution to depend only on the Meeting Date and the phrase, never on today, so that results are reproducible.
20. As a meeting organiser, I want the table's Due column resolved with the same rules, so that table items behave like any other.

## Implementation Decisions

- **`dates` module** gains a pure resolver: given a Due Phrase and a Meeting Date, it returns a Due Date or none. Weeks run Monday to Sunday.
- **Rules**, in order of precedence: absolute ISO date; explicit day + month in either order, with optional ordinal suffix and optional leading weekday; `mid-<Month>`; `end of month`; `end of next week`; `next <weekday>`; `EOD tomorrow` / `tomorrow`; `EOD` / `today`; bare `<weekday>` (full or three-letter). The "first such weekday strictly after M" and year-rollover rules are as in FR-8.
- **Leading words are stripped first:** `by`, `due`, `results due` and surrounding punctuation.
- **Storage:** Due Date is stored as ISO on the item, and the raw Due Phrase is stored alongside. Re-ingest recomputes both, so a rule fix applies on the next run.
- **Report:** `unresolved_due_phrases` lists the note, line and raw phrase.
- **`list` due column:** Due Date, else the raw Due Phrase, else `—`.

## Testing Decisions

- Through the CLI seam: for each rule, write a note with a chosen Meeting Date and one item using the phrase, ingest, and assert the Due Date in `list --json`. Rules are table-driven inside one parametrised test.
- **Edge cases:** a same-weekday meeting; Dec→Jan year rollover; `Wed 16 Sep`; ordinals; casing; an unresolved phrase (e.g. "by the next sprint") appears in the report and has no Due Date.
- **Sample fixture** (from FRD §6): 2026-09-01 "by Friday" → 2026-09-04; 2026-09-03 "end of next week" → 2026-09-11; 2026-09-14 "end of month" → 2026-09-30; 2026-09-18 "by Mon" → 2026-09-21; 2026-09-30 "tomorrow" → 2026-10-01, "by Oct 5th" → 2026-10-05, "mid-October" → 2026-10-15, "results due 15 October" → 2026-10-15; 2026-10-05 "next Tuesday" → 2026-10-13; 2026-10-08 "EOD" → 2026-10-08.
- **Prior art:** specs 01–02 harness.

## Out of Scope

- Times of day and time zones.
- Natural-language date libraries.
- Business-day calendars and holidays.

## Further Notes

- "next <weekday>" meaning the following week is confirmed. Plain "<weekday>" covers the very next one.
- Glossary terms used: Due Phrase, Due Date, Meeting Date.
