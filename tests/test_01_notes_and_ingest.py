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
