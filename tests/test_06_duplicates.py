"""Spec 06: repeats collapse into one item with many Sources (FR-9, FR-10, FR-12).

State is built by ingesting several crafted notes and observed through
`list --json` and the `ingest --json` report.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import Harness

ATTENDEES = "Priya Nair, Priya Shah, Rahul Mehta"


def note(harness: Harness, name: str, date: str, *lines: str, attendees: str = ATTENDEES) -> None:
    """Write one Meeting Note holding `lines`, without ingesting it."""
    body = "".join(f"{line}\n" for line in lines)
    harness.write(name, f"# Meeting: {name}\nDate: {date}\nAttendees: {attendees}\n\n{body}")


def ingest(harness: Harness) -> dict[str, Any]:
    result = harness.ingest()
    assert result.code == 0, result.err
    return result.json


def files(item: dict[str, Any]) -> list[str]:
    return [source["file"] for source in item["sources"]]


# --- wording noise collapses (FR-9) --------------------------------------------------

BASE = "- [ ] Rahul to send the revised quote to Acme by Friday"


@pytest.mark.parametrize(
    "repeat",
    [
        "- [ ] RAHUL to SEND the Revised Quote to ACME",  # case
        "- [ ] Rahul to send the revised quote, to Acme!",  # punctuation
        "- [ ] Rahul to send revised quote to Acme",  # `the` dropped
        "- [ ] Rahul to send the revised quote to Acme by Monday",  # a different Due Phrase
        "- [ ] Rahul to send the revised quote to Acme",  # no Due Phrase
    ],
)
def test_wording_noise_is_the_same_item_fr9(harness: Harness, repeat: str) -> None:
    note(harness, "a.md", "2026-09-01", BASE)
    note(harness, "b.md", "2026-09-08", repeat)

    report = ingest(harness)

    assert (report["items_new"], report["items_merged"]) == (1, 1)
    [item] = harness.items()
    assert files(item) == ["a.md", "b.md"]


def test_articles_a_an_the_are_all_dropped_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] Rahul to write an update for the board")
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to write update for a board")

    ingest(harness)

    assert [len(i["sources"]) for i in harness.items()] == [2]


def test_reingest_does_not_count_repeats_again_fr11_fr12(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", BASE)
    note(harness, "b.md", "2026-09-08", BASE)
    ingest(harness)

    again = ingest(harness)

    assert (again["items_new"], again["items_merged"], again["items_done"]) == (0, 0, 0)
    assert len(harness.items()[0]["sources"]) == 2


# --- what must not collapse (FR-9) ---------------------------------------------------


def test_same_task_with_different_owners_stays_two_items_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] Rahul to send the revised quote to Acme")
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul & Priya N. to send the revised quote to Acme")
    note(harness, "c.md", "2026-09-15", "- [ ] Priya S. to send the revised quote to Acme")

    report = ingest(harness)

    assert (report["items_new"], report["items_merged"]) == (3, 0)


def test_a_genuinely_reworded_task_stays_a_separate_item_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] Rahul to send the revised quote to Acme")
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to email Acme the new quote")

    assert (ingest(harness)["items_new"], len(harness.items())) == (2, 2)


def test_a_different_owner_set_is_a_different_item_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] Rahul to plan the offsite")
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul & Priya N. to plan the offsite")

    assert (ingest(harness)["items_new"], len(harness.items())) == (2, 2)


# --- unclear owners compare on what was written (FR-9) -------------------------------


def test_ambiguous_items_compare_on_the_lowercased_written_owner_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] Priya to circulate the summary")
    note(harness, "b.md", "2026-09-08", "- [ ] PRIYA to circulate the summary")
    note(harness, "c.md", "2026-09-15", "- [ ] Priya N. to circulate the summary")

    report = ingest(harness)

    assert (report["items_new"], report["items_merged"]) == (2, 1)
    assert [len(i["sources"]) for i in harness.items()] == [2, 1]


def test_unknown_items_compare_on_the_lowercased_written_owner_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] Karan to send the invoices")
    note(harness, "b.md", "2026-09-08", "- [ ] KARAN to send the invoices")
    note(harness, "c.md", "2026-09-15", "- [ ] Meera to send the invoices")

    report = ingest(harness)

    assert (report["items_new"], report["items_merged"]) == (2, 1)


def test_unassigned_items_compare_on_the_task_alone_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] TBD to write the changelog")
    note(harness, "b.md", "2026-09-08", "- [ ] Write changelog")
    note(harness, "c.md", "2026-09-15", "- [ ] Someone to write the changelog")

    report = ingest(harness)

    assert (report["items_new"], report["items_merged"]) == (1, 2)
    assert harness.items()[0]["owner_kind"] == "unassigned"


# --- status across Sources (FR-10, FR-12) --------------------------------------------


def test_a_check_mark_in_any_source_marks_the_item_done_fr10_fr12(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", BASE)
    note(harness, "b.md", "2026-09-08", "- [x] Rahul to send revised quote to Acme")

    report = ingest(harness)

    assert report["items_done"] == 1
    assert [i["status"] for i in harness.items()] == ["done"]


def test_a_later_unchecked_mention_does_not_reopen_fr10(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [x] Rahul to send the revised quote to Acme")
    note(harness, "b.md", "2026-09-08", BASE)

    report = ingest(harness)

    assert (report["items_done"], report["items_merged"]) == (1, 1)
    assert [i["status"] for i in harness.items()] == ["done"]


def test_done_is_counted_once_across_runs_fr12(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", BASE)
    assert ingest(harness)["items_done"] == 0
    note(harness, "b.md", "2026-09-08", "- [x] Rahul to send the revised quote to Acme")
    assert ingest(harness)["items_done"] == 1
    note(harness, "c.md", "2026-09-15", "- [x] Rahul to send the revised quote to Acme")

    later = ingest(harness)

    assert (later["items_done"], later["items_merged"]) == (0, 1)


# --- listing (FR-9) ------------------------------------------------------------------


def test_list_shows_every_source_in_meeting_date_order_fr9(harness: Harness) -> None:
    # File names sort opposite to Meeting Dates, so order must come from the date.
    note(harness, "c.md", "2026-09-01", BASE)
    note(harness, "b.md", "2026-09-08", BASE)
    note(harness, "a.md", "2026-09-15", BASE)
    ingest(harness)

    [item] = harness.items()

    assert files(item) == ["c.md", "b.md", "a.md"]


# --- the latest Source sets the Due Date and task text (FR-9, FR-8) -------------------


def test_a_later_due_phrase_replaces_the_earlier_due_date_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", BASE)  # by Friday -> 2026-09-04
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to send the revised quote to Acme by Monday")

    ingest(harness)

    [item] = harness.items()
    assert (item["due_phrase"], item["due_date"]) == ("Monday", "2026-09-14")


def test_a_later_mention_without_a_due_phrase_keeps_the_due_date_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", BASE)
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to send the revised quote to Acme")

    ingest(harness)

    [item] = harness.items()
    assert (item["due_phrase"], item["due_date"]) == ("Friday", "2026-09-04")


def test_the_task_text_follows_the_latest_source_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", "- [ ] Rahul to send the revised quote to Acme")
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to SEND revised quote to Acme!")

    ingest(harness)

    assert [i["task"] for i in harness.items()] == ["SEND revised quote to Acme!"]


def test_on_a_meeting_date_tie_the_later_file_name_wins_fr9(harness: Harness) -> None:
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to send the revised quote to Acme by Monday")
    note(harness, "a.md", "2026-09-08", "- [ ] Rahul to send the revised quote to Acme by Friday")

    ingest(harness)

    [item] = harness.items()
    assert (item["due_phrase"], item["due_date"]) == ("Monday", "2026-09-14")


def test_a_later_dated_note_wins_whatever_its_file_name_or_ingest_order_fr9(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-08", "- [ ] Rahul to send the revised quote to Acme by Monday")  # later Meeting Date
    note(harness, "b.md", "2026-09-01", "- [ ] Rahul to send the revised quote to Acme by Friday")
    ingest(harness)
    [first] = harness.items()

    # A fresh database, which ingests in file-name order, gives the same answer.
    again = harness.ingest(db=harness.root / "fresh.db")
    assert again.code == 0, again.err

    assert (first["due_phrase"], first["due_date"]) == ("Monday", "2026-09-14")
    assert harness.run("list", "--json", db=harness.root / "fresh.db").json == [first]


def test_an_older_source_ingested_later_does_not_override_the_due_date_fr9(harness: Harness) -> None:
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to send the revised quote to Acme by Monday")
    ingest(harness)
    note(harness, "a.md", "2026-09-01", BASE)  # older Meeting Date, ingested after

    ingest(harness)

    [item] = harness.items()
    assert (item["due_phrase"], item["due_date"]) == ("Monday", "2026-09-14")


def test_reingest_rederives_the_due_date_of_a_sole_source_fr8(harness: Harness) -> None:
    note(harness, "a.md", "2026-09-01", BASE)
    ingest(harness)
    note(harness, "a.md", "2026-09-08", BASE)  # same line, new Meeting Date

    ingest(harness)

    [item] = harness.items()
    assert (item["due_phrase"], item["due_date"]) == ("Friday", "2026-09-11")


def test_an_older_source_ingested_later_restores_a_due_date_fr9(harness: Harness) -> None:
    note(harness, "b.md", "2026-09-08", "- [ ] Rahul to send the revised quote to Acme")
    ingest(harness)
    note(harness, "a.md", "2026-09-01", BASE)  # older Meeting Date, ingested after

    ingest(harness)

    [item] = harness.items()
    assert (item["due_phrase"], item["due_date"]) == ("Friday", "2026-09-04")
