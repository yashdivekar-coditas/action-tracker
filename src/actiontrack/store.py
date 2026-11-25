"""All SQLite access. No other module knows SQL (NFR-9).

The schema is versioned with `PRAGMA user_version`; each entry in `_MIGRATIONS`
moves the database up one version. A whole ingest run happens inside one
`transaction()`, so any failure leaves the database as it was (NFR-2).
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from actiontrack.items import Occurrence
from actiontrack.notes import Note

# _MIGRATIONS[n] upgrades a database from user_version n to n + 1.
_MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        """
        CREATE TABLE notes (
          path          TEXT PRIMARY KEY,  -- absolute path
          title         TEXT NOT NULL,
          meeting_date  TEXT NOT NULL,     -- ISO yyyy-mm-dd
          attendees     TEXT NOT NULL,     -- JSON array of full names
          ingested_at   TEXT NOT NULL
        )
        """,
    ),
    (
        # AUTOINCREMENT: ids are never reused, even after the highest row is gone (FR-11).
        """
        CREATE TABLE items (
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          task          TEXT NOT NULL,     -- from the latest Source
          owner_kind    TEXT CHECK (owner_kind IN
                          ('person', 'team', 'ambiguous', 'unknown', 'unassigned')),  -- set by spec 05
          written_owner TEXT,              -- owner part as written, e.g. 'Priya N.'
          candidates    TEXT,              -- JSON array, Ambiguous Owners only
          due_phrase    TEXT,              -- raw, from the latest Source
          due_date      TEXT,              -- ISO, set by spec 03
          done_at       TEXT,              -- NULL = Open; set once, never cleared (FR-10)
          done_by       TEXT CHECK (done_by IN ('note', 'cli')),
          merged_into   INTEGER REFERENCES items (id)
        )
        """,
        """
        CREATE TABLE sources (
          note_path TEXT    NOT NULL REFERENCES notes (path),
          line_key  TEXT    NOT NULL,      -- normalised line text
          item_id   INTEGER NOT NULL REFERENCES items (id),
          line_no   INTEGER NOT NULL,
          raw_line  TEXT    NOT NULL,
          checked   INTEGER NOT NULL,      -- 1 if [x]/[X]
          PRIMARY KEY (note_path, line_key)  -- re-ingest idempotency (FR-11)
        )
        """,
        "CREATE INDEX sources_item ON sources (item_id)",
    ),
)

# NFR-4: meeting content stays private on a shared machine.
_DB_FILE_MODE = 0o600


class StoreError(Exception):
    """The database could not be opened or written; the run was rolled back."""


@dataclass(frozen=True)
class RecordResult:
    """What recording one occurrence changed, for the ingest report."""

    new_item: bool
    newly_done: bool


@dataclass(frozen=True)
class StoredSource:
    path: str
    line_no: int
    raw_line: str
    checked: bool


@dataclass(frozen=True)
class StoredItem:
    id: int
    written_owner: str | None
    task: str
    due_phrase: str | None
    due_date: str | None
    done: bool
    sources: tuple[StoredSource, ...]


class Store:
    """Access to the database inside one open transaction."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert_note(self, path: Path, note: Note) -> None:
        """Insert a Meeting Note, or refresh its header if the file was ingested before."""
        self._conn.execute(
            """
            INSERT INTO notes (path, title, meeting_date, attendees, ingested_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (path) DO UPDATE SET
              title        = excluded.title,
              meeting_date = excluded.meeting_date,
              attendees    = excluded.attendees,
              ingested_at  = excluded.ingested_at
            """,
            (
                str(path),
                note.title,
                note.meeting_date.isoformat(),
                json.dumps(list(note.attendees), ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )

    def record_occurrence(self, note_path: Path, occurrence: Occurrence, meeting_date: date) -> RecordResult:
        """Store one occurrence as a Source, creating its item unless this line was seen before (FR-11).

        A checked occurrence marks its item Done as of the Meeting Date; Done is never cleared (FR-10).
        """
        path = str(note_path)
        row = self._conn.execute(
            "SELECT item_id FROM sources WHERE note_path = ? AND line_key = ?",
            (path, occurrence.line_key),
        ).fetchone()
        item_fields = (occurrence.task, occurrence.owner_part, occurrence.due_phrase)
        if row is None:
            item_id = self._conn.execute(
                "INSERT INTO items (task, written_owner, due_phrase) VALUES (?, ?, ?)", item_fields
            ).lastrowid
            assert item_id is not None
        else:
            item_id = row[0]
            self._conn.execute(
                "UPDATE items SET task = ?, written_owner = ?, due_phrase = ? WHERE id = ?",
                (*item_fields, item_id),
            )
        self._conn.execute(
            """
            INSERT INTO sources (note_path, line_key, item_id, line_no, raw_line, checked)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (note_path, line_key) DO UPDATE SET
              line_no  = excluded.line_no,
              raw_line = excluded.raw_line,
              checked  = excluded.checked
            """,
            (path, occurrence.line_key, item_id, occurrence.line_no, occurrence.raw_line, occurrence.checked),
        )
        newly_done = occurrence.checked and self._mark_done(item_id, meeting_date, by="note")
        return RecordResult(new_item=row is None, newly_done=newly_done)

    def list_items(self) -> list[StoredItem]:
        """Every live (not merged) item in id order, each with its Sources."""
        sources: dict[int, list[StoredSource]] = {}
        for item_id, path, line_no, raw_line, checked in self._conn.execute(
            """
            SELECT s.item_id, s.note_path, s.line_no, s.raw_line, s.checked
            FROM sources s JOIN notes n ON n.path = s.note_path
            ORDER BY n.meeting_date, s.note_path, s.line_no
            """
        ):
            sources.setdefault(item_id, []).append(StoredSource(path, line_no, raw_line, bool(checked)))
        return [
            StoredItem(item_id, owner, task, due_phrase, due_date, done_at is not None,
                       tuple(sources.get(item_id, ())))
            for item_id, owner, task, due_phrase, due_date, done_at in self._conn.execute(
                """
                SELECT id, written_owner, task, due_phrase, due_date, done_at
                FROM items WHERE merged_into IS NULL ORDER BY id
                """
            )
        ]  # fmt: skip

    def _mark_done(self, item_id: int, when: date, *, by: str) -> bool:
        """Set Done once; returns whether this call changed it."""
        cursor = self._conn.execute(
            "UPDATE items SET done_at = ?, done_by = ? WHERE id = ? AND done_at IS NULL",
            (when.isoformat(), by, item_id),
        )
        return cursor.rowcount == 1


@contextmanager
def transaction(db_path: Path) -> Iterator[Store]:
    """Open the database, migrate it and yield a `Store`; commit on success, roll back on any error.

    Raises `StoreError` for any database or file-system failure.
    """
    try:
        conn = _connect(db_path)
    except (OSError, sqlite3.Error) as exc:
        raise StoreError(f"cannot open {db_path}: {exc}") from exc

    try:
        conn.execute("BEGIN IMMEDIATE")
        _migrate(conn)
        yield Store(conn)
        conn.execute("COMMIT")
    except sqlite3.Error as exc:
        _rollback(conn)
        raise StoreError(f"{db_path}: {exc}") from exc
    except BaseException:  # includes KeyboardInterrupt: an interrupted run must not half-commit
        _rollback(conn)
        raise
    finally:
        conn.close()


def _connect(db_path: Path) -> sqlite3.Connection:
    # Create the file ourselves so it is owner-only from the start (sqlite would use the umask).
    os.close(os.open(db_path, os.O_CREAT | os.O_RDWR, _DB_FILE_MODE))
    # isolation_level=None: we issue BEGIN/COMMIT explicitly, so DDL is transactional too.
    return sqlite3.connect(db_path, isolation_level=None)


def _migrate(conn: sqlite3.Connection) -> None:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > len(_MIGRATIONS):
        raise sqlite3.DatabaseError(
            f"created by a newer actiontrack (schema {version}, this version knows {len(_MIGRATIONS)})"
        )
    for target, statements in enumerate(_MIGRATIONS[version:], start=version + 1):
        for statement in statements:
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {target}")  # PRAGMA takes no bound parameters


def _rollback(conn: sqlite3.Connection) -> None:
    # A failed ROLLBACK must not mask the original error; SQLite discards the
    # uncommitted transaction anyway when the connection closes.
    with suppress(sqlite3.Error):
        if conn.in_transaction:
            conn.execute("ROLLBACK")
