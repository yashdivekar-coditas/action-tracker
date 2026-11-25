# actiontrack — Non-Functional Requirements

These are the qualities every actiontrack feature must have. Functional behaviour is in [`frd.md`](frd.md), and terms are in [`../GLOSSARY.md`](../GLOSSARY.md). Refer to requirements as `NFR-<n>`.

## NFR-1 Safety: drafts only, never send
- Email leaves actiontrack only as a Gmail draft. The Gmail adapter calls exactly one MCP tool: the configured create-draft tool.
- At startup the adapter refuses (with an error) a `draft_tool` name containing `send`, `reply` or `forward`, and it never calls any tool not named in config.
- **Test:** a fake MCP server records every tool call. `followup --all` against it produces only create-draft calls, and a config that names a send tool is rejected before any call.

## NFR-2 Robustness: skip and report, never crash on input
- No note content (binary, empty, huge lines, odd encodings, broken tables, unclosed code fences or front-matter) may raise an uncaught exception. Each per-note failure becomes a Malformed Note entry with a reason (FR-3).
- Each `ingest` run writes in a single SQLite transaction, so an interrupted run leaves the database as it was.
- `done` and `followup` never lose recorded Done status or draft history.
- **Test:** ingesting the sample `notes/` folder (which includes deliberately malformed files) completes with exit `0`, and a fuzz-style test feeds random bytes as `.md` files.

## NFR-3 Determinism
- The same notes, config, database and `--today` always give identical output, with the same order and the same ids.
- Only `followup` touches the network, and only through the MCP server. `ingest`, `list` and `done` work offline.

## NFR-4 Security and privacy
- No credentials are stored in config or the database. Gmail authorisation is owned by the MCP server.
- Note text is treated as data: it is never executed, never interpolated into a shell command, and never passed to the MCP server except as draft fields.
- The MCP server is started from the config's argument list (no shell). The database file is created readable by its owner only.

## NFR-5 Testability
- Tests use pytest and use exactly two seams. (1) The CLI entry point is called in-process with a temp notes folder, a temp database and a pinned `--today`; tests assert only on exit code, output and `--json`. (2) The Gmail MCP server is replaced by a fake stdio server that records every tool call. No test calls internal functions or reads tables directly.
- Parsing, Owner resolution, Due Date resolution and Duplicate detection are still written as pure functions (NFR-9), but they are tested through the CLI using small crafted notes.
- At least one test per rule row in FR-7 and FR-8, and one per Malformed reason in FR-3.
- An end-to-end test ingests the provided `notes/` folder with `--today 2026-10-15` and asserts every row of the FRD's acceptance examples (FRD §6).
- Gmail is replaced by a fake MCP server in tests. No test needs network or real credentials.
- The suite runs with one command: `pytest`.

## NFR-6 CLI interface contract
- Human output goes to stdout and warnings/report problems to stderr.
- `--json` on `list`, `ingest` and `done` gives a documented, stable JSON shape for scripting. Adding fields is allowed; renaming or removing them is a breaking change.
- Exit codes: `0` success (including ingest runs with Malformed Notes); `1` operation failed (unknown id, draft creation failed); `2` usage error.
- `--help` on every command lists its options with one-line descriptions.

## NFR-7 Dependencies and runtime
- Python 3.11 or newer, using the standard library (`argparse`, `sqlite3`, `tomllib`, `datetime`, `re`).
- The single runtime dependency is the official `mcp` Python SDK, imported only by the Gmail adapter, so `ingest`/`list`/`done` work even when it fails to import.
- `pytest` is a dev-only dependency.
- Installs as an `actiontrack` console script.

## NFR-8 Portability
- Runs on macOS and Linux. File paths are handled with `pathlib`.
- Notes are read as UTF-8 (a BOM is accepted). Output is UTF-8.

## NFR-9 Maintainability
- Modules follow the flow: note parsing → owner/date resolution → store → commands → Gmail adapter. Only the adapter knows about MCP, and only the store knows about SQLite.
- Code, tests and messages use the terms from `GLOSSARY.md` verbatim.
- Tests and commits cite FR/NFR ids.

## Not committed
- Performance targets. The sample has about 36 notes; no throughput or latency bound is promised.
- Windows support.
- Concurrent use of one database by several processes.
