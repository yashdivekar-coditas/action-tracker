"""Spec 09: `followup` composes one plain-text email per Person from their Open items (FR-15, FR-16).

This file covers `--dry-run`: emails are printed and nothing is created. State is built by ingesting
crafted notes and observed through the exit code and output only. --today is 2026-10-15.
"""

from __future__ import annotations

from conftest import SAMPLE_NOTES, Harness

PRIYA = ("Priya Nair", [])

CHECK_IN = (
    "# Meeting: Acme renewal check-in\nDate: 2026-09-28\n"
    "Attendees: Priya Nair, Karan Joshi, Anita Desai, Anita Rao\n\n"
    "- [ ] Priya to prepare the renewal one-pager by 2026-10-24\n"  # dated, in two meetings
    "- [ ] Priya to collect beta feedback by 2026-10-10\n"  # overdue, 5 days
    "- [ ] Priya to review the welcome email\n"  # undated
    "- [ ] Priya to write the handbook by end of the quarter\n"  # Due Phrase that does not resolve
    "- [ ] Karan and Priya to plan the demo by 2026-10-30\n"  # shared
    "- [x] Priya to ship the old portal by 2026-10-01\n"  # Done
    "- [ ] Anita to book the venue by 2026-10-01\n"  # Ambiguous Owner
    "- [ ] Zed to cancel the trial by 2026-10-01\n"  # Unknown Owner
    "- [ ] TBD to order the badges by 2026-10-01\n"  # Unassigned
)
WRAP_UP = (
    "# Meeting: Acme renewal wrap-up\nDate: 2026-10-14\nAttendees: Priya Nair\n\n"
    "- [ ] Priya to prepare the renewal one-pager by 2026-10-24\n"
)

PRIYA_EMAIL = """\
To: priya.nair@example.com
Subject: Action items from recent meetings — 5 open, 1 overdue

Hi Priya,

Here are your open action items from recent meetings:

OVERDUE
- collect beta feedback — due 2026-10-10 (5 days overdue)
  from: Acme renewal check-in, 2026-09-28

OPEN
- prepare the renewal one-pager — due 2026-10-24
  from: Acme renewal check-in, 2026-09-28; Acme renewal wrap-up, 2026-10-14
- plan the demo — due 2026-10-30
  from: Acme renewal check-in, 2026-09-28
- review the welcome email — no due date
  from: Acme renewal check-in, 2026-09-28
- write the handbook — due end of the quarter
  from: Acme renewal check-in, 2026-09-28

Thanks,
Yash Divekar
"""


def seeded(harness: Harness, *roster: tuple[str, list[str]], sender: str | None = "Yash Divekar") -> Harness:
    harness.write("a.md", CHECK_IN)
    harness.write("b.md", WRAP_UP)
    assert harness.ingest().code == 0
    harness.write_roster(*roster, sender=sender)
    return harness


def test_dry_run_prints_the_email_for_one_person_fr15_fr16(harness: Harness) -> None:
    result = seeded(harness, PRIYA).run("followup", "Priya Nair", "--dry-run")

    assert result.code == 0, result.err
    assert result.out == PRIYA_EMAIL + "\nDry run: 1 email composed, 0 skipped. Nothing was created.\n"


def test_ambiguous_unknown_unassigned_and_done_items_never_appear_fr15(harness: Harness) -> None:
    out = seeded(harness, PRIYA).run("followup", "Priya Nair", "--dry-run").out

    for task in ("book the venue", "cancel the trial", "order the badges", "ship the old portal"):
        assert task not in out


def test_first_name_alias_and_case_resolve_like_list_owner_fr15_fr13(harness: Harness) -> None:
    seeded(harness, ("Priya Nair", ["PN"]))
    for written in ("Priya", "priya nair", "PN"):
        result = harness.run("followup", written, "--dry-run")
        assert result.code == 0, result.err
        assert result.out.startswith(PRIYA_EMAIL)


def test_shared_item_appears_in_each_owners_email_fr15(harness: Harness) -> None:
    seeded(harness, PRIYA, ("Karan Joshi", []))
    result = harness.run("followup", "--all", "--dry-run")

    assert result.code == 0, result.err
    karan = result.out.split("---\n")[0]  # emails are in name order: Karan Joshi, then Priya Nair
    assert karan.startswith("To: karan.joshi@example.com\nSubject: Action items from recent meetings — 1 open, 0 overdue\n")
    assert "- plan the demo — due 2026-10-30" in karan
    assert "OVERDUE" not in karan  # an empty section is left out
    assert "- plan the demo — due 2026-10-30" in result.out.split("---\n")[1]


def test_team_item_appears_in_every_attendees_email_fr15(harness: Harness) -> None:
    harness.write("t.md", "# Meeting: Standup\nDate: 2026-10-01\nAttendees: Priya Nair, Karan Joshi\n\n- [ ] Team to tidy the board\n")
    assert harness.ingest().code == 0
    harness.write_roster(PRIYA, ("Karan Joshi", []), sender="Yash")
    result = harness.run("followup", "--all", "--dry-run")

    assert result.out.count("- tidy the board — no due date") == 2


def test_a_day_late_is_singular_fr16(harness: Harness) -> None:
    harness.write("t.md", "# Meeting: Standup\nDate: 2026-10-01\nAttendees: Priya Nair\n\n- [ ] Priya to file it by 2026-10-14\n")
    assert harness.ingest().code == 0
    harness.write_roster(PRIYA, sender="Yash")

    assert "(1 day overdue)" in harness.run("followup", "Priya", "--dry-run").out


def test_skips_a_person_without_open_items_or_roster_entry_and_reports_why_fr15(harness: Harness) -> None:
    seeded(harness, PRIYA, ("Anita Desai", []))
    result = harness.run("followup", "Anita Desai", "--dry-run")
    assert (result.code, result.out) == (
        0,
        "Skipped Anita Desai: no Open items\nDry run: 0 emails composed, 1 skipped. Nothing was created.\n",
    )

    result = harness.run("followup", "--all", "--dry-run")  # Karan has an Open item but is not in the roster
    assert result.code == 0
    assert "Skipped Karan Joshi: not in the People Roster\n" in result.out
    assert "Dry run: 1 email composed, 1 skipped." in result.out


def test_ambiguous_unknown_and_unassigned_owner_arguments_exit_2_fr15(harness: Harness) -> None:
    harness.write("t.md", "# Meeting: S\nDate: 2026-10-01\nAttendees: Priya Nair, Priya Shah\n\n- [ ] Priya Nair to a\n")
    assert harness.ingest().code == 0
    harness.write_roster(PRIYA, ("Priya Shah", []), sender="Yash")

    ambiguous = harness.run("followup", "Priya", "--dry-run")
    assert ambiguous.code == 2
    assert "ambiguous: Priya Nair, Priya Shah" in ambiguous.err
    for written in ("Nobody", "unassigned"):
        assert harness.run("followup", written, "--dry-run").code == 2


def test_missing_config_or_sender_exits_2_fr15_fr18(harness: Harness) -> None:
    harness.write("t.md", CHECK_IN)
    assert harness.ingest().code == 0

    assert harness.run("followup", "Priya", "--dry-run").code == 2  # no config
    harness.write_roster(PRIYA)  # no sender
    result = harness.run("followup", "Priya", "--dry-run")
    assert result.code == 2
    assert "sender" in result.err


def test_owner_or_all_is_required_but_not_both_fr15(harness: Harness) -> None:
    seeded(harness, PRIYA)
    assert harness.run("followup", "--dry-run").code == 2
    assert harness.run("followup", "Priya", "--all", "--dry-run").code == 2


def test_dry_run_leaves_no_database_behind_fr15(harness: Harness) -> None:
    harness.write_roster(PRIYA, sender="Yash")
    result = harness.run("followup", "--all", "--dry-run")

    assert (result.code, harness.db.exists()) == (0, False)
    assert "0 emails composed" in result.out


def test_email_text_cannot_drive_the_terminal_nfr4(harness: Harness) -> None:
    harness.write("t.md", "# Meeting: S\nDate: 2026-10-01\nAttendees: Priya Nair\n\n- [ ] Priya to mail \x1b[31mred\x07 now\n")
    assert harness.ingest().code == 0
    harness.write_roster(PRIYA, sender="Yash")

    assert "\x1b" not in harness.run("followup", "Priya", "--dry-run").out


def test_sample_notes_fr15_fr16(harness: Harness) -> None:
    assert harness.ingest(SAMPLE_NOTES).code == 0
    names = [item_owner for item in harness.items() for item_owner in item["persons"]]
    harness.write_roster(*((name, []) for name in sorted(set(names))), sender="Yash")
    result = harness.run("followup", "--all", "--dry-run")

    assert result.code == 0, result.err
    assert "circulate the go/no-go summary" not in result.out  # Ambiguous Owner
    meera = next(email for email in result.out.split("---\n") if email.startswith("To: meera.iyer@"))
    overdue = meera.split("OVERDUE\n")[1].split("\n\n")[0]
    assert "finalise the Q4 sales targets" in overdue
    assert "(12 days overdue)" in overdue
