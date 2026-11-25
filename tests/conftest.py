"""Shared test harness (NFR-5).

Every test drives actiontrack through its single seam, `cli.main(argv)`, with a
temporary notes folder, a temporary `--db` and a pinned `--today`. Tests assert
only on the exit code, stdout/stderr and the `--json` report.
"""

from __future__ import annotations

import contextlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from actiontrack import cli

TODAY = "2026-10-15"
SAMPLE_NOTES = Path(__file__).resolve().parents[1] / "notes"


@dataclass(frozen=True)
class CliResult:
    """What a user can observe from one CLI invocation."""

    code: int
    out: str
    err: str

    @property
    def json(self) -> Any:
        return json.loads(self.out)


class Harness:
    """A temp notes folder and temp database, plus helpers to run the CLI against them."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.notes = root / "notes"
        self.notes.mkdir()
        self.db = root / "actiontrack.db"

    def write(self, name: str, content: str | bytes) -> Path:
        """Write one file into the temp notes folder; `bytes` are written verbatim."""
        path = self.notes / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def run(self, *argv: str, global_options: bool = True, db: Path | None = None) -> CliResult:
        """Run `actiontrack <argv>` in-process, appending `--db` and a pinned `--today`."""
        args = list(argv)
        if global_options:
            args += ["--db", str(db or self.db), "--today", TODAY]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
        return CliResult(code, out.getvalue(), err.getvalue())

    def ingest(self, folder: Path | None = None, *, db: Path | None = None) -> CliResult:
        """Run `actiontrack ingest <folder> --json` (the temp notes folder by default)."""
        return self.run("ingest", str(folder or self.notes), "--json", db=db)

    def write_roster(self, *people: tuple[str, list[str]]) -> Path:
        """Write ./actiontrack.toml (found automatically) with a People Roster of (name, aliases)."""
        entries = "".join(
            f'\n[[people]]\nname = "{name}"\nemail = "{name.split()[0].lower()}@example.com"\naliases = {aliases!r}\n'.replace("'", '"')
            for name, aliases in people
        )
        path = self.root / "actiontrack.toml"
        path.write_text(f'[gmail]\ncommand = ["fake-gmail"]\ndraft_tool = "create_draft"\n{entries}', encoding="utf-8")
        return path

    def items(self) -> list[dict[str, Any]]:
        """Run `actiontrack list --json` and return the stored Action Items."""
        result = self.run("list", "--json")
        assert result.code == 0, result.err
        return result.json

    def ingest_note(
        self, body: str, *, name: str = "note.md", date: str = "2026-09-30", attendees: str | None = "Priya Nair"
    ) -> list[dict[str, Any]]:
        """Write one Meeting Note with a valid header around `body`, ingest, and return all items.

        `attendees=None` leaves the Attendees line out.
        """
        attendee_line = f"Attendees: {attendees}\n" if attendees is not None else ""
        self.write(name, f"# Meeting: Test meeting\nDate: {date}\n{attendee_line}\n{body}")
        result = self.ingest()
        assert result.code == 0, result.err
        assert result.json["malformed"] == 0, result.json["malformed_notes"]
        return self.items()


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    # Keep tests hermetic: the developer's own environment must not leak in.
    monkeypatch.delenv("ACTIONTRACK_DB", raising=False)
    monkeypatch.delenv("ACTIONTRACK_TODAY", raising=False)
    monkeypatch.chdir(tmp_path)
    # A developer's ~/.config/actiontrack/actiontrack.toml must not leak in either.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return Harness(tmp_path)


def malformed_reasons(report: dict[str, Any]) -> dict[str, str]:
    """Map file name -> reason for every Malformed Note in an ingest report."""
    return {entry["file"]: entry["reason"] for entry in report["malformed_notes"]}
