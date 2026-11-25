"""End-to-end: ingest the shared sample `notes/` folder (FRD §6, NFR-2, NFR-5).

`notes/` is read-only test data; only the temp database is written.
"""

from __future__ import annotations

from conftest import SAMPLE_NOTES, Harness, malformed_reasons


def test_sample_notes_folder_fr1_fr3_nfr2(harness: Harness) -> None:
    result = harness.ingest(SAMPLE_NOTES)

    assert result.code == 0
    report = result.json
    assert (report["notes_read"], report["malformed"], report["ignored"]) == (31, 4, 1)
    assert malformed_reasons(report) == {
        "2026-09-09-notes-final-v2.md": "empty",
        "2026-10-03-sales-pipeline.md": "unresolvable meeting date: sometime last week",
        "scratch.md": "not text",
        "untitled.md": "no meeting date",
    }


def test_sample_yaml_and_long_date_headers_fr2(harness: Harness) -> None:
    notes = {n["file"]: n for n in harness.ingest(SAMPLE_NOTES).json["notes"]}

    assert notes["2026-09-16-standup.md"] == {
        "file": "2026-09-16-standup.md",
        "title": "Team standup",
        "meeting_date": "2026-09-16",
        "attendees": ["Anita Desai", "Lena Fischer", "Meera Iyer"],
    }
    assert notes["2026-09-09-qa-standup.md"]["meeting_date"] == "2026-09-09"
    assert notes["2026-09-14-onboarding-flow-design.md"]["meeting_date"] == "2026-09-14"
    assert notes["2026-09-23-standup.md"]["attendees"] == []


def test_sample_items_shapes_and_decoys_fr4_fr5(harness: Harness) -> None:
    harness.ingest(SAMPLE_NOTES)
    items = harness.items()

    def found(file: str) -> list[tuple]:
        return [
            (i["written_owner"], i["task"], i["due_phrase"])
            for i in items
            if any(s["file"] == file for s in i["sources"])
        ]

    raw_lines = {s["raw_line"] for i in items for s in i["sources"]}
    # Decoys: the blockquoted refund, the fenced template, the HTML-commented line.
    assert not any(line.lstrip().startswith(">") for line in raw_lines)
    assert not any("remediate finding" in line or "hardware tokens" in line for line in raw_lines)
    assert ("Karan", "refund affected customers", None) in found("2026-09-21-incident-review.md")

    offsite = found("2026-09-30-q4-offsite.md")
    assert ("Anita", "Refresh the brand kit", "2026-10-09") in offsite
    assert ("Karan", "circulate the offsite summary", "tomorrow") in offsite
    assert ("Karan", "validate targets against the budget", "Oct 5th") in offsite
    assert ("Lena", "run the customer survey", "15 October") in offsite
    assert ("Sam", "propose the on-call rotation", "mid-October") in offsite


def test_sample_reingest_is_idempotent_fr11(harness: Harness) -> None:
    first = harness.ingest(SAMPLE_NOTES).json
    before = harness.items()

    again = harness.ingest(SAMPLE_NOTES).json

    assert first["items_new"] == len(before) > 0
    assert again["items_new"] == again["items_done"] == 0
    assert harness.items() == before


def test_sample_owner_resolution_fr7(harness: Harness) -> None:
    harness.ingest(SAMPLE_NOTES)
    items = harness.items()

    def owner_of(file: str, task_start: str) -> tuple[str, list[str], list[str]]:
        (item,) = [
            i for i in items
            if i["task"].startswith(task_start) and any(s["file"] == file for s in i["sources"])
        ]  # fmt: skip
        return item["owner_kind"], item["persons"], item["candidates"]

    assert owner_of("2026-09-01-quote-portal-kickoff.md", "send the revised quote") == ("person", ["Priya Nair"], [])
    assert owner_of("2026-09-03-billing-migration-sync.md", "draft the test plan") == ("person", ["Priya Shah"], [])
    assert owner_of("2026-09-18-design-review.md", "agree on the component API") == (
        "person", ["Anita Desai", "Rahul Mehta"], [],
    )  # fmt: skip
    assert owner_of("2026-09-18-design-review.md", "audit colour contrast") == ("person", ["Anita Desai"], [])
    assert owner_of("2026-09-18-design-review.md", "write the design-system")[0] == "unassigned"
    assert owner_of("2026-09-10-acme-renewal-prep.md", "update the CRM notes")[0] == "unassigned"
    assert owner_of("2026-10-01-quote-portal-weekly.md", "decide on the launch date") == (
        "team", ["Priya Nair", "Rahul Mehta", "Anita Desai", "Sam Okafor", "Meera Iyer"], [],
    )  # fmt: skip
    assert owner_of("2026-10-08-billing-go-no-go.md", "circulate the go/no-go") == (
        "ambiguous", [], ["Priya Nair", "Priya Shah"],
    )  # fmt: skip
    assert owner_of("2026-09-30-q4-offsite.md", "prepare the architecture") == (
        "ambiguous", [], ["Rahul Mehta", "Rahul Verma"],
    )  # fmt: skip
