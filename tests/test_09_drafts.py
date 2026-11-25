"""Spec 09: `followup` without --dry-run creates Gmail drafts through the configured MCP server (FR-15, FR-17, NFR-1).

Seam 1 is the CLI; seam 2 is the fake Gmail MCP server and its call log (`fake_gmail`).
--today is 2026-10-15.
"""

from __future__ import annotations

import re
import sys

from conftest import PRIYA, PRIYA_DRAFT, FakeGmail, Harness, seeded

KARAN = ("Karan Joshi", [])
_, _, PRIYA_SUBJECT_AND_BODY = PRIYA_DRAFT.partition("Subject: ")
PRIYA_SUBJECT, _, PRIYA_BODY = PRIYA_SUBJECT_AND_BODY.partition("\n\n")


def test_one_person_gets_exactly_one_draft_with_the_golden_email_fr15_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    result = seeded(harness, PRIYA).run("followup", "Priya Nair")

    assert result.code == 0, result.err
    assert fake_gmail.calls() == [
        {"tool": "create_draft", "args": {"to": "priya.nair@example.com", "subject": PRIYA_SUBJECT, "body": PRIYA_BODY}}
    ]
    assert "Created draft for Priya Nair (priya.nair@example.com): draft-1\n" in result.out


def test_all_creates_one_draft_per_person_with_open_items_in_name_order_fr15_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    result = seeded(harness, PRIYA, KARAN, ("Anita Desai", [])).run("followup", "--all")

    assert result.code == 0, result.err
    assert [call["args"]["to"] for call in fake_gmail.calls("create_draft")] == ["karan.joshi@example.com", "priya.nair@example.com"]
    assert "Skipped Anita Desai" not in result.out  # no Open items, so never selected; Anita has no entry to skip
    assert result.out.endswith("Drafts: 2 created, 0 skipped, 0 failed. Nothing was sent.\n")


def test_a_skip_is_reported_and_is_not_a_failure_fr15_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    result = seeded(harness, PRIYA).run("followup", "--all")  # Karan has an Open item but is not in the roster

    assert result.code == 0, result.err
    assert "Skipped Karan Joshi: not in the People Roster\n" in result.out
    assert result.out.endswith("Drafts: 1 created, 1 skipped, 0 failed. Nothing was sent.\n")
    assert len(fake_gmail.calls("create_draft")) == 1


def test_dry_run_never_starts_the_server_fr15_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    assert seeded(harness, PRIYA).run("followup", "--all", "--dry-run").code == 0

    assert not fake_gmail.log_path.exists()


def test_nobody_to_draft_for_never_starts_the_server_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    result = seeded(harness, ("Anita Desai", [])).run("followup", "Anita Desai")

    assert (result.code, result.out) == (0, "Skipped Anita Desai: no Open items\nDrafts: 0 created, 1 skipped, 0 failed. Nothing was sent.\n")
    assert not fake_gmail.log_path.exists()


def test_a_server_without_the_draft_tool_exits_1_and_makes_no_calls_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    fake_gmail.switch("OMIT")
    result = seeded(harness, PRIYA).run("followup", "Priya")

    assert result.code == 1
    assert "create_draft" in result.err
    assert fake_gmail.calls() == []


def test_a_server_command_that_does_not_exist_exits_1_with_a_clear_message_fr17(harness: Harness) -> None:
    harness.gmail_command = ["/nonexistent/gmail-server"]
    result = seeded(harness, PRIYA).run("followup", "Priya")

    assert result.code == 1
    assert "cannot create Gmail drafts: cannot start '/nonexistent/gmail-server'" in result.err


def test_a_server_that_exits_at_once_exits_1_fr17(harness: Harness) -> None:
    harness.gmail_command = [sys.executable, "-c", "raise SystemExit(3)"]
    result = seeded(harness, PRIYA).run("followup", "Priya")

    assert result.code == 1
    assert "cannot create Gmail drafts" in result.err


def test_one_failing_recipient_exits_1_and_the_others_are_still_created_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    fake_gmail.switch("FAIL_FOR", "karan.joshi@example.com")
    result = seeded(harness, PRIYA, KARAN).run("followup", "--all")

    assert result.code == 1
    assert [call["args"]["to"] for call in fake_gmail.calls("create_draft")] == ["karan.joshi@example.com", "priya.nair@example.com"]
    assert "draft for Karan Joshi failed: Error executing tool create_draft" in result.err
    assert "Created draft for Priya Nair (priya.nair@example.com): draft-1\n" in result.out
    assert result.out.endswith("Drafts: 1 created, 0 skipped, 1 failed. Nothing was sent.\n")


def test_a_list_recipient_server_gets_to_as_a_list_and_its_text_failures_count_fr17(harness: Harness, fake_gmail: FakeGmail) -> None:
    # The production server wants `to` as a list, answers in text only, and reports some failures as "Error: ..." text.
    fake_gmail.switch("TO_LIST")
    fake_gmail.switch("FAIL_FOR", "karan.joshi@example.com")
    result = seeded(harness, PRIYA, KARAN).run("followup", "--all")

    assert result.code == 1
    assert [call["args"]["to"] for call in fake_gmail.calls("create_draft")] == [["karan.joshi@example.com"], ["priya.nair@example.com"]]
    assert "draft for Karan Joshi failed: Error: cannot draft for karan.joshi@example.com" in result.err
    assert "Created draft for Priya Nair (priya.nair@example.com): Email draft created successfully with ID: draft-1\n" in result.out


def test_a_second_run_within_24_hours_warns_and_still_creates_a_draft_fr15(harness: Harness, fake_gmail: FakeGmail) -> None:
    seeded(harness, PRIYA)
    first = harness.run("followup", "Priya")
    second = harness.run("followup", "Priya")

    assert "warning" not in first.err
    assert second.code == 0, second.err
    assert re.search(r"^warning: a draft for Priya Nair was already created at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$", second.err, re.M)
    assert len(fake_gmail.calls("create_draft")) == 2


def test_the_warning_is_per_person_fr15(harness: Harness, fake_gmail: FakeGmail) -> None:
    seeded(harness, PRIYA, KARAN)
    assert harness.run("followup", "Priya").code == 0
    result = harness.run("followup", "--all")

    assert "draft for Priya Nair was already created" in result.err
    assert "Karan" not in result.err


def test_dry_run_records_nothing_so_a_later_run_does_not_warn_fr15(harness: Harness, fake_gmail: FakeGmail) -> None:
    seeded(harness, PRIYA)
    assert harness.run("followup", "Priya", "--dry-run").code == 0
    result = harness.run("followup", "Priya")

    assert result.err == ""


def test_a_failed_draft_is_not_recorded_fr15(harness: Harness, fake_gmail: FakeGmail) -> None:
    seeded(harness, PRIYA)
    fake_gmail.switch("FAIL_FOR", "priya.nair@example.com")
    assert harness.run("followup", "Priya").code == 1
    fake_gmail.switch("FAIL_FOR", "")
    result = harness.run("followup", "Priya")

    assert "warning" not in result.err


def test_a_server_that_dies_mid_batch_keeps_the_drafts_already_created_nfr2_fr15(harness: Harness, fake_gmail: FakeGmail) -> None:
    fake_gmail.switch("EXIT_AFTER", "1")
    result = seeded(harness, PRIYA, KARAN).run("followup", "--all")

    assert result.code == 1
    assert "Created draft for Karan Joshi (karan.joshi@example.com): draft-1\n" in result.out
    assert "draft for Priya Nair failed" in result.err
    assert result.out.endswith("Drafts: 1 created, 0 skipped, 1 failed. Nothing was sent.\n")
    assert "Traceback" not in result.err
    fake_gmail.switch("EXIT_AFTER", "")
    assert "draft for Karan Joshi was already created" in harness.run("followup", "Karan").err  # it was recorded


def test_a_history_write_failure_still_reports_the_created_drafts_nfr2_fr15(harness: Harness, fake_gmail: FakeGmail) -> None:
    seeded(harness, PRIYA)
    fake_gmail.switch("CHMOD_DB", str(harness.db))  # the server makes the database read-only once it is called
    result = harness.run("followup", "Priya")

    assert result.code == 1
    assert "Created draft for Priya Nair (priya.nair@example.com): draft-1\n" in result.out
    assert "not recorded" in result.err
    assert "Traceback" not in result.err
