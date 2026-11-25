# actiontrack

A Python CLI that ingests markdown meeting notes, tracks their action items, and creates Gmail **drafts** for follow-ups.

## Read before working
- `docs/specs/NN-*.md`: the build queue. Each spec has a `Status:` line and a `Blocked by:` line, so build specs in number order once their blockers are done, and set `Status: done` when a spec's tests pass.
- `docs/specs/index.md`: dependency graph, parallel waves and merge hotspots. Read it before starting a spec in a parallel session.
- `docs/frd.md`: what each command does. It is the spec, with stable `FR-<n>` ids and acceptance examples against `notes/`.
- `docs/nfrd.md`: qualities every change must keep (`NFR-<n>`).
- `docs/technical_details.md`: how it's built. Read it before creating or moving modules, changing the SQLite schema, or touching the ingest/followup flow.
- `GLOSSARY.md`: domain terms. Use them verbatim in code, tests and messages.
- `docs/adr/`: decisions already made. Read the ADRs before changing the Gmail adapter, owner resolution or duplicate handling.

This project's glossary and ADRs are the ones in this folder. The parent repo's `GLOSSARY.md` and `docs/adr/` belong to the unrelated Gatepass project.

## Hard rules
- **Drafts only.** The Gmail adapter calls the configured create-draft tool and nothing else (NFR-1). Changing that requires a new ADR.
- **Skip and report.** Any note content becomes a reported Malformed Note, never an uncaught exception (NFR-2).
- **Stable ids.** Never renumber or reuse item ids; re-ingest is idempotent (FR-11).
- **Stdlib plus `mcp`.** Ask before adding any other runtime dependency (NFR-7).

## Working
- Test-first: each FR/NFR rule gets a pytest test citing its id. Run `pytest`.
- Tests use only two seams: the CLI entry point (with a temp folder, temp `--db` and pinned `--today`) and the fake Gmail MCP server. Assert only on exit code, output and `--json`.
- `notes/` is the shared fixture. Treat it as read-only test data and pin `--today 2026-10-15` in tests that depend on dates.
- When behaviour changes, update `docs/frd.md` in the same change, and `GLOSSARY.md` when a term changes.
