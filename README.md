# actiontrack

A Python CLI that reads a folder of markdown meeting notes, tracks the action items in them, and creates Gmail **drafts** for follow-ups. It never sends email.

```text
notes/*.md ──ingest──▶ SQLite ──list / done──▶ you
                          └────followup────▶ Gmail draft (via an MCP server) ──▶ you review and send
```

## Install

Python 3.11 or newer, macOS or Linux.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

The only runtime dependency is the official `mcp` SDK, used by `followup` alone. `ingest`, `list` and `done` work offline.

## Quick start

```bash
actiontrack ingest notes/                      # read every .md note in the folder
actiontrack list                               # open items, overdue first
actiontrack list --owner "Priya Nair" --status overdue
actiontrack list --due-before 2026-10-01 --json
actiontrack done 12                            # mark item 12 Done
actiontrack followup "Priya Nair" --dry-run    # preview the email, create nothing
actiontrack followup --all                     # one Gmail draft per Person with open items
```

Options such as `--db`, `--config` and `--today` go **after** the subcommand: `actiontrack list --db x.db`.

| Option | Meaning |
|---|---|
| `--db <path>` | Database file. Default `./.actiontrack.db`, or `$ACTIONTRACK_DB`. The default is relative to the current directory. |
| `--config <path>` | Config file (see below). |
| `--today YYYY-MM-DD` | Pin "today" for demos and tests (also `$ACTIONTRACK_TODAY`). |

Exit codes: `0` success (including ingest runs that skipped Malformed Notes), `1` the operation failed, `2` usage error.

## Writing notes

Each `.md` file directly inside the folder is one Meeting Note. It needs a Meeting Date:

```markdown
# Meeting: Quote portal kickoff
Date: 2026-09-01
Attendees: Priya Nair, Rahul Mehta, Anita Desai

- [ ] Priya to send the revised quote to Acme by Friday
- [x] @anita: audit colour contrast on the dashboard by Mon
ACTION: Karan to circulate the offsite summary tomorrow
```

YAML front-matter (`title`, `date`, `attendees`) works too. Action items can be checkbox bullets, `@name:` lines, `ACTION:` lines, or rows of an Owner / Action / Due table. Blockquotes and code blocks are ignored. The full rules, with examples, are in [`docs/frd.md`](docs/frd.md).

Things to know:

- Names are matched against that meeting's Attendees first, then the People Roster. An ambiguous or unknown name is stored, reported and **never** emailed.
- Ingest is idempotent: re-running it creates no new items and keeps ids and Done status.
- A note that can't be read (binary, empty, no date) is skipped and reported, and the rest still ingest.
- Ingest reports problems on stderr. Use `ingest --json` for a machine-readable report.

## Follow-up drafts

Only `followup` needs a config. Copy [`actiontrack.example.toml`](actiontrack.example.toml) to `./actiontrack.toml` (git-ignored) or `~/.config/actiontrack/actiontrack.toml`:

```toml
sender = "Your Name"

[gmail]
command = ["npx", "-y", "@artymclabin/gmail-mcp"]
draft_tool = "draft_email"

[[people]]
name = "Priya Nair"
email = "priya.nair@example.com"
aliases = ["Priya N."]
```

1. Complete the Gmail MCP server's own Google OAuth setup. See [`docs/technical_details.md`](docs/technical_details.md) §6.1. actiontrack never sees credentials.
2. Run `followup --dry-run` first to check each email.
3. Run `followup <owner>` or `followup --all`, then review and send from Gmail Drafts.

Each run creates new drafts. If one was created for the same Person in the last 24 hours, you get a warning and the draft is still created. People missing from the roster, or with no open items, are skipped and reported.

## Safety

- **Drafts only.** actiontrack calls the single configured create-draft tool and nothing else. A `draft_tool` name containing `send`, `reply` or `forward` is rejected at config load.
- No credentials are stored in the config or the database. The database file is owner-readable only.
- Note text is data: it is never executed and only reaches the MCP server as draft fields.

## Known limits

- **Items don't retire when notes change.** Rewording a task line creates a new item, and removing a line or a whole note leaves its items open. Use `actiontrack done <id>` to clear them. Done is permanent, and there is no reopen.
- Items can't be edited, reassigned or deleted from the CLI. Fix the note and re-ingest.
- `followup` has been tested against a fake MCP server. Check one real draft in Gmail before relying on it.
- Folders are not scanned recursively, and email is plain text only.

## Project docs

| File | Contents |
|---|---|
| [`docs/frd.md`](docs/frd.md) | What each command does (`FR-<n>` ids, acceptance examples against `notes/`) |
| [`docs/nfrd.md`](docs/nfrd.md) | Qualities every change must keep (`NFR-<n>`) |
| [`docs/technical_details.md`](docs/technical_details.md) | Architecture, schema, testing, demo walkthrough |
| [`GLOSSARY.md`](GLOSSARY.md) | Domain terms (Meeting Note, Owner, Due Phrase, Duplicate, …) |
| [`docs/adr/`](docs/adr/) | Decisions already made |
| [`docs/specs/`](docs/specs/) | The build queue; all nine specs are done |

`notes/` is the shared sample data and test fixture. Treat it as read-only.
