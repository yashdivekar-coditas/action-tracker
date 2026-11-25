"""Spec 07: `list` shows Open items, Overdue first, filtered by status and due date (FR-13).

State is built by ingesting crafted notes (Meeting Date 2026-09-30) and observed
through `list --json`, the exit code and one smoke test of the human table.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import Harness

# --today is 2026-10-15. Items are written in id order: ids 1..6.
NOTE = (
    "- [ ] Karan to file the tax return by 2026-10-14\n"  # 1: overdue, 1 day
    "- [ ] Karan to ship the beta by 2026-10-20\n"  # 2: open, future
    "- [ ] Karan to plan the offsite\n"  # 3: open, undated
    "- [ ] Karan to renew the licence by 2026-10-01\n"  # 4: overdue, 14 days
    "- [x] Karan to close the audit by 2026-10-02\n"  # 5: done, past due date
    "- [ ] Karan to book the venue by 2026-10-15\n"  # 6: open, due today (not overdue)
)


TABLE_HEADER = ["ID", "OWNER", "TASK", "DUE", "STATUS", "MEETING"]


def listing(harness: Harness, *flags: str) -> list[dict[str, Any]]:
    result = harness.run("list", "--json", *flags)
    assert result.code == 0, result.err
    return result.json


def ids(harness: Harness, *flags: str) -> list[int]:
    return [item["id"] for item in listing(harness, *flags)]


@pytest.fixture
def seeded(harness: Harness) -> Harness:
    harness.ingest_note(NOTE, attendees="Karan Joshi")
    return harness


def test_no_flags_lists_open_items_only_overdue_first_most_late_first_fr13(seeded: Harness) -> None:
    # overdue (14d, 1d), then dated by Due Date (today, future), then undated; Done is left out.
    assert ids(seeded) == [4, 1, 6, 2, 3]


def test_all_lists_every_status_in_the_same_order_fr13(seeded: Harness) -> None:
    assert ids(seeded, "--all") == [4, 1, 5, 6, 2, 3]


def test_ties_break_by_id_fr13(harness: Harness) -> None:
    harness.ingest_note("- [ ] Karan to a by 2026-10-20\n- [ ] Karan to b by 2026-10-20\n- [ ] Karan to c\n- [ ] Karan to d\n")
    assert ids(harness) == [1, 2, 3, 4]


def test_status_open_includes_overdue_fr13(seeded: Harness) -> None:
    assert ids(seeded, "--status", "open") == [4, 1, 6, 2, 3]


def test_status_overdue_is_open_items_past_their_due_date_fr13(seeded: Harness) -> None:
    assert ids(seeded, "--status", "overdue") == [4, 1]


def test_status_done_lists_done_items_fr13(seeded: Harness) -> None:
    assert ids(seeded, "--status", "done") == [5]


def test_all_overrides_status_fr13(seeded: Harness) -> None:
    assert ids(seeded, "--status", "done", "--all") == [4, 1, 5, 6, 2, 3]


def test_json_days_overdue_is_set_only_on_overdue_items_fr13(seeded: Harness) -> None:
    by_id = {item["id"]: item for item in listing(seeded, "--all")}
    assert {i: (item["status"], item["days_overdue"]) for i, item in by_id.items()} == {
        1: ("open", 1),
        2: ("open", None),
        3: ("open", None),
        4: ("open", 14),
        5: ("done", None),
        6: ("open", None),
    }


def test_due_before_is_strict_and_excludes_undated_items_fr13(seeded: Harness) -> None:
    assert ids(seeded, "--due-before", "2026-10-15") == [4, 1]
    assert ids(seeded, "--due-before", "2026-10-16") == [4, 1, 6]


def test_filters_are_anded_fr13(seeded: Harness) -> None:
    assert ids(seeded, "--status", "open", "--due-before", "2026-10-20") == [4, 1, 6]
    assert ids(seeded, "--all", "--due-before", "2026-10-03") == [4, 5]


@pytest.mark.parametrize("flags", [("--status", "late"), ("--due-before", "soon"), ("--due-before", "2026-13-01"), ("--due-before", "20261001")])
def test_invalid_filter_values_exit_2_fr13(seeded: Harness, flags: tuple[str, ...]) -> None:
    result = seeded.run("list", *flags)
    assert result.code == 2
    assert result.err


def test_no_matching_items_says_so_and_exits_0_fr13(seeded: Harness) -> None:
    result = seeded.run("list", "--due-before", "2000-01-01")
    assert (result.code, result.out.strip()) == (0, "No matching items.")
    assert listing(seeded, "--due-before", "2000-01-01") == []


def test_table_shows_overdue_with_days_late_fr13(seeded: Harness) -> None:
    out = seeded.run("list").out
    assert out.splitlines()[0].split() == TABLE_HEADER
    assert "overdue (14d)" in out and "overdue (1d)" in out
    assert "done" not in out


def test_sample_notes_overdue_includes_the_q4_sales_targets_fr13(harness: Harness) -> None:
    from conftest import SAMPLE_NOTES

    assert harness.ingest(SAMPLE_NOTES).code == 0
    [item] = [i for i in listing(harness, "--status", "overdue") if "Q4 sales targets" in i["task"]]
    assert (item["persons"], item["days_overdue"]) == (["Meera Iyer"], 12)


# --- table rendering (FR-13) ---------------------------------------------------------


def test_table_ends_with_the_latest_source_meeting_date_and_title_fr13(harness: Harness) -> None:
    harness.write("a.md", "# Meeting: Kickoff\nDate: 2026-09-01\nAttendees: Karan Joshi\n\n- [ ] Karan to ship the beta by 2026-10-20\n")
    harness.write("b.md", "# Meeting: Standup\nDate: 2026-09-20\nAttendees: Karan Joshi\n\n- [ ] Karan to ship the beta\n")
    assert harness.ingest().code == 0
    lines = harness.run("list").out.splitlines()
    assert lines[0].split() == TABLE_HEADER
    assert lines[1].endswith("2026-09-20 Standup")  # the latest Source, not the first
    assert len(lines) == 2


def test_json_sources_carry_the_meeting_title_and_date_fr13(seeded: Harness) -> None:
    source = listing(seeded)[0]["sources"][0]
    assert (source["title"], source["meeting_date"]) == ("Test meeting", "2026-09-30")
    assert {"file", "path", "line", "raw_line", "checked"} <= source.keys()  # keys are only ever added (NFR-6)


def test_long_task_is_truncated_with_an_ellipsis_to_the_terminal_width_fr13(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = "write up " + "a very long description " * 10 + "END"
    harness.ingest_note(f"- [ ] Karan to {task}\n", attendees="Karan Joshi")
    monkeypatch.setenv("COLUMNS", "80")
    lines = harness.run("list").out.splitlines()
    assert all(len(line) <= 80 for line in lines)
    assert "…" in lines[1] and "END" not in lines[1]
    assert lines[1].rstrip().endswith("Test meeting")  # the right-hand columns survive
    assert listing(harness)[0]["task"].endswith("END")  # --json is never truncated


def test_wide_owner_column_of_a_team_item_still_fits_the_width_fr13(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    attendees = "Priya Nair, Rahul Mehta, Anita Desai, Sam Okafor, Meera Iyer, Karan Joshi"
    harness.ingest_note("- [ ] Team to review the plan by 2026-10-20\n", attendees=attendees)
    monkeypatch.setenv("COLUMNS", "100")
    lines = harness.run("list").out.splitlines()
    assert all(len(line) <= 100 for line in lines)
    assert "Priya Nair" in lines[1] and "…" in lines[1]


def test_width_falls_back_to_100_columns_when_undetectable_fr13(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_terminal(*_: object) -> None:
        raise OSError

    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.setattr("os.get_terminal_size", no_terminal)
    harness.ingest_note("- [ ] Karan to " + "x" * 200 + "\n", attendees="Karan Joshi")
    lines = harness.run("list").out.splitlines()
    assert max(len(line) for line in lines) == 100
