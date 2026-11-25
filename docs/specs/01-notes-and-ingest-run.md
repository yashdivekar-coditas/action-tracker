# 01 — Notes: folder scan, note headers and Malformed Notes

Status: ready-for-agent
Blocked by: none
Requirements: FR-1, FR-2, FR-3, FR-12, NFR-2, NFR-3, NFR-4, NFR-6, NFR-7, NFR-8

## Problem Statement

Our meeting notes pile up as markdown files in a folder. Some follow the house template, some use YAML front-matter, and a few are broken (an image saved as `.md`, an empty file, a note with no date). There is no tool that reads them all reliably. Anything we build on top (action items, follow-ups) needs a dependable way to read the folder that never crashes on bad input and always says what it skipped and why.

## Solution

`actiontrack ingest <folder>` reads every `.md` file directly inside the folder. It understands both header styles, records each Meeting Note (title, Meeting Date, Attendees), skips every Malformed Note with a stated reason, ignores non-markdown files, and prints a report. It exits `0` whenever the run completes, even when notes were skipped.

This spec also sets up what every later spec builds on: the `actiontrack` command, its global options, the local database and the ingest report.

## User Stories

1. As a meeting organiser, I want to run `actiontrack ingest <folder>` on my notes folder, so that every meeting is read in one step.
2. As a meeting organiser, I want only `.md` files to be read, so that agendas, drafts and other files in the folder aren't mistaken for meetings.
3. As a meeting organiser, I want the report to count files that were ignored for not being `.md`, so that I know they were seen and skipped on purpose.
4. As a meeting organiser, I want notes written with a `# Meeting: <title>` line, a `Date:` line and an `Attendees:` line to be understood, so that our standard template just works.
5. As a meeting organiser, I want notes that use a YAML front-matter block (`title`, `date`, `attendees`) to be understood, so that notes exported from other tools also work.
6. As a meeting organiser, I want Meeting Dates written as `2026-09-01`, `9 September 2026`, `9 Sep 2026` or `Monday, 14 September 2026` to be understood, so that people can write dates naturally.
7. As a meeting organiser, I want a note with no title to fall back to its file name, so that every meeting still has a readable label.
8. As a meeting organiser, I want a note without an Attendees list to still be ingested, so that one missing line doesn't lose a whole meeting.
9. As a meeting organiser, I want a binary file named `.md` to be reported as Malformed ("not text") instead of crashing the tool, so that one bad file never blocks the rest.
10. As a meeting organiser, I want an empty or whitespace-only note to be reported as Malformed ("empty"), so that I can delete or fix it.
11. As a meeting organiser, I want a note with no Meeting Date to be reported as Malformed ("no meeting date"), so that its due dates are never guessed from nothing.
12. As a meeting organiser, I want a note whose Meeting Date can't be resolved (e.g. `sometime last week`) to be reported as Malformed ("unresolvable meeting date: <text>"), so that I know exactly what to correct.
13. As a meeting organiser, I want a Malformed Note to be skipped completely, never half-ingested, so that the tracker never holds items from a note it couldn't fully understand.
14. As a meeting organiser, I want every other note to be ingested even when some are Malformed, so that the run is still useful.
15. As a meeting organiser, I want ingest to exit `0` when it completes with skipped notes, so that scripts don't treat expected messiness as failure.
16. As a meeting organiser, I want a clear error and exit `2` when the folder doesn't exist or the arguments are wrong, so that I notice typos straight away.
17. As a meeting organiser, I want the report to show how many notes were read, skipped and ignored, so that I can trust the run covered everything.
18. As a script author, I want `ingest --json` to print the same report as one JSON object, so that I can automate checks on it.
19. As a meeting organiser, I want to choose the database file with `--db` or `ACTIONTRACK_DB`, so that I can keep separate trackers for separate teams.
20. As a meeting organiser, I want the database created by default at `./.actiontrack.db`, so that I don't need any setup to start.
21. As a meeting organiser, I want an interrupted or failed ingest to leave the database exactly as it was, so that a crash never leaves half a run behind.
22. As a tester, I want to pin "today" with a hidden `--today YYYY-MM-DD` or `ACTIONTRACK_TODAY`, so that results don't change from day to day.
23. As a maintainer, I want files processed in name order, so that the same folder always gives the same ids and the same report.
24. As a meeting organiser, I want notes saved with a UTF-8 byte-order mark to be read normally, so that notes from Windows editors work.
25. As a meeting organiser, I want re-ingesting a note whose header changed (e.g. a corrected title) to update that Meeting Note, so that the tracker reflects the current file.
26. As a privacy-minded user, I want the database file to be readable only by me, so that meeting content stays private on a shared machine.
27. As any user, I want `--help` on `actiontrack` and on `ingest`, so that I can discover the options without reading docs.
28. As any user, I want human output on stdout and warnings on stderr, so that I can pipe the output cleanly.

## Implementation Decisions

- **Modules introduced:** `cli` (subcommands, global options, output formatting, exit codes), `notes` (turns a file's bytes into a Meeting Note or a Malformed reason; pure, no I/O beyond the bytes it is given), `dates` (Meeting Date parsing here; Due Date resolution arrives in spec 03), `ingest` (runs a folder: scan, parse, store, build the report), `store` (all SQLite access).
- **Single entry point:** the CLI exposes one function that takes the argument list and returns the exit code. The console script calls it and every test calls it. Nothing else is a test seam.
- **Global options** on every command: `--db` (default `./.actiontrack.db`, env `ACTIONTRACK_DB`), `--config` (used from spec 04), and the hidden `--today` (env `ACTIONTRACK_TODAY`). An explicit option beats the environment variable.
- **Exit codes:** `0` the run completed; `1` the operation failed (e.g. database error); `2` usage error.
- **Folder scan:** non-recursive; `.md` extension compared case-insensitively; files sorted by name before processing.
- **Malformed reasons** are a fixed set of short strings: `not text`, `empty`, `no meeting date`, `unresolvable meeting date: <raw>`, and `unreadable: <error>` for any unexpected exception while parsing a single note. The `ingest` module catches per-note exceptions and turns them into the last reason (NFR-2).
- **Header parsing:** YAML front-matter is recognised only when the file's first line is `---`. Only the simple `key: value` and `key: [a, b]` forms are supported, which is enough for `title`, `date` and `attendees`, so no YAML library is needed. Otherwise, the first `# Meeting:` (or first `#` heading) is the title, and `Date:` / `Attendees:` lines are matched case-insensitively anywhere before the first `##` heading. Attendees are split on commas and trimmed.
- **Storage:** the database schema is versioned with SQLite's `user_version`. This spec creates the Meeting Notes table: absolute path (key), title, Meeting Date (ISO), Attendees (JSON list of full names), ingested-at. An ingest run is one transaction, and any store error rolls it back and exits `1`. The database file is created with owner-only permissions.
- **Report contract:** the report has counts `notes_read`, `malformed`, `ignored`, `items_new`, `items_merged`, `items_done`, and lists `malformed_notes` (file + reason), `ambiguous_owners`, `unknown_owners`, `unassigned_items` and `unresolved_due_phrases`. This spec fills the note counts and `malformed_notes`; later specs fill the rest. In `--json` the keys are stable: they may be added to, never renamed (NFR-6).

## Testing Decisions

- **A good test** calls the CLI entry point with a temporary notes folder and a temporary database, then asserts only on the exit code, stdout/stderr and `--json` output. It never calls internal functions or reads database tables directly, so tests survive refactors.
- **Shared harness (created here, reused by every later spec):** a helper that writes small notes into a temp folder, runs the CLI in-process with `--db` pointing into the temp folder and `--today` pinned, and returns exit code, stdout, stderr and parsed JSON.
- **Cases:** both header styles; each Meeting Date format; title fallback; missing Attendees; each Malformed reason; ignored non-`.md` count; missing folder (exit 2); name-order determinism (same folder twice gives identical JSON); a database path that can't be written (exit 1, nothing partially written).
- **Sample fixture:** ingesting the provided `notes/` folder gives exactly 4 Malformed Notes with the expected reasons (`scratch.md` not text, `2026-09-09-notes-final-v2.md` empty, `untitled.md` no meeting date, `2026-10-03-sales-pipeline.md` unresolvable meeting date), 1 ignored file (`2026-09-19-offsite-draft.txt`) and 31 notes read, with exit `0`. Treat `notes/` as read-only.
- **Prior art:** none yet; this spec establishes the harness.

## Out of Scope

- Finding action items in the note body (spec 02).
- Recursive folder scanning, non-markdown formats, remote sources.
- Removing notes from the tracker when files are deleted.

## Further Notes

- `untitled.md` contains real-looking action items but no header; it is still Malformed because its due dates would have nothing to be resolved against.
- Glossary terms used: Meeting Note, Meeting Date, Attendee, Malformed Note.
