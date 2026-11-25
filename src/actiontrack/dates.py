"""Date parsing: Meeting Dates (FR-2) and Due Phrase resolution (FR-8).

Pure and locale-independent (English month names are spelled out here rather
than taken from `calendar`), so results never depend on the machine (NFR-3).
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

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

_WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Full names and three-letter abbreviations: "wednesday" and "wed" -> 2 (Monday is 0).
_WEEKDAYS: dict[str, int] = {
    key: number for number, name in enumerate(_WEEKDAY_NAMES) for key in (name, name[:3])
}
_FRIDAY = _WEEKDAYS["friday"]

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


# --- Due Phrase resolution (FR-8) -------------------------------------------------

_DUE_LEADING_WORDS = re.compile(r"^(?:results due|by|due)\b")
_DUE_TRIM = " \t,;:.!?—–-"
_ORDINAL = r"(\d{1,2})(?:st|nd|rd|th)?"
_DAY_MONTH = re.compile(rf"{_ORDINAL} ([a-z]+)")
_MONTH_DAY = re.compile(rf"([a-z]+) {_ORDINAL}")
_MID_MONTH = re.compile(r"mid[- ]?([a-z]+)")
_NEXT_WEEKDAY = re.compile(r"next ([a-z]+)")


def resolve_due_phrase(phrase: str, meeting_date: date) -> date | None:
    """Resolve a Due Phrase against the Meeting Date by the FR-8 rules; `None` if no rule matches.

    Depends only on its arguments, never on today (NFR-3). Weeks run Monday to Sunday.
    """
    text = " ".join(phrase.lower().split()).strip(_DUE_TRIM)
    text = _DUE_LEADING_WORDS.sub("", text).strip(_DUE_TRIM)
    try:
        return _resolve(text, meeting_date)
    except (ValueError, OverflowError):  # no such day (31 Sep), or past date.max
        return None


def _resolve(text: str, m: date) -> date | None:
    """The FR-8 rules in order of precedence; `text` is lowercased with single spaces."""
    if _ISO_DATE.match(text):
        return date.fromisoformat(text)
    explicit = _WEEKDAY_PREFIX.sub("", text, count=1)  # `Wed 16 Sep`: the date wins
    if match := _DAY_MONTH.fullmatch(explicit):
        return _without_year(_MONTHS.get(match[2]), int(match[1]), m)
    if match := _MONTH_DAY.fullmatch(explicit):
        return _without_year(_MONTHS.get(match[1]), int(match[2]), m)
    if match := _MID_MONTH.fullmatch(text):
        return _without_year(_MONTHS.get(match[1]), 15, m)
    if text == "end of month":
        return m.replace(day=calendar.monthrange(m.year, m.month)[1])
    if text == "end of next week":
        return _week_after(m) + timedelta(days=_FRIDAY)
    if (match := _NEXT_WEEKDAY.fullmatch(text)) and match[1] in _WEEKDAYS:
        return _week_after(m) + timedelta(days=_WEEKDAYS[match[1]])
    if text in ("tomorrow", "eod tomorrow"):
        return m + timedelta(days=1)
    if text in ("eod", "today"):
        return m
    if text in _WEEKDAYS:  # strictly after M: `Friday` said on a Friday is a week later
        return m + timedelta(days=(_WEEKDAYS[text] - m.weekday() - 1) % 7 + 1)
    return None


def _week_after(m: date) -> date:
    """Monday of the week after M's week."""
    return m + timedelta(days=7 - m.weekday())


def _without_year(month: int | None, day: int, m: date) -> date | None:
    """A date written without a year: M's year, or the next year if that date is before M."""
    if month is None:
        return None
    due = date(m.year, month, day)  # raises for a day the month doesn't have
    return due if due >= m else due.replace(year=m.year + 1)
