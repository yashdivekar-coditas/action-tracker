# 04 — Configuration: `actiontrack.toml` and the People Roster

Status: done
Blocked by: 01
Requirements: FR-18, FR-7 (roster input), NFR-1 (draft-tool validation), NFR-4

## Problem Statement

Notes only contain names, never email addresses, and the tool has to know which Gmail MCP server to talk to and who signs the emails. That information must live somewhere the team can maintain. It must be checked early so mistakes surface as clear errors rather than wrong emails, and it must never hold secrets.

## Solution

A single `actiontrack.toml` holds the sender name, the Gmail MCP server's launch command and create-draft tool name, and the People Roster (each Person's full name, email and aliases). It is found automatically, validated whenever it is loaded, and rejects any setting that could make the tool send email. `ingest`, `list` and `done` work without it; `followup` requires it.

## User Stories

1. As a meeting organiser, I want to keep all settings in one `actiontrack.toml`, so that there's a single file to maintain.
2. As a meeting organiser, I want the config found from `--config`, then `./actiontrack.toml`, then `~/.config/actiontrack/actiontrack.toml`, so that I can keep it per project or per machine.
3. As a meeting organiser, I want `ingest`, `list` and `done` to work without any config, so that I can start tracking before setting up email.
4. As a meeting organiser, I want to list each Person with their full name and email, so that follow-ups reach the right inbox.
5. As a meeting organiser, I want to give a Person aliases (e.g. `anita`, `Priya N.`), so that nicknames and handles in notes resolve to them.
6. As a meeting organiser, I want to set the sender name used to sign follow-up emails, so that drafts are ready to send as me.
7. As a meeting organiser, I want to set the Gmail MCP server's launch command as a list of arguments, so that I can use whichever server I've set up.
8. As a meeting organiser, I want to set the server's create-draft tool name, so that servers with different tool names work.
9. As a meeting organiser, I want a config whose draft tool name contains `send`, `reply` or `forward` to be rejected with a clear error, so that a typo can never make the tool send email.
10. As a meeting organiser, I want a Person entry missing a name or email rejected with the entry's position, so that I can fix it quickly.
11. As a meeting organiser, I want two People with the same full name, or an alias shared by two People, rejected, so that the roster itself is never ambiguous.
12. As a meeting organiser, I want invalid TOML reported with its line number, so that I can fix syntax errors.
13. As a meeting organiser, I want config errors to exit `2` with the file path, so that I know which file is wrong.
14. As a meeting organiser, I want `--config` pointing to a missing file to be an error, so that a wrong path isn't silently ignored.
15. As a meeting organiser, I want a missing config to be an error only for `followup`, with a message saying where it was looked for, so that I know what to create.
16. As a security-minded user, I want the config to hold no passwords or tokens, so that it's safe to share inside the team.
17. As a meeting organiser, I want an example config shipped with the project, so that I can copy and fill it in.
18. As a meeting organiser, I want unknown keys in the config to cause a warning rather than an error, so that a stray key doesn't block me but I still notice it.

## Implementation Decisions

- **New module `config`:** finds and loads the file with the stdlib TOML reader and returns a validated config with `sender`, `gmail.command` (argument list), `gmail.draft_tool`, and `people` (name, email, aliases). Validation errors are a single error type carrying the file path and a message; the CLI maps them to exit `2`.
- **When it loads:** `ingest` loads the config if one is found (for roster fallback, spec 05); `followup` requires one; `list` and `done` never load it. Any command that loads it validates all of it.
- **Validation rules:** `gmail.command` is a non-empty list of strings; `gmail.draft_tool` is non-empty and doesn't contain `send`, `reply` or `forward` (case-insensitive); every person has a non-empty name and an email containing `@`; full names and aliases are unique case-insensitively across the roster. `sender` is required only when `followup` runs.
- **No secrets:** the schema has no fields for credentials. Gmail authorisation belongs to the MCP server (ADR-0001).
- **Example file:** an `actiontrack.example.toml` is committed; the real `actiontrack.toml` is git-ignored.

## Testing Decisions

- Through the CLI seam: write a config into the temp folder, run `ingest` (which loads it when present), and assert the exit code and stderr. Valid-config behaviour is proven by later specs (05 roster fallback, 09 follow-ups).
- **Cases:** lookup order (`--config` beats `./` beats home, with home redirected via the environment in tests); missing `--config` file → 2; bad TOML → 2 with line; draft tool `send_message` → 2; person without email → 2; duplicate alias → 2; unknown key → warning on stderr, exit 0; no config → `ingest` still exits 0.
- **Prior art:** specs 01–02 harness.

## Out of Scope

- Editing the roster from the CLI.
- Importing people from Google Contacts or a directory.
- Choosing the default Gmail MCP server (open item; spec 09 notes).

## Further Notes

- Glossary terms used: Person, People Roster, Follow-up Draft.
