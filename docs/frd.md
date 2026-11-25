# actiontrack — Functional Requirements

actiontrack is a CLI that reads a folder of markdown Meeting Notes, tracks the Action Items in them, and drafts follow-up emails to their Owners as Gmail drafts for a human to review and send.

Domain terms (Meeting Note, Owner, Ambiguous Owner, Due Phrase, Source, Duplicate, …) are defined in [`../GLOSSARY.md`](../GLOSSARY.md) and used here with exactly that meaning. Non-functional requirements live in [`nfrd.md`](nfrd.md).

Requirement ids are stable: refer to them as `FR-<n>` in code comments, tests and commits.

## Commands at a glance

| Command | Purpose |
|---|---|
| `actiontrack ingest <folder>` | Parse every `.md` Meeting Note in the folder and store its Action Items. |
| `actiontrack list [filters]` | Show Action Items. |
| `actiontrack done <id>` | Mark an Action Item Done. |
| `actiontrack followup <owner> \| --all` | Create one Follow-up Draft per Owner in Gmail. Never sends. |

Global options on every command: `--db <path>` (default `./.actiontrack.db`, env `ACTIONTRACK_DB`), `--config <path>`, and a hidden `--today YYYY-MM-DD` (env `ACTIONTRACK_TODAY`) that pins "today" for tests and demos.

---

## 1. Ingest

### FR-1 Folder scan
- Read every file directly inside `<folder>` whose name ends in `.md` (case-insensitive). Subfolders are not scanned.
- Other files are ignored and counted in the report (e.g. `2026-09-19-offsite-draft.txt`).
- A missing or unreadable folder is a usage error (FR-12).

### FR-2 Note header
A note's header gives its title, Meeting Date and Attendees, in either form:

```markdown
# Meeting: Quote portal kickoff
Date: 2026-09-01
Attendees: Priya Nair, Rahul Mehta, Anita Desai, Sam Okafor
```

```markdown
---
title: Team standup
date: 2026-09-16
attendees: [Anita Desai, Lena Fischer, Meera Iyer]
---
```

- Meeting Date formats accepted: `2026-09-01`, `9 September 2026`, `Monday, 14 September 2026`, and `9 Sep 2026`. A leading weekday is ignored.
- Title falls back to the file name without `.md` (`2026-09-23-standup.md` → `2026-09-23-standup`) when absent.
- Attendees are optional; a note without them is still valid.

### FR-3 Malformed Notes
A note is Malformed, skipped entirely (none of its items stored) and listed in the report with its reason, when it:

| Reason | Sample |
|---|---|
| is not valid UTF-8 text | `scratch.md` (binary/PNG content) |
| is empty or whitespace only | `2026-09-09-notes-final-v2.md` |
| has no Meeting Date | `untitled.md` |
| has a Meeting Date that cannot be resolved | `2026-10-03-sales-pipeline.md` (`Date: sometime last week`) |

A Malformed Note never stops the run; every other note is still ingested.

### FR-4 Action Item shapes
Each of these is one Action Item, anywhere in the note:

| Shape | Example |
|---|---|
| Checkbox bullet with `-`, `*` or `+`, any indent, `[ ]`, `[x]` or `[X]` | `* [ ] Lena to run the customer survey, results due 15 October` |
| Nested checkbox (its own item, independent of its parent) | `  - [ ] Karan to validate targets against the budget by Oct 5th` |
| `@name:` prefix | `- [ ] @anita: audit colour contrast on the dashboard by Mon` |
| Row of a table with Owner / Action / Due columns | `\| Anita \| Refresh the brand kit \| 2026-10-09 \|` |
| `ACTION:` line | `ACTION: Karan to circulate the offsite summary tomorrow` |

Table rows and `ACTION:` lines are Open unless they say otherwise; checkbox items are Done when checked.

### FR-5 Decoys
Never ingest text inside a blockquote (`> - [ ] Karan to refund affected customers by Friday` in `2026-09-21-incident-review.md`) or inside a fenced or indented code block.

### FR-6 Splitting owner, task and Due Phrase
- **Owner part**: the text before the first ` to ` when it is made only of name tokens (capitalised words, initials like `N.`, `&`, `,`, `and`); or the `@name` before `:`; or the table's Owner column. Otherwise the item has no written owner and the whole text is the task.
- **Due Phrase**: only a trailing `by …` (including `— by Friday`; with several, the last `by` wins), a `, due …` / `results due …` clause, a bare trailing `tomorrow`, `today`, `EOD` or `EOD tomorrow` (`ACTION: Karan to circulate the offsite summary tomorrow`), or the table's Due column. A date anywhere else stays part of the task: `Sam to schedule cutover for Saturday 10 Oct` and `Karan to freeze invoice edits from 9 Oct` have no Due Date.
- The Due Phrase is stored without its leading `by` / `due` or trailing punctuation: `by Friday.` → `Friday`, `results due 15 October` → `15 October`. Table Due cells follow the same rule, and `—`, `-` or `n/a` cells count as empty.
- **Task**: what remains, trimmed of separators (`—`, `,`).

### FR-7 Owner resolution
Resolve each name in the owner part, in order:

1. Split on `&`, `,` and `and`: each name is a separate Owner of one shared item (`Anita & Rahul to agree on the component API` → Anita Desai **and** Rahul Mehta, one item).
2. `Team`, `Everyone` or `All` → a Team Item owned by every Attendee of that meeting. With no Attendees, it is Unassigned.
3. `TBD`, `Someone`, `Somebody`, `Anyone`, `?`, or no owner part → Unassigned.
4. Match case-insensitively against **that meeting's Attendees** by full name, first name, or first name + surname initial (`Priya N.` → Priya Nair).
5. No Attendee matches → match the People Roster (names and aliases) when a config is present (FR-17).
6. Exactly one match → that Person. More than one → **Ambiguous Owner**, keeping the written name and the candidates. None → **Unknown Owner**, keeping the written name.

Ambiguous, Unknown and Unassigned items are stored, listed and reported but never included in a Follow-up Draft.

### FR-8 Due Date resolution
Resolve the Due Phrase against the note's Meeting Date (M). Weeks run Monday–Sunday.

| Due Phrase | Due Date |
|---|---|
| `<weekday>` / `Wed`, `Mon` … | first such weekday strictly after M |
| `next <weekday>` | that weekday in the week after M's week |
| `tomorrow` / `EOD tomorrow` | M + 1 day |
| `EOD`, `today` | M |
| `end of next week` | Friday of the week after M's week |
| `end of month` | last day of M's month |
| `mid-<Month>` | 15th of that month |
| `2026-09-08`, `10 Sep`, `9 Oct`, `Oct 3rd`, `15 October`, `Wed 16 Sep` | that date; when the year is missing, M's year, or the next year if that date is before M |

Any other phrase → no Due Date, but the Due Phrase is stored and reported as unresolved. The raw Due Phrase is always stored.

### FR-9 Duplicates
- Two occurrences are the same Action Item when they have the same resolved Owner set and the same task once both are lowercased, stripped of punctuation, stripped of `a`/`an`/`the`, and stripped of the Due Phrase. For Ambiguous or Unknown Owners the written name is used; Unassigned items compare on task alone.
- A Duplicate adds a Source to the existing item, so it is one item with many Sources.
- The Due Phrase and Due Date come from the Source with the latest Meeting Date.

### FR-10 Status from notes
- An item is Done when any Source shows it checked (`[x]`/`[X]`), or when `actiontrack done` marked it.
- Done is final: a later unchecked mention does not reopen it.

### FR-11 Re-ingest and stable ids
- Ids are small integers assigned once and never reused or renumbered.
- Ingesting the same or an overlapping folder again creates no new items for occurrences already seen (an occurrence is identified by its note's path plus its normalised line: case, spacing, indent, bullet character and checkbox mark are ignored, so ticking a box or moving the line keeps the same item), changes no ids, and keeps Done status.
- If re-ingest re-resolves an occurrence (e.g. a config was added and an Unknown Owner now matches the roster), the existing item is updated in place.
- If two existing items become Duplicates, they merge into the lower id; using the higher id still works and prints `#<old> was merged into #<new>`.

### FR-12 Ingest report and exit codes
After every run, print:
- counts: notes read, notes skipped as Malformed, files ignored, items new, items merged as Duplicates, items newly Done;
- each Malformed Note with its reason (FR-3);
- each Ambiguous Owner (written name, candidates, note), Unknown Owner, and Unassigned item;
- each unresolved Due Phrase.

Exit `0` whenever the run completes, Malformed Notes included. Exit `2` for usage errors (missing folder, bad arguments). Exit `1` if the database fails; the run is rolled back. With `--json`, print the same report as one JSON object with keys `notes_read`, `malformed`, `ignored`, `items_new`, `items_merged`, `items_done`, `notes` (each Meeting Note read: `file`, `title`, `meeting_date`, `attendees`; JSON only), `malformed_notes` (`file`, `reason`), `ambiguous_owners` (`file`, `line`, `item_id`, `written_owner`, `candidates` sorted by name), `unknown_owners` (`file`, `line`, `item_id`, `written_owner`), `unassigned_items` (`file`, `line`, `item_id`, `task`) and `unresolved_due_phrases`. Keys may be added, never renamed (NFR-6). Problems such as Malformed Notes are also written to stderr.

---

## 2. List

### FR-13 `actiontrack list`
- With no filters: Open items only (Overdue included).
- Columns: id, Owner(s), task, due (Due Date, else raw Due Phrase, else `—`), status (`open`, `overdue (Nd)`, `done`), latest Source meeting title and date.
- Order: Overdue (most late first), then Open by Due Date, then undated items last; ties by id.
- Filters, combined with AND:
  - `--owner <name>`: full name, alias, or a first name unique among known Persons (all Attendees plus the roster); also `unassigned`. A first name matching several Persons is an error listing them. A shared or Team Item matches each of its Owners.
  - `--status open|done|overdue`: `open` = not Done (includes Overdue); `overdue` = Open with a Due Date before today; `done` = Done.
  - `--due-before <YYYY-MM-DD>`: Due Date strictly before that date; undated items excluded.
  - `--all`: every status.
- `--json`: an array of item objects with all fields above plus every Source.
- Overdue is computed at run time from today (or `--today`), never stored.

## 3. Done

### FR-14 `actiontrack done <id>`
- Marks the item Done and records when. Prints the item.
- Already Done → says so, exit `0`.
- Merged id → acts on the surviving item (FR-11).
- Unknown id → error, exit `1`.

---

## 4. Follow-up

### FR-15 `actiontrack followup <owner> | --all [--dry-run]`
- `<owner>` resolves as in `list --owner`; it must be a single Person with an email in the People Roster.
- `--all`: one draft for every Person with at least one Open item.
- Content: that Person's Open items, Overdue first, including shared and Team Items. Ambiguous, Unknown and Unassigned items are never included.
- Skipped and reported (no draft, not an error): an Owner with no Open items, or one not in the roster or without an email.
- `--dry-run`: print each email and create nothing.
- Each run creates a new draft. If a draft for that Owner was created in the last 24 hours, warn and still create it. Record the time of every draft created.
- Exit `0` when every attempted draft succeeded; `1` if any failed (the others are still attempted and reported). A missing config, or an MCP server that won't start, is an error with a clear message.

### FR-16 Email content
Plain text (illustrative only, with today = 2026-10-23):

```
To: priya.nair@example.com
Subject: Action items from recent meetings — 2 open, 1 overdue

Hi Priya,

Here are your open action items from recent meetings:

OVERDUE
- Collect beta feedback from Acme — due 2026-10-20 (3 days overdue)
  from: Quote portal weekly, 2026-10-13

OPEN
- Prepare the renewal one-pager — due 2026-10-24
  from: Acme renewal check-in, 2026-09-28; Acme renewal wrap-up, 2026-10-14
- Review the welcome email for accessibility — no due date
  from: Onboarding retro, 2026-10-05

Thanks,
<sender from config>
```

- Due shows the Due Date, else the raw Due Phrase, else `no due date`.
- Overdue items show days late.
- Every Source meeting is listed, joined in date order.

### FR-17 Gmail draft creation
- actiontrack is an MCP client (ADR-0001). It starts the stdio Gmail MCP server given in config and calls **only** the configured create-draft tool, once per draft, with recipient, subject and body.
- It never calls any tool that sends, replies or forwards. See NFR-1.

---

## 5. Configuration

### FR-18 `actiontrack.toml`
Looked up as `--config`, then `./actiontrack.toml`, then `~/.config/actiontrack/actiontrack.toml`. Only `followup` requires it; `ingest` uses it for roster fallback (FR-7 step 5) when present.

```toml
sender = "Your Name"

[gmail]
command = ["npx", "-y", "<gmail-mcp-server>"]   # stdio MCP server launch command
draft_tool = "create_draft"                     # the server's create-draft tool name

[[people]]
name = "Priya Nair"
email = "priya.nair@example.com"
aliases = ["Priya N."]

[[people]]
name = "Anita Desai"
email = "anita.desai@example.com"
aliases = ["anita"]
```

The config holds no credentials; Gmail authorisation stays with the MCP server. A filled-in copy of this example ships as `actiontrack.example.toml`; the real `actiontrack.toml` is git-ignored.

Any command that loads the config validates all of it. `ingest` loads it when found; `list` and `done` never load it. Each problem below exits `2` with the file path on stderr:

- `--config` names a file that doesn't exist (no fallback to the other locations).
- Invalid TOML or a file that isn't UTF-8 (TOML errors include the line).
- `[gmail]` is missing, `gmail.command` isn't a non-empty list of strings, or `gmail.draft_tool` is empty.
- `gmail.draft_tool` contains `send`, `reply` or `forward`, in any case (NFR-1).
- A `[[people]]` entry without a non-empty `name`, with an `email` lacking `@`, or with `aliases` that aren't a list of non-empty strings. The error names the entry's position (`[[people]] entry 3`).
- A full name or alias used by two People, ignoring case. A Person may repeat their own name as an alias.
- `sender` that isn't a non-empty string. `sender` may be left out until `followup` runs.

Unknown keys print a `warning:` line on stderr and are otherwise ignored.

---

## 6. Acceptance examples (sample `notes/`, `--today 2026-10-15`)

| Source | Expected |
|---|---|
| `2026-09-01` `Priya to send the revised quote to Acme by Friday` | Owner Priya Nair (the only Priya attending); due 2026-09-04 |
| `2026-09-08` `Priya N. to send revised quote to Acme — by Friday` | Duplicate of the above; due becomes 2026-09-11 |
| `2026-09-15` `[x] Priya to send the revised quote to Acme` | Same item becomes Done |
| `2026-09-30` `Karan to approve the Q4 cloud spend by 2026-10-02` + `2026-10-02` `[X] …` | One item, Done |
| `2026-09-03` `Priya to draft the test plan … by end of next week` | Priya Shah; due 2026-09-11 |
| `2026-09-14` / `2026-09-24` `Rahul to estimate (the) SSO work (by Monday)` | One item, Rahul Verma; due 2026-09-28 |
| `2026-09-14` `… by end of month` | due 2026-09-30 |
| `2026-09-18` `@anita: audit colour contrast on the dashboard by Mon` | Anita Desai; due 2026-09-21 |
| `2026-09-18` `Anita & Rahul to agree on the component API by Wednesday` | One shared item: Anita Desai + Rahul Mehta; due 2026-09-23 |
| `2026-09-18` `TBD to write the design-system changelog`; `2026-09-10` `Someone to update the CRM notes` | Unassigned |
| `2026-10-01` `Team to decide on the launch date` | Team Item: Priya Nair, Rahul Mehta, Anita Desai, Sam Okafor, Meera Iyer |
| `2026-10-08` `Priya to circulate the go/no-go summary by EOD` | Ambiguous Owner (Priya Nair, Priya Shah); due 2026-10-08 |
| `2026-09-30` `Rahul to prepare the architecture overview by Friday` | Ambiguous Owner (Rahul Mehta, Rahul Verma); due 2026-10-02 |
| `2026-09-30` table row `Anita \| Refresh the brand kit \| 2026-10-09` | Anita Desai; due 2026-10-09 |
| `2026-09-30` `ACTION: Karan to circulate the offsite summary tomorrow` | Karan Joshi; due 2026-10-01 |
| `2026-09-30` nested `Karan to validate targets against the budget by Oct 5th` | Its own item; due 2026-10-05 |
| `2026-09-30` `Lena to run the customer survey, results due 15 October` | Task "run the customer survey"; due 2026-10-15 |
| `2026-09-30` `Sam to propose the on-call rotation by mid-October` | due 2026-10-15 |
| `2026-09-30` `Meera to finalise the Q4 sales targets by Oct 3rd` | due 2026-10-03; Overdue by 12 days |
| `2026-10-05` `Rahul to start SSO spike by next Tuesday` | due 2026-10-13 |
| `2026-09-29` `Sam to schedule cutover for Saturday 10 Oct` | No Due Date |
| `2026-09-29` + `2026-10-08` `Karan to freeze invoice edits from 9 Oct` | One item, two Sources, no Due Date |
| `2026-09-21` blockquote `Karan to refund affected customers by Friday` | Decoy, not ingested |
| `scratch.md`, `2026-09-09-notes-final-v2.md`, `untitled.md`, `2026-10-03-sales-pipeline.md` | Malformed, with reasons from FR-3 |
| `2026-09-19-offsite-draft.txt` | Ignored (not `.md`) |
| `2026-09-16-standup.md` (YAML front-matter) | Valid; items ingested |

## 7. Out of scope
- Sending email of any kind.
- Editing, reassigning or deleting items from the CLI (fix the note and re-ingest).
- Reading notes from anywhere except a local folder.
- Recursive folder scanning.
- HTML email.

## 8. Open items
- Deferred to the start of spec 09: pick and document one tested stdio Gmail MCP server as the default, and confirm its create-draft tool's argument names (recipient, subject, body). If they differ between servers, add a mapping to `[gmail]`.
