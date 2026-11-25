"""Spec 01: folder scan, note headers, Malformed Notes and the ingest run.

Each test names the FR/NFR rule it proves.
"""

from __future__ import annotations

from conftest import Harness

TEMPLATE_NOTE = """\
# Meeting: Quote portal kickoff
Date: 2026-09-01
Attendees: Priya Nair, Rahul Mehta

## Discussion
Kickoff.
"""


# --- CLI contract (NFR-6, FR-12) -------------------------------------------------


def test_help_lists_ingest_command_nfr6(harness: Harness) -> None:
    result = harness.run("--help", global_options=False)

    assert result.code == 0
    assert "ingest" in result.out


def test_ingest_help_lists_global_options_but_hides_today_nfr6(harness: Harness) -> None:
    result = harness.run("ingest", "--help", global_options=False)

    assert result.code == 0
    for option in ("--db", "--config", "--json"):
        assert option in result.out
    assert "--today" not in result.out


def test_missing_folder_is_usage_error_fr12(harness: Harness) -> None:
    result = harness.ingest(harness.notes / "nope")

    assert result.code == 2
    assert result.out == ""
    assert "nope" in result.err


def test_bad_arguments_are_usage_error_fr12(harness: Harness) -> None:
    assert harness.run("ingest", global_options=False).code == 2
    assert harness.run("frobnicate", global_options=False).code == 2


def test_invalid_today_is_usage_error_fr12(harness: Harness) -> None:
    result = harness.run("ingest", str(harness.notes), "--today", "15/10/2026", global_options=False)

    assert result.code == 2
    assert "--today" in result.err


# --- folder scan and report (FR-1, FR-12) ----------------------------------------

REPORT_KEYS = {
    "notes_read",
    "malformed",
    "ignored",
    "items_new",
    "items_merged",
    "items_done",
    "malformed_notes",
    "ambiguous_owners",
    "unknown_owners",
    "unassigned_items",
    "unresolved_due_phrases",
}


def test_ingest_reads_a_template_note_and_reports_stable_keys_fr12_nfr6(harness: Harness) -> None:
    harness.write("2026-09-01-kickoff.md", TEMPLATE_NOTE)

    result = harness.ingest()

    assert result.code == 0
    report = result.json
    assert REPORT_KEYS <= report.keys()
    assert (report["notes_read"], report["malformed"], report["ignored"]) == (1, 0, 0)
    assert report["malformed_notes"] == []


def test_only_md_files_directly_inside_folder_are_read_fr1(harness: Harness) -> None:
    harness.write("a.md", TEMPLATE_NOTE)
    harness.write("B.MD", TEMPLATE_NOTE)  # extension is case-insensitive
    harness.write("agenda.txt", "not a note")
    harness.write("draft.md.bak", "not a note")
    (harness.notes / "archive").mkdir()
    (harness.notes / "archive" / "old.md").write_text(TEMPLATE_NOTE, encoding="utf-8")

    report = harness.ingest().json

    assert report["notes_read"] == 2
    assert report["ignored"] == 2


def test_human_report_goes_to_stdout_fr12_nfr6(harness: Harness) -> None:
    harness.write("a.md", TEMPLATE_NOTE)
    harness.write("agenda.txt", "x")

    result = harness.run("ingest", str(harness.notes))

    assert result.code == 0
    assert "1 Meeting Note" in result.out
    assert "1 non-markdown file" in result.out
    assert result.err == ""


def test_database_defaults_to_actiontrack_db_in_working_directory(harness: Harness) -> None:
    harness.write("a.md", TEMPLATE_NOTE)

    result = harness.run("ingest", str(harness.notes), "--today", "2026-10-15", global_options=False)

    assert result.code == 0
    assert (harness.notes.parent / ".actiontrack.db").is_file()


def test_database_path_from_environment_and_flag_beats_it(harness: Harness, monkeypatch) -> None:
    harness.write("a.md", TEMPLATE_NOTE)
    env_db = harness.notes.parent / "from-env.db"
    flag_db = harness.notes.parent / "from-flag.db"
    monkeypatch.setenv("ACTIONTRACK_DB", str(env_db))

    assert harness.run("ingest", str(harness.notes), global_options=False).code == 0
    assert env_db.is_file()

    assert harness.run("ingest", str(harness.notes), "--db", str(flag_db), global_options=False).code == 0
    assert flag_db.is_file()


def test_database_file_is_readable_by_owner_only_nfr4(harness: Harness) -> None:
    harness.write("a.md", TEMPLATE_NOTE)

    assert harness.ingest().code == 0

    assert harness.db.stat().st_mode & 0o777 == 0o600
