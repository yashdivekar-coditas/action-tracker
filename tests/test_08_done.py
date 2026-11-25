"""Spec 08: `actiontrack done <id>` closes an item for good (FR-14, FR-10, FR-11).

State is built by ingesting crafted notes and observed through `done` output,
its exit code and `list --json`.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import Harness

ATTENDEES = "Priya Nair, Priya Shah, Rahul Mehta"
OPEN = "- [ ] Rahul to send the revised quote to Acme"


def seed(harness: Harness, *lines: str, attendees: str = ATTENDEES) -> list[dict[str, Any]]:
    return harness.ingest_note("".join(f"{line}\n" for line in lines), attendees=attendees)


def test_done_closes_an_open_item_and_prints_it_fr14(harness: Harness) -> None:
    seed(harness, OPEN)

    result = harness.run("done", "1")

    assert result.code == 0, result.err
    assert "#1" in result.out and "Rahul Mehta" in result.out and "send the revised quote to Acme" in result.out
    assert "already done" not in result.out
    assert harness.items()[0]["status"] == "done"


def test_reingest_keeps_a_cli_done_item_done_fr14_fr10(harness: Harness) -> None:
    seed(harness, OPEN)
    harness.run("done", "1")

    result = harness.ingest()

    assert result.code == 0, result.err
    assert [i["status"] for i in harness.items()] == ["done"]


def test_a_shared_item_is_done_for_every_owner_fr14(harness: Harness) -> None:
    seed(harness, "- [ ] Priya Nair and Rahul Mehta to book the venue")

    result = harness.run("done", "1")

    assert "Priya Nair, Rahul Mehta" in result.out
    [item] = harness.items()
    assert (item["persons"], item["status"]) == (["Priya Nair", "Rahul Mehta"], "done")


def test_done_on_a_done_item_says_so_and_exits_zero_fr14(harness: Harness) -> None:
    seed(harness, OPEN)
    harness.run("done", "1")

    result = harness.run("done", "1")

    assert result.code == 0
    assert "already done" in result.out


@pytest.mark.parametrize(
    "line",
    [
        "- [ ] Priya to book the venue",  # Ambiguous
        "- [ ] Karan to book the venue",  # Unknown
        "- [ ] book the venue",  # Unassigned
    ],
)
def test_ambiguous_unknown_and_unassigned_items_can_be_closed_fr14(harness: Harness, line: str) -> None:
    [item] = seed(harness, line)
    assert item["owner_kind"] in {"ambiguous", "unknown", "unassigned"}

    result = harness.run("done", "1")

    assert result.code == 0, result.err
    assert harness.items()[0]["status"] == "done"


def test_a_merged_id_closes_the_survivor_and_says_so_fr14_fr11(harness: Harness) -> None:
    for name, date, attendees in (("a.md", "2026-09-01", "Priya Nair"), ("b.md", "2026-09-08", "Karan Rao")):
        harness.write(
            name, f"# Meeting: {name}\nDate: {date}\nAttendees: {attendees}\n\n- [ ] Karan to send the invoices\n"
        )
    assert harness.ingest().code == 0
    assert [i["id"] for i in harness.items()] == [1, 2]
    harness.write_roster(("Karan Rao", ["Karan"]))
    assert harness.ingest().code == 0
    assert [i["id"] for i in harness.items()] == [1]

    result = harness.run("done", "2")

    assert result.code == 0, result.err
    assert "#2 was merged into #1" in result.out
    assert harness.items()[0]["status"] == "done"


def test_an_unknown_id_exits_one_fr14(harness: Harness) -> None:
    seed(harness, OPEN)

    result = harness.run("done", "99")

    assert result.code == 1
    assert "99" in result.err
    assert harness.items()[0]["status"] == "open"


def test_a_missing_database_is_an_unknown_id_and_is_not_created_fr14(harness: Harness) -> None:
    result = harness.run("done", "1")

    assert result.code == 1
    assert not harness.db.exists()


def test_a_non_numeric_id_exits_two_fr14(harness: Harness) -> None:
    assert harness.run("done", "abc").code == 2


def test_done_json_matches_the_list_element_fr14(harness: Harness) -> None:
    seed(harness, OPEN, "- [ ] Priya Nair to book the venue")

    result = harness.run("done", "2", "--json")

    assert result.code == 0, result.err
    assert result.json == harness.items()[1]
    assert result.json["status"] == "done"
