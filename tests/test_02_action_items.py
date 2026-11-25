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
