"""Date parsing. Meeting Dates here; Due Date resolution arrives in spec 03 (FR-2, FR-8).

Pure and locale-independent, so results never depend on the machine (NFR-3).
"""

from __future__ import annotations

from datetime import date


def parse_meeting_date(text: str) -> date | None:
    """Parse a Meeting Date as written in a note header; `None` if it can't be resolved."""
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None
