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

from actiontrack.items import Occurrence, dedupe_key
from actiontrack.notes import Note
from actiontrack.owners import Resolution

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
          due_date      TEXT,              -- ISO, resolved from due_phrase (FR-8)
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
    (
        # One row per Owner: several for a shared or Team Item (FR-7). Persons are full names.
        """
        CREATE TABLE item_owners (
          item_id  INTEGER NOT NULL REFERENCES items (id),
          person   TEXT    NOT NULL,
          PRIMARY KEY (item_id, person)
        )
        """,
    ),
    (
        # Nullable: rows from before spec 06 get their key on the next ingest.
        "ALTER TABLE items ADD COLUMN dedupe_key TEXT",
        "CREATE UNIQUE INDEX items_live_key ON items (dedupe_key) WHERE merged_into IS NULL",
    ),
    (
        # Each Source keeps what its line said, so an item's fields are derived from its Sources (FR-9).
        # Before this version every item had one Source, so the item's own values are that Source's.
        "ALTER TABLE sources ADD COLUMN task TEXT",
        "ALTER TABLE sources ADD COLUMN written_owner TEXT",
        "ALTER TABLE sources ADD COLUMN due_phrase TEXT",
        "ALTER TABLE sources ADD COLUMN due_date TEXT",
        """
        UPDATE sources SET
          task          = (SELECT task FROM items WHERE items.id = sources.item_id),
          written_owner = (SELECT written_owner FROM items WHERE items.id = sources.item_id),
          due_phrase    = (SELECT due_phrase FROM items WHERE items.id = sources.item_id),
          due_date      = (SELECT due_date FROM items WHERE items.id = sources.item_id)
        """,
    ),
)

# NFR-4: meeting content stays private on a shared machine.
_DB_FILE_MODE = 0o600


class StoreError(Exception):
    """The database could not be opened or written; the run was rolled back."""


@dataclass(frozen=True)
class DoneResult:
    """What `mark_done_by_id` did, for the `done` command (FR-14)."""

    item: StoredItem
    already_done: bool
    redirected_from: int | None  # the id asked for, when it had been merged into `item` (FR-11)


@dataclass(frozen=True)
class RecordResult:
    """What recording one occurrence changed, for the ingest report."""

    item_id: int
    new_item: bool
    duplicate: bool  # a repeat attached to an existing item as another Source (FR-9)
    merged: bool  # a correction made two items one; `item_id` is the survivor (FR-11)
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
    owner_kind: str | None  # None only for items stored before owner resolution existed
    persons: tuple[str, ...]
    candidates: tuple[str, ...]
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

    def record_occurrence(
        self,
        note_path: Path,
        occurrence: Occurrence,
        meeting_date: date,
        due_date: date | None,
        *,
        owner: Resolution,
    ) -> RecordResult:
        """Store one occurrence as a Source of an item (FR-9, FR-11).

        A line seen before updates its item in place; otherwise an item with the same dedupe key
        gains the Source as a Duplicate; otherwise a new item is created. If re-resolving a known
        line gives its item the key of another live item, the two merge into the lower id (FR-11).

        The Source keeps its own task, written owner, Due Phrase and Due Date, rewritten on every
        ingest so a rule fix applies on the next run (FR-8). The item's fields are then re-derived
        from all its Sources, so they do not depend on ingest order (FR-9).

        A checked occurrence marks its item Done as of the Meeting Date; Done is never cleared (FR-10).
        """
        path = str(note_path)
        row = self._conn.execute(
            "SELECT item_id FROM sources WHERE note_path = ? AND line_key = ?",
            (path, occurrence.line_key),
        ).fetchone()
        key = dedupe_key(owner.kind.value, owner.persons, occurrence.owner_part, occurrence.task)
        duplicate = merged = False
        if row is not None:
            item_id = row[0]
            if (other := self._live_with_key(key, excluding=item_id)) is not None:
                item_id, merged = min(item_id, other), True
                self._merge_items(loser=max(row[0], other), survivor=item_id)
            self._conn.execute("UPDATE items SET dedupe_key = ? WHERE id = ?", (key, item_id))
        elif (live := self._live_with_key(key)) is not None:
            item_id, duplicate = live, True
        else:
            item_id = self._conn.execute(
                "INSERT INTO items (task, dedupe_key) VALUES (?, ?)", (occurrence.task, key)
            ).lastrowid
            assert item_id is not None
        self._conn.execute(
            """
            INSERT INTO sources (note_path, line_key, item_id, line_no, raw_line, checked,
                                 task, written_owner, due_phrase, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (note_path, line_key) DO UPDATE SET
              line_no       = excluded.line_no,
              raw_line      = excluded.raw_line,
              checked       = excluded.checked,
              task          = excluded.task,
              written_owner = excluded.written_owner,
              due_phrase    = excluded.due_phrase,
              due_date      = excluded.due_date
            """,
            (
                path, occurrence.line_key, item_id, occurrence.line_no, occurrence.raw_line, occurrence.checked,
                occurrence.task, occurrence.owner_part, occurrence.due_phrase,
                due_date.isoformat() if due_date else None,
            ),
        )  # fmt: skip
        self._derive_item_fields(item_id)
        self._set_owner(item_id, owner)
        newly_done = occurrence.checked and self._mark_done(item_id, meeting_date, by="note")
        return RecordResult(
            item_id=item_id, new_item=row is None and not duplicate, duplicate=duplicate, merged=merged,
            newly_done=newly_done,
        )  # fmt: skip

    def _live_with_key(self, key: str, *, excluding: int = 0) -> int | None:
        """The id of the live (not merged) item with this dedupe key, other than `excluding`."""
        row = self._conn.execute(
            "SELECT id FROM items WHERE dedupe_key = ? AND merged_into IS NULL AND id != ?", (key, excluding)
        ).fetchone()
        return row[0] if row else None

    def live_id(self, item_id: int) -> int | None:
        """`item_id`, or the item it was merged into (FR-11), or None if there is no such id.

        Merges repoint chains, so one hop is enough.
        """
        if not -(2**63) <= item_id < 2**63:  # beyond SQLite's INTEGER range, so no such id (and sqlite3 would raise)
            return None
        row = self._conn.execute("SELECT COALESCE(merged_into, id) FROM items WHERE id = ?", (item_id,)).fetchone()
        return row[0] if row else None

    def mark_done_by_id(self, item_id: int, when: date) -> DoneResult | None:
        """Mark the live item behind `item_id` Done, set once, by the CLI (FR-14); None if the id is unknown."""
        live = self.live_id(item_id)
        if live is None:
            return None
        already_done = not self._mark_done(live, when, by="cli")
        item = next(i for i in self.list_items() if i.id == live)
        return DoneResult(item, already_done, item_id if live != item_id else None)

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
        persons: dict[int, list[str]] = {}
        for item_id, person in self._conn.execute("SELECT item_id, person FROM item_owners ORDER BY rowid"):
            persons.setdefault(item_id, []).append(person)
        return [
            StoredItem(item_id, kind, tuple(persons.get(item_id, ())), tuple(json.loads(candidates or "[]")),
                       owner, task, due_phrase, due_date, done_at is not None, tuple(sources.get(item_id, ())))
            for item_id, kind, candidates, owner, task, due_phrase, due_date, done_at in self._conn.execute(
                """
                SELECT id, owner_kind, candidates, written_owner, task, due_phrase, due_date, done_at
                FROM items WHERE merged_into IS NULL ORDER BY id
                """
            )
        ]  # fmt: skip

    def _derive_item_fields(self, item_id: int) -> None:
        """Set the item's task, written owner, Due Phrase and Due Date from its Sources (FR-9).

        Task and written owner come from the latest Source; the Due Phrase and Due Date from the
        latest Source that has a Due Phrase, else none. Latest means the greatest Meeting Date,
        then file path, then line number.
        """
        sources = self._conn.execute(
            """
            SELECT s.task, s.written_owner, s.due_phrase, s.due_date
            FROM sources s JOIN notes n ON n.path = s.note_path
            WHERE s.item_id = ?
            ORDER BY n.meeting_date DESC, s.note_path DESC, s.line_no DESC
            """,
            (item_id,),
        ).fetchall()
        task, written_owner, _, _ = sources[0]
        due_phrase, due_date = next(
            ((phrase, due) for _, _, phrase, due in sources if phrase is not None), (None, None)
        )
        self._conn.execute(
            "UPDATE items SET task = ?, written_owner = ?, due_phrase = ?, due_date = ? WHERE id = ?",
            (task, written_owner, due_phrase, due_date, item_id),
        )

    def _merge_items(self, *, loser: int, survivor: int) -> None:
        """Fold `loser` into `survivor`: same dedupe key, so same Persons; Done wins (FR-11).

        The loser is retired first so the survivor can take the shared key without tripping `items_live_key`.
        """
        self._conn.execute("UPDATE items SET merged_into = ? WHERE id = ?", (survivor, loser))
        self._conn.execute("UPDATE items SET merged_into = ? WHERE merged_into = ?", (survivor, loser))
        self._conn.execute("UPDATE sources SET item_id = ? WHERE item_id = ?", (survivor, loser))
        self._conn.execute("DELETE FROM item_owners WHERE item_id = ?", (loser,))
        self._conn.execute(
            """
            UPDATE items SET (done_at, done_by) = (SELECT done_at, done_by FROM items WHERE id = ?)
            WHERE id = ? AND done_at IS NULL
            """,
            (loser, survivor),
        )
        self._derive_item_fields(survivor)

    def _set_owner(self, item_id: int, owner: Resolution) -> None:
        """Replace the item's owner fields with a fresh resolution (FR-11: updated in place)."""
        self._conn.execute(
            "UPDATE items SET owner_kind = ?, candidates = ? WHERE id = ?",
            (owner.kind.value, json.dumps(list(owner.candidates), ensure_ascii=False) if owner.candidates else None,
             item_id),
        )  # fmt: skip
        self._conn.execute("DELETE FROM item_owners WHERE item_id = ?", (item_id,))
        self._conn.executemany(
            "INSERT INTO item_owners (item_id, person) VALUES (?, ?)",
            [(item_id, person) for person in owner.persons],
        )

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
