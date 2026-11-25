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
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

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
)

# NFR-4: meeting content stays private on a shared machine.
_DB_FILE_MODE = 0o600


class StoreError(Exception):
    """The database could not be opened or written; the run was rolled back."""


class Store:
    """Write access to the database inside one open transaction."""

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
    for target, statements in enumerate(_MIGRATIONS[version:], start=version + 1):
        for statement in statements:
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {target}")  # PRAGMA takes no bound parameters


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.execute("ROLLBACK")
