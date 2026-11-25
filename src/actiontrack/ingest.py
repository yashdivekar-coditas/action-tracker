"""Run one ingest over a folder: scan, parse, store, and build the report (FR-1, FR-12).

Per-note failures never escape: they become Malformed Notes (NFR-2). Store
failures abort the run, and `store.transaction` rolls everything back.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from actiontrack import config, dates, items, notes, owners, store

NOTE_SUFFIX = ".md"


class FolderError(Exception):
    """The notes folder could not be listed."""


@dataclass(frozen=True)
class MalformedNote:
    """A skipped note and why, as shown in the report (FR-3)."""

    file: str
    reason: str


@dataclass(frozen=True)
class ParsedNote:
    """A valid Meeting Note and the Action Item occurrences found in it."""

    note: notes.Note
    occurrences: list[items.Occurrence]


@dataclass(frozen=True)
class UnresolvedDuePhrase:
    """A Due Phrase no FR-8 rule matched, as shown in the report (FR-12)."""

    file: str
    line: int
    due_phrase: str


@dataclass(frozen=True)
class IngestedNote:
    """A Meeting Note read this run, with the header it was stored with."""

    file: str
    note: notes.Note

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "title": self.note.title,
            "meeting_date": self.note.meeting_date.isoformat(),
            "attendees": list(self.note.attendees),
        }


@dataclass
class IngestReport:
    """The result of one ingest run.

    The `to_dict()` keys are a public `--json` contract: add keys, never rename them (NFR-6).
    `items_merged` counts repeats attached to an existing item (FR-9) and items merged by a correction (FR-11).
    """

    ignored: int = 0
    items_new: int = 0
    items_merged: int = 0
    items_done: int = 0
    ingested_notes: list[IngestedNote] = field(default_factory=list)
    malformed_notes: list[MalformedNote] = field(default_factory=list)
    ambiguous_owners: list[dict[str, Any]] = field(default_factory=list)
    unknown_owners: list[dict[str, Any]] = field(default_factory=list)
    unassigned_items: list[dict[str, Any]] = field(default_factory=list)
    unresolved_due_phrases: list[UnresolvedDuePhrase] = field(default_factory=list)

    @property
    def notes_read(self) -> int:
        return len(self.ingested_notes)

    @property
    def malformed(self) -> int:
        return len(self.malformed_notes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "notes_read": self.notes_read,
            "malformed": self.malformed,
            "ignored": self.ignored,
            "items_new": self.items_new,
            "items_merged": self.items_merged,
            "items_done": self.items_done,
            "notes": [n.to_dict() for n in self.ingested_notes],
            "malformed_notes": [{"file": m.file, "reason": m.reason} for m in self.malformed_notes],
            "ambiguous_owners": self.ambiguous_owners,
            "unknown_owners": self.unknown_owners,
            "unassigned_items": self.unassigned_items,
            "unresolved_due_phrases": [
                {"file": u.file, "line": u.line, "due_phrase": u.due_phrase} for u in self.unresolved_due_phrases
            ],
        }


def run(folder: Path, db_path: Path, roster: Sequence[config.Person] = ()) -> IngestReport:
    """Ingest every `.md` file directly inside `folder` into the database at `db_path`.

    `roster` is the People Roster from the config (empty without one), used for Owners
    that match no Attendee (FR-7 step 5).

    Raises `FolderError` if the folder can't be listed (before the database is touched)
    and `store.StoreError` if the database fails (the run is rolled back).
    """
    files = _scan(folder, skip=db_path)
    report = IngestReport()
    with store.transaction(db_path) as db:
        for path in files:
            if not path.name.lower().endswith(NOTE_SUFFIX):
                report.ignored += 1
                continue
            parsed = _parse(path)
            if isinstance(parsed, notes.Malformed):  # FR-3: skipped whole, no items stored
                report.malformed_notes.append(MalformedNote(path.name, parsed.reason))
                continue
            note_path = path.resolve()
            db.upsert_note(note_path, parsed.note)
            meeting_date = parsed.note.meeting_date
            for occurrence in parsed.occurrences:
                due_date = _resolve_due(occurrence, meeting_date, path.name, report)
                owner = owners.resolve(occurrence.owner_part, parsed.note.attendees, roster)
                result = db.record_occurrence(note_path, occurrence, meeting_date, due_date, owner=owner)
                _report_owner(report, path.name, occurrence, owner, result.item_id)
                report.items_new += result.new_item
                report.items_merged += result.duplicate + result.merged
                report.items_done += result.newly_done
            report.ingested_notes.append(IngestedNote(path.name, parsed.note))
        # A later line can merge an item an earlier entry names, so report the live id (FR-11, FR-12).
        for entry in (*report.ambiguous_owners, *report.unknown_owners, *report.unassigned_items):
            entry["item_id"] = db.live_id(entry["item_id"])
    return report


def _resolve_due(occurrence: items.Occurrence, meeting_date: date, file: str, report: IngestReport) -> date | None:
    """The occurrence's Due Date (FR-8); an unresolved Due Phrase is kept and reported (FR-12)."""
    if occurrence.due_phrase is None:
        return None
    due_date = dates.resolve_due_phrase(occurrence.due_phrase, meeting_date)
    if due_date is None:
        report.unresolved_due_phrases.append(UnresolvedDuePhrase(file, occurrence.line_no, occurrence.due_phrase))
    return due_date


def _report_owner(
    report: IngestReport, file: str, occurrence: items.Occurrence, owner: owners.Resolution, item_id: int
) -> None:
    """List an unclear owner so it can be fixed in the note or roster (FR-12)."""
    where = {"file": file, "line": occurrence.line_no, "item_id": item_id}
    if owner.kind is owners.OwnerKind.AMBIGUOUS:
        report.ambiguous_owners.append(
            {**where, "written_owner": occurrence.owner_part, "candidates": list(owner.candidates)}
        )
    elif owner.kind is owners.OwnerKind.UNKNOWN:
        report.unknown_owners.append({**where, "written_owner": occurrence.owner_part})
    elif owner.kind is owners.OwnerKind.UNASSIGNED:
        report.unassigned_items.append({**where, "task": occurrence.task})


def _scan(folder: Path, skip: Path) -> list[Path]:
    """Files directly inside `folder`, sorted by name so ids and reports are deterministic (NFR-3).

    `skip` is the database: with `ingest .` it lives in the notes folder and would
    otherwise be counted as ignored from the second run on.
    """
    try:
        return sorted(
            (p for p in folder.iterdir() if p.is_file() and not _same_file(p, skip)),
            key=lambda p: p.name,
        )
    except OSError as exc:
        raise FolderError(f"cannot read folder {folder}: {exc.strerror or exc}") from exc


def _same_file(path: Path, other: Path) -> bool:
    try:
        return path.samefile(other)
    except OSError:  # `other` doesn't exist yet
        return False


def _parse(path: Path) -> ParsedNote | notes.Malformed:
    """Read, parse and extract one note; any failure becomes a Malformed reason."""
    try:
        note = notes.parse(path.read_bytes(), path.name)
        if isinstance(note, notes.Malformed):
            return note
        return ParsedNote(note, items.extract(note.text))
    except Exception as exc:  # NFR-2: one bad note must never stop the run
        return notes.Malformed(f"unreadable: {exc}")
