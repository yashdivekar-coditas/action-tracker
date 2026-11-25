"""Date parsing. Meeting Dates here; Due Date resolution arrives in spec 03 (FR-2, FR-8).

Pure and locale-independent (English month names are spelled out here rather
than taken from `calendar`), so results never depend on the machine (NFR-3).
"""

from __future__ import annotations

import re
from datetime import date

_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)  # fmt: skip
# Full names and three-letter abbreviations: "september" and "sep" -> 9.
_MONTHS: dict[str, int] = {
    key: number
    for number, name in enumerate(_MONTH_NAMES, start=1)
    for key in (name, name[:3])
}

# FR-2: a leading weekday ("Monday, ") is ignored, not checked against the date.
_WEEKDAY_PREFIX = re.compile(
    r"^(?:mon|tue|wed|thu|fri|sat|sun)(?:day|sday|nesday|rsday|urday)?,?\s+",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})\s+([a-z]+)\s+(\d{4})$", re.IGNORECASE)


def parse_meeting_date(text: str) -> date | None:
    """Parse a Meeting Date as written in a note header; `None` if it can't be resolved.

    Accepts `2026-09-01`, `9 September 2026`, `9 Sep 2026` and `Monday, 14 September 2026`.
    """
    text = _WEEKDAY_PREFIX.sub("", text.strip(), count=1)
    if match := _ISO_DATE.match(text):
        year, month, day = int(match[1]), int(match[2]), int(match[3])
    elif match := _DAY_MONTH_YEAR.match(text):
        month_number = _MONTHS.get(match[2].lower())
        if month_number is None:
            return None
        year, month, day = int(match[3]), month_number, int(match[1])
    else:
        return None
    try:
        return date(year, month, day)
    except ValueError:  # e.g. 31 February
        return None
