# 09 — `actiontrack followup`: Follow-up Drafts through the Gmail MCP server

Status: done
Blocked by: 04, 07
Requirements: FR-15, FR-16, FR-17, NFR-1, NFR-4, NFR-5, ADR-0001

## Problem Statement

Follow-up emails after meetings are written late or not at all, and when they are written they miss items or include finished ones. Sending automatically is not acceptable either: a human must review every message, and nobody should get an email about a task that may not be theirs.

## Solution

`actiontrack followup <owner>` (or `--all`) composes one plain-text email per Person, listing their Open items with Overdue first and showing where each item came from. It saves the email as a **Gmail draft** through the configured Gmail MCP server, which actiontrack talks to as its own MCP client (ADR-0001). It never sends. `--dry-run` shows the emails without touching Gmail. Items with Ambiguous, Unknown or no Owners are never included.

## User Stories

1. As a meeting organiser, I want `actiontrack followup "Priya Nair"` to create one Gmail draft listing her Open items, so that I can review it and send it in seconds.
2. As a meeting organiser, I want `followup --all` to create one draft per Person who has Open items, so that I can do the whole week's follow-ups at once.
3. As a meeting organiser, I want `--dry-run` to print every email without contacting Gmail, so that I can check content first.
4. As a meeting organiser, I want the tool never to send, reply or forward any email, so that every message is reviewed by a human.
5. As a meeting organiser, I want Overdue items listed first under an OVERDUE heading with days late, then Open items by Due Date, so that the urgent work is obvious to the reader.
6. As a meeting organiser, I want each item to show its Due Date, or its raw Due Phrase, or "no due date", so that the reader knows what is expected.
7. As a meeting organiser, I want each item to show every source meeting's title and date, so that the reader remembers where they agreed to it.
8. As a meeting organiser, I want the subject to say how many items are open and overdue ("Action items from recent meetings — 2 open, 1 overdue"), so that the reader sees the size of the ask.
9. As a meeting organiser, I want the email to greet the Person by first name and be signed with the sender from config, so that it's ready to send as me.
10. As a meeting organiser, I want shared and Team Items included in each Owner's email, so that joint work is followed up with everyone.
11. As a meeting organiser, I want Ambiguous, Unknown and Unassigned items never included in any email, so that nobody is chased for work that may not be theirs.
12. As a meeting organiser, I want Done items never included, so that finished work isn't chased.
13. As a meeting organiser, I want `<owner>` resolved the same way as `list --owner` (full name, alias, unique first name), so that the commands feel consistent.
14. As a meeting organiser, I want an ambiguous `<owner>` (e.g. "Priya") to fail with the candidates, so that I never draft to the wrong person.
15. As a meeting organiser, I want a Person with no Open items skipped with a note and no draft, so that nobody gets an empty email.
16. As a meeting organiser, I want a Person missing from the roster or without an email skipped and reported, so that I know whose address to add.
17. As a meeting organiser, I want a warning when a draft for that Person was already created in the last 24 hours, while still creating the new one, so that I notice possible duplicates in Gmail.
18. As a meeting organiser, I want every draft created to be recorded with its Gmail draft id and items, so that there's a history of follow-ups.
19. As a meeting organiser, I want a clear summary at the end (drafts created, skipped with reasons, failed), so that I know what to check in Gmail.
20. As a meeting organiser, I want one failed draft not to stop the others, and the run to exit `1` when any failed, so that partial problems are visible without losing the rest.
21. As a meeting organiser, I want a clear error and exit `1` when the MCP server can't start or doesn't offer the configured draft tool, so that setup problems are obvious.
22. As a meeting organiser, I want a clear error and exit `2` when there's no config, so that I know to create one.
23. As a security-minded user, I want actiontrack to call only the configured create-draft tool, so that even a misbehaving server can't be asked to send.
24. As a security-minded user, I want note text passed to the server only as draft fields and never run as a command, so that a malicious note can't do anything.
25. As a tester, I want `--today` to control which items count as Overdue in emails, so that email content is reproducible.
26. As a meeting organiser, I want the drafts' content to match what `list --owner <Person>` shows as Open, so that the two views never disagree.

## Implementation Decisions

- **New module `followup`** (pure): given a Person, their Open items with Sources, today and the sender, it returns recipient, subject and body. The format is fixed by FR-16; Sources are joined in date order with `;`.
- **New module `gmail`** (the only MCP-aware code): opens a stdio session to the configured server command using the official `mcp` SDK client, initialises it, lists tools, and fails if the configured draft tool is missing. Then, per draft, it calls only that tool with `to`, `subject` and `body`. The draft id is taken from the tool result (structured content if present, otherwise text) and stored as returned. The async session is wrapped so the rest of the CLI stays synchronous. The server is started from the argument list, never through a shell.
- **Never-send guard** (NFR-1): the adapter holds the single configured tool name (already validated by spec 04 against send/reply/forward) and has no code path that calls any other tool.
- **Open-items selection** reuses the store query from spec 07 (status open, Owner = Person), so `list` and `followup` agree by construction. Only items of kind `person` or `team` are selectable by Person.
- **Store:** a drafts table (Person, email, Gmail draft id, item ids JSON, created-at). The 24-hour warning checks the latest row for that Person.
- **`--dry-run`** never starts the MCP server and never writes draft rows.
- **Exit codes:** `0` all attempted drafts created (skips are not failures); `1` any draft failed or the server/tool was unavailable; `2` no config, or an unresolvable or ambiguous `<owner>`.

## Testing Decisions

- **Seam 1 (CLI):** every test runs the `followup` command in-process with a temp database, temp notes and `--today` pinned.
- **Seam 2 (Gmail MCP boundary):** a fake stdio MCP server, built with the SDK's FastMCP, is named in the test config's `gmail.command`. It exposes `create_draft` and a decoy `send_message`, appends every call (tool name + arguments) to a log file whose path comes from an environment variable, and can be told through the environment to fail for a given recipient or to omit `create_draft`.
- **A good test** asserts on the command's output, exit code, the fake server's call log, and `list --json`. It never inspects internals.
- **Cases:** single Person → exactly one `create_draft` call with the expected subject/body (golden text); `--all` → one call per Person with Open items; the log never contains `send_message`, across all tests; `--dry-run` → no log file, no draft rows; Ambiguous/Unknown/Unassigned/Done items absent from bodies; shared and Team Items present for each Owner; skip reasons (no Open items, not in roster); ambiguous `<owner>` → 2; no config → 2; a server missing the tool → 1 and no calls; one recipient failing → 1, others created; a second run within 24 hours warns.
- **Sample fixture:** with `--today 2026-10-15` and a roster covering the sample Persons, `followup --all --dry-run` never mentions "circulate the go/no-go summary" (Ambiguous), and Meera Iyer's email lists "finalise the Q4 sales targets" under OVERDUE (12 days).
- **Prior art:** specs 01–08 harness; the fake server is new here.

## Out of Scope

- Sending, scheduling or replying to email.
- HTML email, attachments, CC/BCC.
- Updating or deleting earlier drafts.
- Choosing the production Gmail MCP server (see below).

## Further Notes

- **Open item, decided at the start of this spec:** pick and document one tested stdio Gmail MCP server for real use, and confirm its create-draft tool accepts `to`/`subject`/`body`. If it uses different argument names, add an argument-name mapping to `[gmail]` (spec 04) rather than special-casing servers in code.
- Glossary terms used: Follow-up Draft, Person, People Roster, Owner, Open, Overdue, Done, Source, Ambiguous Owner, Unknown Owner, Unassigned, Team Item.
