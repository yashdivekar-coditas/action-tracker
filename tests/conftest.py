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
