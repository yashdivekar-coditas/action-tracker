"""Spec 09: `followup` without --dry-run creates Gmail drafts through the configured MCP server (FR-15, FR-17, NFR-1).

Seam 1 is the CLI; seam 2 is the fake Gmail MCP server and its call log (`fake_gmail`).
--today is 2026-10-15.
"""

from __future__ import annotations

import sys

from conftest import FakeGmail, Harness
from test_09_followup import PRIYA, PRIYA_EMAIL, seeded

KARAN = ("Karan Joshi", [])
_, _, PRIYA_SUBJECT_AND_BODY = PRIYA_EMAIL.partition("Subject: ")
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
