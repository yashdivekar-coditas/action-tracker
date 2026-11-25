"""Command-line entry point: subcommands, global options, output and exit codes.

`main(argv)` is the only seam tests use (NFR-5): it takes the argument list and
returns the exit code, so the console script and the tests run the same path.
Human output goes to stdout; warnings and report problems go to stderr (NFR-6).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from actiontrack import config, ingest, store

PROG = "actiontrack"

# Exit codes (NFR-6).
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

DEFAULT_DB = Path(".actiontrack.db")
ENV_DB = "ACTIONTRACK_DB"
ENV_TODAY = "ACTIONTRACK_TODAY"
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


class UsageError(Exception):
    """Bad input from the user: reported on stderr with exit code 2."""


@dataclass(frozen=True)
class GlobalOptions:
    """Options shared by every command, resolved from flags, then environment, then defaults."""

    db: Path
    config: Path | None
    today: date


def main(argv: Sequence[str] | None = None) -> int:
    """Run actiontrack with `argv` (defaults to `sys.argv[1:]`) and return the exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits on --help (0) and on bad arguments (2)
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    try:
        options = _resolve_global_options(args)
        handler: Callable[[argparse.Namespace, GlobalOptions], int] = args.handler
        return handler(args, options)
    except (UsageError, config.ConfigError) as exc:
        _error(_printable(str(exc)))
        return EXIT_USAGE


# --- argument parsing -------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Track action items from markdown meeting notes and draft follow-ups.",
    )
    commands = parser.add_subparsers(title="commands", metavar="<command>", required=True)

    ingest = commands.add_parser(
        "ingest",
        parents=[_global_options_parser()],
        help="read every .md Meeting Note in a folder",
        description="Read every .md Meeting Note directly inside FOLDER and print a report.",
    )
    ingest.add_argument("folder", type=Path, help="folder of markdown Meeting Notes (not scanned recursively)")
    ingest.add_argument("--json", action="store_true", help="print the report as one JSON object")
    ingest.set_defaults(handler=_cmd_ingest)

    list_ = commands.add_parser(
        "list",
        parents=[_global_options_parser()],
        help="show stored Action Items",
        description="Show every stored Action Item in id order.",
    )
    list_.add_argument("--json", action="store_true", help="print the items as a JSON array")
    list_.set_defaults(handler=_cmd_list)

    done = commands.add_parser(
        "done",
        parents=[_global_options_parser()],
        help="mark an Action Item Done",
        description="Mark an Action Item Done for good; re-ingesting notes never reopens it.",
    )
    done.add_argument("id", type=int, help="id of the Action Item")
    done.add_argument("--json", action="store_true", help="print the item as JSON")
    done.set_defaults(handler=_cmd_done)

    return parser


def _global_options_parser() -> argparse.ArgumentParser:
    """Options every command accepts; an explicit flag beats its environment variable."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--db",
        type=Path,
        help=f"database file (default: ${ENV_DB} or ./{DEFAULT_DB})",
    )
    parent.add_argument("--config", type=Path, help="path to actiontrack.toml")
    # Hidden: pins "today" for tests and demos (NFR-3).
    parent.add_argument("--today", help=argparse.SUPPRESS)
    return parent


def _resolve_global_options(args: argparse.Namespace) -> GlobalOptions:
    db = args.db or Path(os.environ.get(ENV_DB) or DEFAULT_DB)
    # An explicit `--today ''` is an error, but an empty environment variable counts as unset.
    today_text: str | None = args.today if args.today is not None else os.environ.get(ENV_TODAY) or None
    return GlobalOptions(db=db, config=args.config, today=_parse_today(today_text))


def _parse_today(text: str | None) -> date:
    if text is None:
        return date.today()
    # fromisoformat alone also accepts forms like 20261015 and 2026-W42-1.
    if _ISO_DAY.fullmatch(text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    raise UsageError(f"--today must be a YYYY-MM-DD date, got {text!r}")


# --- commands ---------------------------------------------------------------------


def _cmd_ingest(args: argparse.Namespace, options: GlobalOptions) -> int:
    loaded = _load_config(options)  # optional; its People Roster is the FR-7 step 5 fallback
    folder: Path = args.folder
    if not folder.is_dir():
        raise UsageError(f"folder not found: {folder}")
    try:
        report = ingest.run(folder, options.db, loaded.people if loaded else ())
    except ingest.FolderError as exc:
        raise UsageError(str(exc)) from exc
    except store.StoreError as exc:
        _error(f"ingest failed, database unchanged: {exc}")
        return EXIT_FAILED

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_ingest_report(report)
    _warn_ingest_problems(report)
    return EXIT_OK


def _cmd_list(args: argparse.Namespace, options: GlobalOptions) -> int:
    stored: list[store.StoredItem] = []
    try:
        if options.db.exists():  # a read must not leave a new, empty database behind
            with store.transaction(options.db) as db:
                stored = db.list_items()
    except store.StoreError as exc:
        _error(str(exc))
        return EXIT_FAILED

    if args.json:
        print(json.dumps([_item_to_dict(item) for item in stored], ensure_ascii=False, indent=2))
    else:
        _print_items_table(stored)
    return EXIT_OK


def _cmd_done(args: argparse.Namespace, options: GlobalOptions) -> int:
    result: store.DoneResult | None = None
    try:
        if options.db.exists():  # an unknown id must not leave a new, empty database behind
            with store.transaction(options.db) as db:
                result = db.mark_done_by_id(args.id, options.today)
    except store.StoreError as exc:
        _error(str(exc))
        return EXIT_FAILED
    if result is None:
        _error(f"no Action Item with id {args.id}")
        return EXIT_FAILED

    if args.json:
        print(json.dumps(_item_to_dict(result.item), ensure_ascii=False, indent=2))
        return EXIT_OK
    if result.redirected_from is not None:
        print(f"#{result.redirected_from} was merged into #{result.item.id}")
    state = "already done" if result.already_done else "done"
    print(f"#{result.item.id} {state}: {_printable(_owner_label(result.item))}: {_printable(result.item.task)}")
    return EXIT_OK


def _load_config(options: GlobalOptions) -> config.Config | None:
    """Load and validate the config, printing its warnings; a `ConfigError` exits 2 (FR-18)."""
    loaded = config.load(options.config)
    for warning in loaded.warnings if loaded else ():
        print(f"{PROG}: warning: {_printable(warning)}", file=sys.stderr)
    return loaded


# --- output -----------------------------------------------------------------------

NO_VALUE = "—"


def _item_status(item: store.StoredItem) -> str:
    return "done" if item.done else "open"


def _item_to_dict(item: store.StoredItem) -> dict[str, object]:
    """One item in `list --json`; keys may be added, never renamed (NFR-6)."""
    return {
        "id": item.id,
        "owner_kind": item.owner_kind,
        "persons": list(item.persons),
        "written_owner": item.written_owner,
        "candidates": list(item.candidates),
        "task": item.task,
        "due_phrase": item.due_phrase,
        "due_date": item.due_date,
        "status": _item_status(item),
        "sources": [
            {
                "file": Path(source.path).name,
                "path": source.path,
                "line": source.line_no,
                "raw_line": source.raw_line,
                "checked": source.checked,
            }
            for source in item.sources
        ],
    }


def _owner_label(item: store.StoredItem) -> str:
    """Resolved Persons, or a label that makes an unclear owner stand out (FR-13)."""
    match item.owner_kind:
        case "person" | "team":
            return ", ".join(item.persons)
        case "ambiguous":
            return f"{item.written_owner} (ambiguous: {', '.join(item.candidates)})"
        case "unknown":
            return f"{item.written_owner} (unknown)"
        case "unassigned":
            return "unassigned"
        case _:  # stored before owner resolution; re-ingest fills it in
            return item.written_owner or NO_VALUE


def _print_items_table(stored: list[store.StoredItem]) -> None:
    # shortcut: basic aligned columns, no truncation; spec 07 adds terminal-width rendering.
    header = ("ID", "OWNER", "TASK", "DUE", "STATUS")
    rows = [
        (
            str(item.id),
            _printable(_owner_label(item)),
            _printable(item.task),
            _printable(item.due_date or item.due_phrase or NO_VALUE),
            _item_status(item),
        )
        for item in stored
    ]
    widths = [max(len(row[col]) for row in (header, *rows)) for col in range(len(header))]
    for row in (header, *rows):
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())



def _print_ingest_report(report: ingest.IngestReport) -> None:
    print(
        f"Ingested {_plural(report.notes_read, 'Meeting Note')}; "
        f"skipped {_plural(report.malformed, 'Malformed Note')}; "
        f"ignored {_plural(report.ignored, 'non-markdown file')}."
    )
    print(
        f"Action Items: {report.items_new} new, "
        f"{report.items_merged} merged as Duplicates, {report.items_done} newly Done."
    )


def _warn_ingest_problems(report: ingest.IngestReport) -> None:
    """Report problems go to stderr in both output modes, so stdout stays pipeable (NFR-6)."""
    for entry in report.malformed_notes:
        print(f"Malformed Note: {_printable(entry.file)}: {_printable(entry.reason)}", file=sys.stderr)
    for entry in report.unresolved_due_phrases:
        print(
            f"Unresolved Due Phrase: {_printable(entry.file)}:{entry.line}: {_printable(entry.due_phrase)}",
            file=sys.stderr,
        )
    for entry in report.ambiguous_owners:
        candidates = ", ".join(entry["candidates"])
        _warn_at("Ambiguous Owner", entry, f"{entry['written_owner']} ({candidates})")
    for entry in report.unknown_owners:
        _warn_at("Unknown Owner", entry, entry["written_owner"])
    for entry in report.unassigned_items:
        _warn_at("Unassigned", entry, entry["task"])


def _warn_at(label: str, entry: dict[str, Any], detail: str) -> None:
    print(f"{label}: {_printable(entry['file'])}:{entry['line']}: {_printable(detail)}", file=sys.stderr)


def _printable(text: str) -> str:
    """Escape control characters so note text can't drive the terminal (NFR-4)."""
    return "".join(ch if ch.isprintable() else ascii(ch)[1:-1] for ch in text)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _error(message: str) -> None:
    print(f"{PROG}: error: {message}", file=sys.stderr)
