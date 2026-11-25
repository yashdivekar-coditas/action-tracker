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
