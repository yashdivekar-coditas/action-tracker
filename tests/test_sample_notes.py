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
