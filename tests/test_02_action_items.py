"""Spec 02: Action Item shapes, Decoys and the owner / task / Due Phrase split.

Each test names the FR/NFR rule it proves. State is built by ingesting crafted
notes and observed through `actiontrack list --json`.
"""

from __future__ import annotations

from typing import Any

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
