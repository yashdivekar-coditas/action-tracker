"""Spec 05: resolving written owner names to Persons (FR-7, FR-12, FR-13).

State is built by ingesting crafted notes (and an optional roster config) and
observed through `list --json` and the `ingest --json` report.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import Harness

PRIYAS_AND_RAHULS = "Priya Nair, Priya Shah, Rahul Mehta, Anita Desai"


def owner(item: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """An item's (owner kind, Persons, candidates)."""
    return item["owner_kind"], item["persons"], item["candidates"]


def resolve(
    harness: Harness, line: str, attendees: str | None = PRIYAS_AND_RAHULS, *, name: str = "note.md"
) -> dict[str, Any]:
    """Ingest a note holding one checkbox item; return that item (the newest stored)."""
    return harness.ingest_note(f"- [ ] {line}\n", attendees=attendees, name=name)[-1]


# --- matching against the meeting's Attendees (FR-7 steps 1, 4, 6) -----------------


@pytest.mark.parametrize(
    ("written", "person"),
    [
        ("Rahul", "Rahul Mehta"),  # unique first name
        ("RAHUL", "Rahul Mehta"),  # case-insensitive
        ("Priya N.", "Priya Nair"),  # first name + surname initial
        ("Priya S.", "Priya Shah"),
        ("Priya Shah", "Priya Shah"),  # full name
        ("PRIYA NAIR", "Priya Nair"),
    ],
)
def test_attendee_match_fr7_step4(harness: Harness, written: str, person: str) -> None:
    item = resolve(harness, f"{written} to do the thing")

    assert owner(item) == ("person", [person], [])
    assert item["written_owner"] == written


def test_mention_handle_matches_an_attendee_fr7_step4(harness: Harness) -> None:
    assert owner(resolve(harness, "@anita: audit colour contrast")) == ("person", ["Anita Desai"], [])


def test_first_name_shared_by_two_attendees_is_ambiguous_fr7_step6(harness: Harness) -> None:
    item = resolve(harness, "Priya to circulate the summary")

    assert owner(item) == ("ambiguous", [], ["Priya Nair", "Priya Shah"])
    assert item["written_owner"] == "Priya"


def test_name_matching_nobody_is_unknown_and_keeps_the_written_name_fr7_step6(harness: Harness) -> None:
    item = resolve(harness, "Karan to send the invoices")

    assert owner(item) == ("unknown", [], [])
    assert item["written_owner"] == "Karan"


@pytest.mark.parametrize("joined", ["Anita & Rahul", "Anita and Rahul", "Anita, Rahul"])
def test_joined_names_make_one_shared_item_fr7_step1(harness: Harness, joined: str) -> None:
    items = harness.ingest_note(f"- [ ] {joined} to agree on the component API\n", attendees=PRIYAS_AND_RAHULS)

    assert [owner(i) for i in items] == [("person", ["Anita Desai", "Rahul Mehta"], [])]


def test_shared_item_takes_the_least_certain_kind_fr7_step1(harness: Harness) -> None:
    ambiguous = resolve(harness, "Anita & Priya & Karan to pair")
    unknown = resolve(harness, "Anita & Karan to pair", attendees="Anita Desai", name="other.md")

    assert owner(ambiguous) == ("ambiguous", [], ["Priya Nair", "Priya Shah"])
    assert ambiguous["written_owner"] == "Anita & Priya & Karan"
    assert owner(unknown) == ("unknown", [], [])


def test_table_and_action_line_owners_use_the_same_rules_fr7(harness: Harness) -> None:
    items = harness.ingest_note(
        "| Owner | Action | Due |\n|---|---|---|\n| Anita | Refresh the brand kit | 9 Oct |\n"
        "ACTION: Priya N. to circulate the summary\n",
        attendees=PRIYAS_AND_RAHULS,
    )

    assert [owner(i) for i in items] == [
        ("person", ["Anita Desai"], []),
        ("person", ["Priya Nair"], []),
    ]


# --- placeholders (FR-7 steps 2 and 3) ---------------------------------------------


@pytest.mark.parametrize("word", ["Team", "Everyone", "All"])
def test_team_words_make_a_team_item_owned_by_every_attendee_fr7_step2(harness: Harness, word: str) -> None:
    item = resolve(harness, f"{word} to decide on the launch date", attendees="Priya Nair, Rahul Mehta, Sam Okafor")

    assert owner(item) == ("team", ["Priya Nair", "Rahul Mehta", "Sam Okafor"], [])
    assert item["written_owner"] == word


def test_team_item_without_attendees_is_unassigned_fr7_step2(harness: Harness) -> None:
    assert owner(resolve(harness, "Team to decide on the launch date", attendees=None)) == ("unassigned", [], [])


@pytest.mark.parametrize("word", ["TBD", "Someone", "Somebody", "Anyone", "?"])
def test_placeholder_words_are_unassigned_fr7_step3(harness: Harness, word: str) -> None:
    item = resolve(harness, f"{word} to write the changelog")

    assert owner(item) == ("unassigned", [], [])
    assert item["written_owner"] == word


def test_no_owner_part_is_unassigned_fr7_step3(harness: Harness) -> None:
    item = resolve(harness, "Book the venue")

    assert owner(item) == ("unassigned", [], [])
    assert item["written_owner"] is None


# --- People Roster fallback (FR-7 step 5) ------------------------------------------


def test_name_missing_from_attendees_falls_back_to_the_roster_fr7_step5(harness: Harness) -> None:
    harness.write_roster(("Karan Joshi", []), ("Meera Iyer", []))

    assert owner(resolve(harness, "Karan to send the invoices")) == ("person", ["Karan Joshi"], [])


def test_without_a_config_there_is_no_roster_fallback_fr7_step5(harness: Harness) -> None:
    assert owner(resolve(harness, "Karan to send the invoices"))[0] == "unknown"


def test_roster_alias_counts_as_a_match_fr7_step5(harness: Harness) -> None:
    harness.write_roster(("Karan Joshi", ["KJ"]), ("Lena Fischer", ["Lenny"]))

    items = harness.ingest_note("- [ ] KJ to send the invoices\n- [ ] Lenny to draft the survey\n")

    assert [owner(i) for i in items] == [("person", ["Karan Joshi"], []), ("person", ["Lena Fischer"], [])]


def test_attendees_win_over_the_roster_fr7_step5(harness: Harness) -> None:
    harness.write_roster(("Rahul Verma", []))

    assert owner(resolve(harness, "Rahul to fix the bug"))[1] == ["Rahul Mehta"]  # attending, so no fallback


def test_several_roster_matches_are_ambiguous_fr7_step6(harness: Harness) -> None:
    harness.write_roster(("Sam Okafor", []), ("Sam Lee", []))

    assert owner(resolve(harness, "Sam to book the room")) == ("ambiguous", [], ["Sam Lee", "Sam Okafor"])


def test_reingest_after_a_roster_fix_updates_the_owner_and_keeps_the_id_fr7_fr11(harness: Harness) -> None:
    before = resolve(harness, "Karan to send the invoices")
    harness.write_roster(("Karan Joshi", []))

    result = harness.ingest()

    (after,) = harness.items()
    assert result.json["items_new"] == 0
    assert (before["id"], before["owner_kind"]) == (after["id"], "unknown")
    assert owner(after) == ("person", ["Karan Joshi"], [])


# --- report and list output (FR-12, FR-13) -----------------------------------------

REPORT_NOTE = (
    "- [ ] Priya to circulate the summary\n"
    "- [ ] Karan to send the invoices\n"
    "- [ ] TBD to write the changelog\n"
    "- [ ] Anita to refresh the brand kit\n"
)


def test_ingest_report_lists_unclear_owners_fr12(harness: Harness) -> None:
    harness.ingest_note(REPORT_NOTE, attendees=PRIYAS_AND_RAHULS, name="sync.md")

    report = harness.ingest().json

    assert report["ambiguous_owners"] == [
        {"file": "sync.md", "line": 5, "item_id": 1, "written_owner": "Priya", "candidates": ["Priya Nair", "Priya Shah"]}
    ]
    assert report["unknown_owners"] == [{"file": "sync.md", "line": 6, "item_id": 2, "written_owner": "Karan"}]
    assert report["unassigned_items"] == [{"file": "sync.md", "line": 7, "item_id": 3, "task": "write the changelog"}]


def test_unclear_owners_are_warned_on_stderr_fr12_nfr6(harness: Harness) -> None:
    harness.ingest_note(REPORT_NOTE, attendees=PRIYAS_AND_RAHULS, name="sync.md")

    err = harness.run("ingest", str(harness.notes)).err

    assert "Ambiguous Owner: sync.md:5: Priya (Priya Nair, Priya Shah)" in err
    assert "Unknown Owner: sync.md:6: Karan" in err
    assert "Unassigned: sync.md:7: write the changelog" in err


def test_list_owner_column_shows_resolution_fr13(harness: Harness) -> None:
    harness.ingest_note(
        REPORT_NOTE + "- [ ] Anita & Rahul to agree on the API\n", attendees=PRIYAS_AND_RAHULS
    )

    out = harness.run("list").out

    assert "Priya (ambiguous: Priya Nair, Priya Shah)" in out
    assert "Karan (unknown)" in out
    assert "unassigned" in out
    assert "Anita Desai, Rahul Mehta" in out


# --- review fixes (FR-7) -----------------------------------------------------------


def test_a_person_listed_twice_is_not_ambiguous_fr7_step6(harness: Harness) -> None:
    item = resolve(harness, "Priya to send the quote", attendees="Priya Nair, Rahul Mehta, Priya Nair")

    assert owner(item) == ("person", ["Priya Nair"], [])


def test_roster_name_that_is_also_an_alias_is_one_match_fr7_step5(harness: Harness) -> None:
    harness.write_roster(("Karan Joshi", ["Karan"]))

    assert owner(resolve(harness, "Karan to send the invoices")) == ("person", ["Karan Joshi"], [])


def test_placeholder_next_to_team_keeps_a_team_item_fr7_step2(harness: Harness) -> None:
    item = resolve(harness, "Team & TBD to decide on the launch date", attendees="Priya Nair, Sam Okafor")

    assert owner(item) == ("team", ["Priya Nair", "Sam Okafor"], [])


def test_placeholder_next_to_a_name_is_ignored_fr7_step3(harness: Harness) -> None:
    assert owner(resolve(harness, "Anita & TBD to agree on the API")) == ("person", ["Anita Desai"], [])


def test_surname_initial_without_a_dot_and_spaced_aliases_match_fr7(harness: Harness) -> None:
    harness.write_roster(("Lena Fischer", ["Big  Boss"]))

    items = harness.ingest_note("- [ ] Priya N to send the quote\n- [ ] Big Boss to run the survey\n", attendees=PRIYAS_AND_RAHULS)

    assert [owner(i) for i in items] == [("person", ["Priya Nair"], []), ("person", ["Lena Fischer"], [])]
