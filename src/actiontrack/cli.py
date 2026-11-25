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

from actiontrack import ingest, store

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
    except UsageError as exc:
        _error(str(exc))
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
    folder: Path = args.folder
    if not folder.is_dir():
        raise UsageError(f"folder not found: {folder}")
    try:
        report = ingest.run(folder, options.db)
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


# --- output -----------------------------------------------------------------------


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


def _printable(text: str) -> str:
    """Escape control characters so note text can't drive the terminal (NFR-4)."""
    return "".join(ch if ch.isprintable() else ascii(ch)[1:-1] for ch in text)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _error(message: str) -> None:
    print(f"{PROG}: error: {message}", file=sys.stderr)
