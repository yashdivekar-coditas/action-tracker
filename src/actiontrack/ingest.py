"""Run one ingest over a folder: scan, parse, store, and build the report (FR-1, FR-12).

Per-note failures never escape: they become Malformed Notes (NFR-2). Store
failures abort the run, and `store.transaction` rolls everything back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from actiontrack import notes, store

NOTE_SUFFIX = ".md"


class FolderError(Exception):
    """The notes folder could not be listed."""


@dataclass(frozen=True)
class MalformedNote:
    """A skipped note and why, as shown in the report (FR-3)."""

    file: str
    reason: str


@dataclass
class IngestReport:
    """The result of one ingest run.

    The `to_dict()` keys are a public `--json` contract: add keys, never rename them (NFR-6).
    Item counts and the owner/due-phrase lists are filled by later specs.
    """

    notes_read: int = 0
    ignored: int = 0
    items_new: int = 0
    items_merged: int = 0
    items_done: int = 0
    malformed_notes: list[MalformedNote] = field(default_factory=list)
    ambiguous_owners: list[dict[str, Any]] = field(default_factory=list)
    unknown_owners: list[dict[str, Any]] = field(default_factory=list)
    unassigned_items: list[dict[str, Any]] = field(default_factory=list)
    unresolved_due_phrases: list[dict[str, Any]] = field(default_factory=list)

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
            "malformed_notes": [{"file": m.file, "reason": m.reason} for m in self.malformed_notes],
            "ambiguous_owners": self.ambiguous_owners,
            "unknown_owners": self.unknown_owners,
            "unassigned_items": self.unassigned_items,
            "unresolved_due_phrases": self.unresolved_due_phrases,
        }


def run(folder: Path, db_path: Path) -> IngestReport:
    """Ingest every `.md` file directly inside `folder` into the database at `db_path`.

    Raises `FolderError` if the folder can't be listed (before the database is touched)
    and `store.StoreError` if the database fails (the run is rolled back).
    """
    files = _scan(folder)
    report = IngestReport()
    with store.transaction(db_path) as db:
        for path in files:
            if not path.name.lower().endswith(NOTE_SUFFIX):
                report.ignored += 1
                continue
            parsed = _parse(path)
            if isinstance(parsed, notes.Malformed):
                report.malformed_notes.append(MalformedNote(path.name, parsed.reason))
                continue
            db.upsert_note(path.resolve(), parsed)
            report.notes_read += 1
    return report


def _scan(folder: Path) -> list[Path]:
    """Files directly inside `folder`, sorted by name so ids and reports are deterministic (NFR-3)."""
    try:
        return sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name)
    except OSError as exc:
        raise FolderError(f"cannot read folder {folder}: {exc.strerror or exc}") from exc


def _parse(path: Path) -> notes.Note | notes.Malformed:
    try:
        return notes.parse(path.read_bytes(), path.name)
    except Exception as exc:  # NFR-2: one bad note must never stop the run
        return notes.Malformed(f"unreadable: {exc}")
