"""Spec 02: Action Item shapes, Decoys and the owner / task / Due Phrase split.

Each test names the FR/NFR rule it proves. State is built by ingesting crafted
notes and observed through `actiontrack list --json`.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from conftest import Harness


def split(item: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """An item's (written owner, task, Due Phrase)."""
    return item["written_owner"], item["task"], item["due_phrase"]


# --- checkbox shape, storage and list (FR-4, FR-13 basic) --------------------------


def test_checkbox_bullets_with_dash_star_and_plus_fr4(harness: Harness) -> None:
    items = harness.ingest_note(
        "## Action items\n"
        "- [ ] Priya to send the revised quote by Friday\n"
        "* [ ] Rahul to finish login screen by Wed\n"
        "+ [ ] Sam to confirm cloud budget with finance\n"
    )

    assert [split(i) for i in items] == [
        ("Priya", "send the revised quote", "Friday"),
        ("Rahul", "finish login screen", "Wed"),
        ("Sam", "confirm cloud budget with finance", None),
    ]
    assert [i["id"] for i in items] == [1, 2, 3]
    assert {i["status"] for i in items} == {"open"}


def test_each_item_keeps_its_source_line_and_line_number_fr4(harness: Harness) -> None:
    (item,) = harness.ingest_note("## Action items\n- [ ] Sam to share the VPN guide\n", name="standup.md")

    (source,) = item["sources"]
    assert source["file"] == "standup.md"
    assert source["line"] == 6
    assert source["raw_line"] == "- [ ] Sam to share the VPN guide"
    assert source["checked"] is False


def test_ingest_report_counts_new_items_fr12(harness: Harness) -> None:
    harness.write("a.md", "# Meeting: A\nDate: 2026-09-01\n\n- [ ] Sam to do X\n- [ ] Rahul to do Y\n")

    assert harness.ingest().json["items_new"] == 2


def test_list_prints_a_table_of_items_fr13(harness: Harness) -> None:
    harness.ingest_note("- [ ] Priya to send the revised quote by Friday\n- [ ] Book the venue\n")

    result = harness.run("list")

    assert result.code == 0
    lines = result.out.splitlines()
    assert lines[0].split() == ["ID", "OWNER", "TASK", "DUE", "STATUS"]
    assert lines[1].split()[:2] == ["1", "Priya"]
    assert lines[1].rstrip().endswith("Friday  open")
    assert lines[2].split()[:2] == ["2", "—"]


def test_list_on_a_new_database_is_empty_fr13(harness: Harness) -> None:
    assert harness.items() == []


# --- other shapes and status (FR-4, FR-10) -----------------------------------------


def test_nested_checkbox_is_its_own_item_fr4(harness: Harness) -> None:
    items = harness.ingest_note(
        "- [ ] Meera to finalise the Q4 sales targets by Oct 3rd\n"
        "  - [ ] Karan to validate targets against the budget by Oct 5th\n"
        "        - [ ] Sam to double-check the maths\n"
    )

    assert [split(i) for i in items] == [
        ("Meera", "finalise the Q4 sales targets", "Oct 3rd"),
        ("Karan", "validate targets against the budget", "Oct 5th"),
        ("Sam", "double-check the maths", None),
    ]


def test_checked_boxes_are_done_whatever_the_case_fr4_fr10(harness: Harness) -> None:
    items = harness.ingest_note("- [x] Sam to do A\n- [X] Sam to do B\n- [ ] Sam to do C\n")

    assert [i["status"] for i in items] == ["done", "done", "open"]
    assert [i["sources"][0]["checked"] for i in items] == [True, True, False]
    assert harness.ingest().json["items_done"] == 0  # already Done on the first run


def test_first_ingest_counts_newly_done_items_fr12(harness: Harness) -> None:
    harness.write("a.md", "# Meeting: A\nDate: 2026-09-01\n\n- [x] Sam to do A\n- [ ] Sam to do B\n")

    assert harness.ingest().json["items_done"] == 1


def test_mention_prefix_gives_the_owner_part_fr4_fr6(harness: Harness) -> None:
    (item,) = harness.ingest_note("- [ ] @anita: audit colour contrast on the dashboard by Mon\n")

    assert split(item) == ("anita", "audit colour contrast on the dashboard", "Mon")


def test_owner_action_due_table_rows_are_open_items_fr4(harness: Harness) -> None:
    items = harness.ingest_note(
        "## Afternoon\n"
        "We split the follow-ups:\n"
        "\n"
        "| Due | ACTION | owner | Notes |\n"
        "|:---:|--------|-------|-------|\n"
        "| 2026-10-09 | Refresh the brand kit | Anita | |\n"
        "| | Draft the hiring plan | Priya N. | urgent |\n"
        "\n"
        "| Name | Role |\n"
        "|------|------|\n"
        "| Sam | Host |\n"
    )

    assert [split(i) for i in items] == [
        ("Anita", "Refresh the brand kit", "2026-10-09"),
        ("Priya N.", "Draft the hiring plan", None),
    ]
    assert {i["status"] for i in items} == {"open"}
    assert items[0]["sources"][0]["raw_line"] == "| 2026-10-09 | Refresh the brand kit | Anita | |"


def test_action_line_is_an_open_item_fr4(harness: Harness) -> None:
    (item,) = harness.ingest_note(
        "## Wrap-up\nACTION: Karan to circulate the offsite summary tomorrow\n"
    )

    assert split(item) == ("Karan", "circulate the offsite summary", "tomorrow")
    assert item["status"] == "open"


# --- Decoys (FR-5) -----------------------------------------------------------------


def tasks(items: list[dict[str, Any]]) -> list[str]:
    return [i["task"] for i in items]


def test_blockquoted_items_are_decoys_fr5(harness: Harness) -> None:
    items = harness.ingest_note(
        "> Please make sure someone owns refunds this time.\n"
        "> - [ ] Karan to refund affected customers by Friday\n"
        ">> ACTION: Sam to forward the complaint\n"
        "   > | Owner | Action | Due |\n"
        "- [ ] Sam to write the postmortem\n"
    )

    assert tasks(items) == ["write the postmortem"]


def test_fenced_code_blocks_are_decoys_fr5(harness: Harness) -> None:
    items = harness.ingest_note(
        "Template:\n"
        "```markdown\n"
        "- [ ] Owner to remediate finding by <date>\n"
        "```\n"
        "~~~\n"
        "ACTION: Sam to copy this example\n"
        "```\n"  # a different fence char does not close a ~~~ block
        "- [ ] Sam to stay hidden\n"
        "~~~\n"
        "- [ ] Sam to enable MFA on all admin accounts\n"
    )

    assert tasks(items) == ["enable MFA on all admin accounts"]


def test_unclosed_fence_hides_the_rest_of_the_note_fr5_nfr2(harness: Harness) -> None:
    items = harness.ingest_note("- [ ] Sam to do A\n```\n- [ ] Sam to do B\n")

    assert tasks(items) == ["do A"]


def test_indented_code_blocks_are_decoys_but_nested_list_items_are_not_fr5(harness: Harness) -> None:
    items = harness.ingest_note(
        "Example of the format:\n"
        "\n"
        "    - [ ] Owner to do the thing by Friday\n"
        "\tACTION: Sam to copy this example\n"
        "\n"
        "- [ ] Meera to finalise the targets\n"
        "    - [ ] Karan to validate the targets\n"
        "\n"
        "        - [ ] Lena to check the maths\n"
    )

    assert tasks(items) == ["finalise the targets", "validate the targets", "check the maths"]


# --- owner / task / Due Phrase split (FR-6) ----------------------------------------

SPLIT_CASES = [
    # owner part: only name tokens before the first " to "
    ("Book the venue for the offsite", (None, "Book the venue for the offsite", None)),
    ("Ask the team to vote on the logo by Friday", (None, "Ask the team to vote on the logo", "Friday")),
    ("Lena (with Priya) to collect user feedback", (None, "Lena (with Priya) to collect user feedback", None)),
    ("Priya N. to send revised quote to Acme — by Friday", ("Priya N.", "send revised quote to Acme", "Friday")),
    ("Anita & Rahul to agree on the component API by Wednesday", ("Anita & Rahul", "agree on the component API", "Wednesday")),
    ("Anita, Rahul and Sam to pair on the API", ("Anita, Rahul and Sam", "pair on the API", None)),
    ("Team to decide on the launch date", ("Team", "decide on the launch date", None)),
    ("TBD to write the design-system changelog", ("TBD", "write the design-system changelog", None)),
    ("? to own the release notes", ("?", "own the release notes", None)),
    ("Everyone to submit their Q4 goals by 7 Oct", ("Everyone", "submit their Q4 goals", "7 Oct")),
    # Due Phrase: only a trailing by-clause, a due-clause, or a bare tomorrow/today/EOD
    ("Lena to run the customer survey, results due 15 October", ("Lena", "run the customer survey", "15 October")),
    ("Sam to send the draft, due Friday", ("Sam", "send the draft", "Friday")),
    ("Sam to cut cloud costs by 10% — proposal by 2026-10-09", ("Sam", "cut cloud costs by 10% — proposal", "2026-10-09")),
    ("Sam to schedule cutover for Saturday 10 Oct", ("Sam", "schedule cutover for Saturday 10 Oct", None)),
    ("Karan to freeze invoice edits from 9 Oct", ("Karan", "freeze invoice edits from 9 Oct", None)),
    ("Meera to demo the portal to Acme on 2026-10-14", ("Meera", "demo the portal to Acme on 2026-10-14", None)),
    ("Sam to write the postmortem by EOD tomorrow", ("Sam", "write the postmortem", "EOD tomorrow")),
    ("Priya to circulate the summary EOD", ("Priya", "circulate the summary", "EOD")),
    ("Karan to pay the overdue invoices", ("Karan", "pay the overdue invoices", None)),
    ("Rahul to write the runbook, by Monday,", ("Rahul", "write the runbook", "Monday")),
]


@pytest.mark.parametrize(("text", "expected"), SPLIT_CASES, ids=[c[0][:40] for c in SPLIT_CASES])
def test_owner_task_and_due_phrase_split_fr6(harness: Harness, text: str, expected: tuple) -> None:
    (item,) = harness.ingest_note(f"- [ ] {text}\n")

    assert split(item) == expected


def test_same_split_rules_apply_to_action_lines_fr6(harness: Harness) -> None:
    (item,) = harness.ingest_note("ACTION: Lena to run the customer survey, results due 15 October\n")

    assert split(item) == ("Lena", "run the customer survey", "15 October")


# --- re-ingest and status across runs (FR-10, FR-11, FR-3) -------------------------

NOTE_HEADER = "# Meeting: Sync\nDate: 2026-09-01\n\n"


def test_reingest_creates_no_new_items_and_keeps_ids_fr11(harness: Harness) -> None:
    harness.write("a.md", NOTE_HEADER + "- [ ] Sam to do A\n- [ ] Rahul to do B by Friday\n")
    harness.write("b.md", NOTE_HEADER + "ACTION: Karan to do C\n")
    first = harness.ingest()
    before = harness.items()

    again = harness.ingest()

    assert first.json["items_new"] == 3
    assert again.json["items_new"] == 0
    assert harness.items() == before


def test_moved_or_respaced_line_is_the_same_occurrence_fr11(harness: Harness) -> None:
    harness.write("a.md", NOTE_HEADER + "- [ ] Sam to do A\n")
    harness.ingest()

    harness.write("a.md", NOTE_HEADER + "Intro line.\n\n*  [ ]  Sam to do A\n")
    result = harness.ingest()

    assert result.json["items_new"] == 0
    (item,) = harness.items()
    assert item["id"] == 1
    assert item["sources"][0]["line"] == 6  # the Source follows the line


def test_ticking_a_box_later_marks_the_same_item_done_fr10_fr11(harness: Harness) -> None:
    harness.write("a.md", NOTE_HEADER + "- [ ] Sam to do A\n")
    harness.ingest()

    harness.write("a.md", NOTE_HEADER + "- [x] Sam to do A\n")
    result = harness.ingest()

    assert (result.json["items_new"], result.json["items_done"]) == (0, 1)
    (item,) = harness.items()
    assert (item["id"], item["status"]) == (1, "done")


def test_done_is_never_cleared_by_unticking_fr10(harness: Harness) -> None:
    harness.write("a.md", NOTE_HEADER + "- [x] Sam to do A\n")
    harness.ingest()

    harness.write("a.md", NOTE_HEADER + "- [ ] Sam to do A\n")
    harness.ingest()

    (item,) = harness.items()
    assert item["status"] == "done"
    assert item["sources"][0]["checked"] is False


def test_malformed_note_stores_no_items_fr3(harness: Harness) -> None:
    harness.write("untitled.md", "- [ ] Sam to chase the vendor\n- [ ] Priya to send the slides by Friday\n")

    result = harness.ingest()

    assert result.json["items_new"] == 0
    assert harness.items() == []


# --- review fixes: consistent values (FR-6) ----------------------------------------


def test_table_cells_follow_the_same_rules_as_text_items_fr6(harness: Harness) -> None:
    items = harness.ingest_note(
        "| Owner | Action | Due |\n"
        "|---|---|---|\n"
        "| Anita | Refresh the brand kit | by Fri |\n"
        "| — | Pick a venue | — |\n"
        "| n/a | Book the room | due 9 Oct. |\n"
    )

    assert [split(i) for i in items] == [
        ("Anita", "Refresh the brand kit", "Fri"),
        (None, "Pick a venue", None),
        (None, "Book the room", "9 Oct"),
    ]


def test_trailing_sentence_punctuation_is_not_part_of_the_due_phrase_fr6(harness: Harness) -> None:
    items = harness.ingest_note("- [ ] Karan to pay the invoice by Friday.\nACTION: Sam to file it, due 15 October!\n")

    assert [i["due_phrase"] for i in items] == ["Friday", "15 October"]


def test_an_item_never_has_an_empty_task_fr6(harness: Harness) -> None:
    items = harness.ingest_note("- [ ] @karan:\n- [ ] Karan to by Friday\n")

    assert [split(i) for i in items] == [(None, "@karan:", None), ("Karan", "by Friday", None)]


def test_pathological_lines_are_split_in_linear_time_nfr2(harness: Harness) -> None:
    started = time.perf_counter()
    items = harness.ingest_note(
        "- [ ] Karan to x" + " " * 20_000 + "y\n"
        "- [ ] Karan to x " + "by " * 20_000 + "Friday\n"
        "- [ ] Karan to x, due" + " " * 20_000 + "z\n"
    )

    assert time.perf_counter() - started < 2  # quadratic backtracking took ~48 s
    assert len(items) == 3


def test_fenced_block_indented_under_a_list_item_is_a_decoy_fr5(harness: Harness) -> None:
    items = harness.ingest_note(
        "- Notes on the migration\n"
        "    ```\n"
        "    - [ ] Karan to code by Fri\n"
        "    ```\n"
        "- [ ] Sam to review the plan\n"
    )

    assert tasks(items) == ["review the plan"]


def test_line_numbers_count_only_real_line_breaks_fr4(harness: Harness) -> None:
    (item,) = harness.ingest_note("Pasted text\x0cwith odd breaks\n- [ ] Sam to do A\n")

    assert item["sources"][0]["line"] == 6


def test_escaped_pipe_stays_inside_a_table_cell_fr4(harness: Harness) -> None:
    (item,) = harness.ingest_note("| Owner | Action | Due |\n|---|---|---|\n| Sam | Merge A \\| B | 9 Oct |\n")

    assert split(item) == ("Sam", "Merge A | B", "9 Oct")
