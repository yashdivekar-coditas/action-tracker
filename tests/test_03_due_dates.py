"""Spec 03: resolving Due Phrases to Due Dates against the Meeting Date (FR-8, FR-12, NFR-3).

Each case writes one note with a chosen Meeting Date and one Action Item ending in the
phrase, ingests it, and reads the Due Date back from `list --json`.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import SAMPLE_NOTES, TODAY, Harness


def due_of(harness: Harness, meeting_date: str, ending: str) -> dict[str, Any]:
    """Ingest `ACTION: Karan to file the report <ending>` and return its single item."""
    (item,) = harness.ingest_note(f"ACTION: Karan to file the report {ending}\n", date=meeting_date)
    return item


# Meeting Date, how the item ends, expected Due Date. Weekdays: 2026-09-01 is a Tuesday.
RULES = [
    # <weekday>: first such weekday strictly after M
    ("2026-09-01", "by Friday", "2026-09-04"),
    ("2026-09-04", "by Friday", "2026-09-11"),  # said on a Friday: never the same day
    ("2026-09-18", "by Mon", "2026-09-21"),
    ("2026-09-18", "by Wednesday", "2026-09-23"),
    ("2026-09-01", "by sun", "2026-09-06"),
    # next <weekday>: that weekday in the week after M's week (weeks run Monday-Sunday)
    ("2026-10-05", "by next Tuesday", "2026-10-13"),
    ("2026-10-06", "by next Tuesday", "2026-10-13"),
    ("2026-10-11", "by next Monday", "2026-10-12"),  # said on a Sunday
    ("2026-10-05", "by next fri", "2026-10-16"),
    # tomorrow / EOD tomorrow: M + 1
    ("2026-09-30", "tomorrow", "2026-10-01"),
    ("2026-09-30", "by tomorrow", "2026-10-01"),
    ("2026-09-21", "by EOD tomorrow", "2026-09-22"),
    ("2026-12-31", "tomorrow", "2027-01-01"),
    # EOD / today: M
    ("2026-10-08", "by EOD", "2026-10-08"),
    ("2026-10-08", "today", "2026-10-08"),
    # end of next week: Friday of the week after M's week
    ("2026-09-03", "by end of next week", "2026-09-11"),
    ("2026-09-06", "by end of next week", "2026-09-11"),  # said on a Sunday
    # end of month: last day of M's month
    ("2026-09-14", "by end of month", "2026-09-30"),
    ("2028-02-10", "by end of month", "2028-02-29"),
    # mid-<Month>: the 15th, rolling into next year when already past
    ("2026-09-30", "by mid-October", "2026-10-15"),
    ("2026-09-30", "by mid-Oct", "2026-10-15"),
    ("2026-12-01", "by mid-January", "2027-01-15"),
    # ISO dates are used as they are, even in the past
    ("2026-09-30", "by 2026-10-02", "2026-10-02"),
    ("2026-09-30", "by 2026-09-08", "2026-09-08"),
    # day + month in either order, ordinals, a leading weekday ignored
    ("2026-09-01", "by 10 Sep", "2026-09-10"),
    ("2026-10-05", "by 9 Oct", "2026-10-09"),
    ("2026-09-30", "by Oct 3rd", "2026-10-03"),
    ("2026-09-30", "by Oct 5th", "2026-10-05"),
    ("2026-09-30", "by 1st October", "2026-10-01"),
    ("2026-09-30", ", results due 15 October", "2026-10-15"),
    ("2026-09-30", ", due 15 October", "2026-10-15"),
    ("2026-09-14", "by Wed 16 Sep", "2026-09-16"),
    ("2026-09-14", "by Wednesday, 16 September", "2026-09-16"),
    # no year: M's year, or the next year when that date is before M
    ("2026-12-10", "by 5 Jan", "2027-01-05"),
    ("2026-09-30", "by 30 Sep", "2026-09-30"),
    ("2026-09-30", "by 29 Sep", "2027-09-29"),
    ("2027-12-20", "by 29 Feb", "2028-02-29"),  # rolls into a leap year
    ("2026-09-30", ", due by 15 October", "2026-10-15"),  # leading words stripped repeatedly
    # case and spacing make no difference
    ("2026-09-01", "BY   FRIDAY", "2026-09-04"),
    ("2026-09-30", "by  OCT   5TH", "2026-10-05"),
]


@pytest.mark.parametrize(("meeting_date", "ending", "expected"), RULES)
def test_due_phrase_resolves_against_meeting_date_fr8(
    harness: Harness, meeting_date: str, ending: str, expected: str
) -> None:
    item = due_of(harness, meeting_date, ending)
    assert item["due_date"] == expected, item["due_phrase"]


@pytest.mark.parametrize(
    ("ending", "phrase"),
    [
        ("by the next sprint", "the next sprint"),
        ("by Funday", "Funday"),
        ("by 31 Sep", "31 Sep"),  # no such date
        ("by 2026-02-30", "2026-02-30"),
        ("by 10 Sep 2027", "10 Sep 2027"),  # only ISO carries a year
        ("by end of the quarter", "end of the quarter"),
        ("by 29 Feb", "29 Feb"),  # 2026 has no 29 February and it isn't before M
        ("by midOctober", "midOctober"),
    ],
)
def test_unresolved_due_phrase_keeps_raw_text_and_is_reported_fr8_fr12(
    harness: Harness, ending: str, phrase: str
) -> None:
    harness.write("note.md", f"# Meeting: Sync\nDate: 2026-09-30\nAttendees: Karan Joshi\n\nACTION: Karan to file the report {ending}\n")
    result = harness.ingest()

    assert result.code == 0
    assert result.json["unresolved_due_phrases"] == [{"file": "note.md", "line": 5, "due_phrase": phrase}]
    assert f"Unresolved Due Phrase: note.md:5: {phrase}" in result.err
    (item,) = harness.items()
    assert (item["due_phrase"], item["due_date"]) == (phrase, None)


def test_item_without_due_phrase_has_no_due_date_and_is_not_reported_fr8(harness: Harness) -> None:
    (item,) = harness.ingest_note("ACTION: Karan to file the report\n")
    assert (item["due_phrase"], item["due_date"]) == (None, None)
    assert harness.ingest().json["unresolved_due_phrases"] == []


def test_table_due_column_uses_the_same_rules_fr8(harness: Harness) -> None:
    items = harness.ingest_note(
        "| Owner | Action | Due |\n|---|---|---|\n| Anita | Refresh the brand kit | by Fri |\n"
        "| Sam | Book the room | mid-October |\n",
        date="2026-09-30",
    )
    assert [i["due_date"] for i in items] == ["2026-10-02", "2026-10-15"]


def test_list_due_column_shows_date_else_phrase_else_dash_fr8(harness: Harness) -> None:
    harness.ingest_note(
        "- [ ] Karan to file the report by Friday\n"
        "- [ ] Sam to plan by the next sprint\n"
        "- [ ] Lena to tidy the board\n"
    )
    out = harness.run("list").out
    rows = {line.split("  ")[0]: line for line in out.splitlines()[1:]}
    assert "2026-10-02" in rows["1"]
    assert "the next sprint" in rows["2"]
    assert "—" in rows["3"]


def test_resolution_ignores_today_nfr3(harness: Harness) -> None:
    harness.write("note.md", "# Meeting: Sync\nDate: 2026-09-01\nAttendees: Karan Joshi\n\n- [ ] Karan to file it by Friday\n")
    dues = []
    for today in ("2026-09-02", "2030-01-01"):
        db = harness.db.with_name(f"{today}.db")
        assert harness.run("ingest", str(harness.notes), "--db", str(db), "--today", today, global_options=False).code == 0
        items = harness.run("list", "--json", "--db", str(db), "--today", TODAY, global_options=False).json
        dues.append(items[0]["due_date"])
    assert dues == ["2026-09-04", "2026-09-04"]


def test_due_date_past_the_last_representable_day_is_unresolved_nfr2(harness: Harness) -> None:
    (item,) = harness.ingest_note("ACTION: Karan to file the report tomorrow\n", date="9999-12-31")
    assert (item["due_phrase"], item["due_date"]) == ("tomorrow", None)


# --- sample fixture (FRD §6) ------------------------------------------------------


SAMPLE_DUES = [
    ("2026-09-01-quote-portal-kickoff.md", "send the revised quote to Acme by Friday", "2026-09-04"),
    ("2026-09-03-billing-migration-sync.md", "draft the test plan", "2026-09-11"),
    ("2026-09-14-onboarding-flow-design.md", "by end of month", "2026-09-30"),
    ("2026-09-18-design-review.md", "audit colour contrast", "2026-09-21"),
    ("2026-09-18-design-review.md", "agree on the component API", "2026-09-23"),
    ("2026-09-24-onboarding-flow-design.md", "estimate SSO work", "2026-09-28"),
    ("2026-09-30-q4-offsite.md", "Refresh the brand kit", "2026-10-09"),
    ("2026-09-30-q4-offsite.md", "circulate the offsite summary", "2026-10-01"),
    ("2026-09-30-q4-offsite.md", "validate targets against the budget", "2026-10-05"),
    ("2026-09-30-q4-offsite.md", "run the customer survey", "2026-10-15"),
    ("2026-09-30-q4-offsite.md", "propose the on-call rotation", "2026-10-15"),
    ("2026-09-30-q4-offsite.md", "finalise the Q4 sales targets", "2026-10-03"),
    ("2026-09-30-q4-offsite.md", "prepare the architecture overview", "2026-10-02"),
    ("2026-09-30-standup.md", "approve the Q4 cloud spend", "2026-10-02"),
    ("2026-10-05-onboarding-retro.md", "start SSO spike", "2026-10-13"),
    ("2026-10-08-billing-go-no-go.md", "circulate the go/no-go summary", "2026-10-08"),
    ("2026-09-29-billing-cutover-planning.md", "schedule cutover", None),
    ("2026-09-29-billing-cutover-planning.md", "freeze invoice edits", None),
]


@pytest.fixture
def sample_items(harness: Harness) -> list[dict[str, Any]]:
    assert harness.ingest(SAMPLE_NOTES).code == 0
    return harness.items()


@pytest.mark.parametrize(("file", "text", "expected"), SAMPLE_DUES)
def test_sample_notes_due_dates_match_frd_examples_fr8(
    sample_items: list[dict[str, Any]], file: str, text: str, expected: str | None
) -> None:
    (due,) = {
        item["due_date"]
        for item in sample_items
        for source in item["sources"]
        if source["file"] == file and text in source["raw_line"]
    }
    assert due == expected


def test_sample_notes_report_no_unresolved_due_phrases_fr12(harness: Harness) -> None:
    assert harness.ingest(SAMPLE_NOTES).json["unresolved_due_phrases"] == []
