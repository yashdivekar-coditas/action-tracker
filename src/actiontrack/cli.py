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
import shutil
import sys
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from actiontrack import config, followup, gmail, ingest, owners, store

PROG = "actiontrack"

# Exit codes (NFR-6).
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

DEFAULT_DB = Path(".actiontrack.db")
ENV_DB = "ACTIONTRACK_DB"
ENV_TODAY = "ACTIONTRACK_TODAY"
LIST_STATUSES = ("open", "done", "overdue")
UNASSIGNED = "unassigned"  # the `list --owner` value that selects Unassigned items

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
        description=(
            "Show stored Action Items: Open ones by default, Overdue first (most late first), "
            "then by Due Date with undated items last. Filters combine with AND."
        ),
    )
    list_.add_argument(
        "--status", choices=LIST_STATUSES, help="only items with this status; open includes Overdue (default: open)"
    )
    list_.add_argument("--all", action="store_true", help="show items of every status (overrides --status)")
    list_.add_argument(
        "--due-before", type=_day_argument, metavar="YYYY-MM-DD", help="only items due strictly before this date"
    )
    list_.add_argument(
        "--owner", help="only items owned by this Person: full name, alias or unique first name; or 'unassigned'"
    )
    list_.add_argument("--json", action="store_true", help="print the items as a JSON array")
    list_.set_defaults(handler=_cmd_list)

    followup_ = commands.add_parser(
        "followup",
        parents=[_global_options_parser()],
        help="compose follow-up emails from Open items",
        description="Compose one plain-text email per Person listing their Open items, Overdue first.",
    )
    followup_.add_argument("owner", nargs="?", help="the Person: full name, alias or unique first name")
    followup_.add_argument("--all", action="store_true", help="one email for every Person with Open items")
    followup_.add_argument("--dry-run", action="store_true", help="print the emails and create nothing")
    followup_.set_defaults(handler=_cmd_followup)

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
    today = date.today() if today_text is None else _parse_day(today_text, "--today")
    return GlobalOptions(db=db, config=args.config, today=today)


def _parse_day(text: str, flag: str) -> date:
    # fromisoformat alone also accepts forms like 20261015 and 2026-W42-1.
    if _ISO_DAY.fullmatch(text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    raise UsageError(f"{flag} must be a YYYY-MM-DD date, got {text!r}")


def _day_argument(text: str) -> str:
    """argparse `type` for `--due-before`: the validated ISO date text; argparse turns the error into exit 2."""
    try:
        return _parse_day(text, "--due-before").isoformat()
    except UsageError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


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
                owner = _resolve_owner_filter(args.owner, db.attendees(), options)
                stored = db.list_items(
                    options.today,
                    status=None if args.all else args.status or "open",
                    due_before=args.due_before,
                    owner=owner,
                    unassigned=_is_unassigned(args.owner),
                )
        else:
            _resolve_owner_filter(args.owner, [], options)  # with no database only the roster is known
    except store.StoreError as exc:
        _error(str(exc))
        return EXIT_FAILED

    if args.json:
        print(json.dumps([_item_to_dict(item) for item in stored], ensure_ascii=False, indent=2))
    else:
        _print_items_table(stored)
    return EXIT_OK


def _is_unassigned(written: str | None) -> bool:
    return written is not None and written.casefold() == UNASSIGNED


def _resolve_owner_filter(written: str | None, attendees: list[str], options: GlobalOptions) -> str | None:
    """The one known Person `--owner` names (None for no filter or `unassigned`); no match or several exit 2 (FR-13)."""
    if written is None or _is_unassigned(written):
        return None
    loaded = _load_config(options)
    return _resolve_person(written, attendees, loaded.people if loaded else (), "--owner")


def _resolve_person(written: str, attendees: list[str], roster: tuple[config.Person, ...], label: str) -> str:
    matches = owners.find_person(written, attendees, roster)
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise UsageError(f"{label} {written!r} is ambiguous: {', '.join(matches)}")
    known = ", ".join(dict.fromkeys([*attendees, *(person.name for person in roster)]))
    raise UsageError(f"{label} {written!r} matches nobody; known people: {known or 'none'}")


@dataclass(frozen=True)
class PlannedDraft:
    """A Follow-up Draft ready to create, with the Person and the Open items it lists (for the history)."""

    person: str
    item_ids: list[int]
    draft: followup.FollowupDraft


@dataclass(frozen=True)
class Skip:
    """A Person who gets no Follow-up Draft, and why."""

    person: str
    reason: str


def _cmd_followup(args: argparse.Namespace, options: GlobalOptions) -> int:
    """Compose the Follow-up Drafts (FR-15), then print them (`--dry-run`) or save them in Gmail (FR-17)."""
    if args.all == (args.owner is not None):
        raise UsageError("give one <owner> or --all, not both or neither")
    loaded = _load_config(options, required=True)
    assert loaded is not None  # required=True raises instead of returning None
    if not loaded.sender:
        raise UsageError(f"{loaded.path}: sender is required by followup")
    try:
        planned, skips = _plan_drafts(args, options, loaded)
    except store.StoreError as exc:
        _error(str(exc))
        return EXIT_FAILED
    if args.dry_run:
        return _print_dry_run(planned, skips)
    return _create_drafts(loaded, options.db, planned, skips)


def _plan_drafts(
    args: argparse.Namespace, options: GlobalOptions, loaded: config.Config
) -> tuple[list[PlannedDraft], list[Skip]]:
    """One PlannedDraft per Person with Open items, and a Skip for each Person who cannot get one."""
    roster = {person.name: person for person in loaded.people}
    planned: list[PlannedDraft] = []
    skips: list[Skip] = []
    # A read must not leave a new, empty database behind, so with none there are simply no items.
    with store.transaction(options.db) if options.db.exists() else nullcontext() as db:
        if args.all:
            # Ambiguous and Unknown items have no Persons, so only resolved Owners get a draft.
            names = sorted({person for item in (db.list_items(options.today, status="open") if db else []) for person in item.persons})
        else:
            names = [_resolve_person(args.owner, db.attendees() if db else [], loaded.people, "<owner>")]
        for name in names:
            person = roster.get(name)
            items = db.list_items(options.today, status="open", owner=name) if db else []
            if person is None:
                skips.append(Skip(name, "not in the People Roster"))
            elif not items:
                skips.append(Skip(name, "no Open items"))
            else:
                planned.append(PlannedDraft(name, [item.id for item in items], followup.compose(person, items, loaded.sender)))
    return planned, skips


def _print_skips(skips: list[Skip]) -> None:
    for skip in skips:
        print(f"Skipped {_printable(f'{skip.person}: {skip.reason}')}")


def _print_dry_run(planned: list[PlannedDraft], skips: list[Skip]) -> int:
    for position, plan in enumerate(planned):
        if position:
            print("---")
        print(_printable(f"To: {plan.draft.to}"))
        print(_printable(f"Subject: {plan.draft.subject}"))
        print()
        print(*(_printable(line) for line in plan.draft.body.splitlines()), sep="\n")
    if planned:
        print()
    _print_skips(skips)
    print(f"Dry run: {_plural(len(planned), 'email')} composed, {len(skips)} skipped. Nothing was created.")
    return EXIT_OK


def _create_drafts(loaded: config.Config, db_path: Path, planned: list[PlannedDraft], skips: list[Skip]) -> int:
    """Save each Follow-up Draft in Gmail and summarise: created, skipped, failed (FR-17); exit 1 if any failed.

    Drafts that were created are printed before anything else can fail, and always recorded (FR-15, NFR-2).
    """
    outcomes: list[gmail.Outcome] = []
    if planned:
        try:
            _warn_recent_drafts(db_path, [plan.person for plan in planned])  # before the batch: it makes every draft at once
            outcomes = gmail.create_drafts(loaded.gmail_command, loaded.gmail_draft_tool, [plan.draft for plan in planned])
        except gmail.GmailError as exc:
            _error(f"cannot create Gmail drafts: {_printable(str(exc))}")
            return EXIT_FAILED
        except store.StoreError as exc:
            _error(str(exc))
            return EXIT_FAILED

    created: list[tuple[PlannedDraft, str | None]] = []
    failed = 0
    for plan, outcome in zip(planned, outcomes, strict=True):
        if outcome.error is None:
            created.append((plan, outcome.draft_id))
            print(f"Created draft for {_printable(plan.person)} ({_printable(plan.draft.to)}): {_printable(outcome.draft_id or '')}")
        else:
            failed += 1
            _error(f"draft for {_printable(plan.person)} failed: {_printable(outcome.error)}")
    recorded = True
    if created:
        try:
            with store.transaction(db_path) as db:
                for plan, draft_id in created:
                    db.record_draft(plan.person, plan.draft.to, draft_id, plan.item_ids)
        except store.StoreError as exc:
            recorded = False
            _error(f"the drafts above were created in Gmail but not recorded, so a repeat will not warn: {_printable(str(exc))}")
    _print_skips(skips)
    print(f"Drafts: {len(created)} created, {len(skips)} skipped, {failed} failed. Nothing was sent.")
    return EXIT_FAILED if failed or not recorded else EXIT_OK


def _warn_recent_drafts(db_path: Path, names: list[str]) -> None:
    """Warn for each Person who already got a draft in the last 24 hours; the new draft is still made (FR-15)."""
    with store.transaction(db_path) as db:
        for name in names:
            latest = db.latest_draft_at(name)
            if latest and datetime.now(timezone.utc) - latest < timedelta(hours=24):
                print(f"warning: a draft for {_printable(name)} was already created at {latest.isoformat()}", file=sys.stderr)


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


def _load_config(options: GlobalOptions, *, required: bool = False) -> config.Config | None:
    """Load and validate the config, printing its warnings; a `ConfigError` exits 2 (FR-18)."""
    loaded = config.load(options.config, required=required)
    for warning in loaded.warnings if loaded else ():
        print(f"{PROG}: warning: {_printable(warning)}", file=sys.stderr)
    return loaded


# --- output -----------------------------------------------------------------------

NO_VALUE = "—"
MIN_FLEXIBLE_WIDTH = 10


def _item_status(item: store.StoredItem) -> str:
    """`open` includes Overdue, as in `--status open`; `days_overdue` tells the two apart in JSON."""
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
        "days_overdue": item.days_overdue,
        "sources": [
            {
                "file": Path(source.path).name,
                "path": source.path,
                "line": source.line_no,
                "raw_line": source.raw_line,
                "checked": source.checked,
                "title": source.title,
                "meeting_date": source.meeting_date,
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


def _status_label(item: store.StoredItem) -> str:
    if item.days_overdue is not None:
        return f"overdue ({item.days_overdue}d)"
    return _item_status(item)


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_items_table(stored: list[store.StoredItem]) -> None:
    if not stored:
        print("No matching items.")
        return
    header = ("ID", "OWNER", "TASK", "DUE", "STATUS", "MEETING")
    rows = [
        (
            str(item.id),
            _printable(_owner_label(item)),
            _printable(item.task),
            _printable(item.due_date or item.due_phrase or NO_VALUE),
            _status_label(item),
            # Date first, so a truncated title never hides it.
            _printable(f"{item.latest_source.meeting_date} {item.latest_source.title}") if item.sources else NO_VALUE,
        )
        for item in stored
    ]
    widths = [max(len(row[col]) for row in (header, *rows)) for col in range(len(header))]
    available = shutil.get_terminal_size(fallback=(100, 24)).columns - 2 * (len(header) - 1)
    flexible = tuple(header.index(name) for name in ("OWNER", "TASK", "MEETING"))  # the columns that can be long
    while sum(widths) > available:
        widest = max(flexible, key=lambda col: widths[col])
        if widths[widest] <= MIN_FLEXIBLE_WIDTH:
            break  # nothing left to shrink; the table overflows rather than lose more text
        widths[widest] -= 1
    for row in (header, *rows):
        print("  ".join(_fit(cell, width).ljust(width) for cell, width in zip(row, widths)).rstrip())


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
