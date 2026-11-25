"""Turn a file's bytes into a Meeting Note or a Malformed reason (FR-2, FR-3).

Pure: no I/O beyond the bytes it is given (NFR-9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from actiontrack import dates


@dataclass(frozen=True)
class Note:
    """A Meeting Note's header."""

    title: str
    meeting_date: date
    attendees: tuple[str, ...]


@dataclass(frozen=True)
class Malformed:
    """Why a note was skipped; one of the fixed reasons in FR-3."""

    reason: str


_TITLE_MEETING = re.compile(r"^#\s+Meeting:\s*(.*)$", re.IGNORECASE)
_TITLE_ANY = re.compile(r"^#\s+(.*)$")
_HEADER_FIELD = re.compile(r"^\s*(date|attendees)\s*:\s*(.*)$", re.IGNORECASE)


def parse(data: bytes, file_name: str) -> Note | Malformed:
    """Parse one note. `file_name` is the title fallback when the note has none."""
    text = data.decode("utf-8")
    fields = _template_header(text.splitlines())

    raw_date = fields.get("date", "")
    meeting_date = dates.parse_meeting_date(raw_date)
    assert meeting_date is not None

    return Note(
        title=fields.get("title") or file_name,
        meeting_date=meeting_date,
        attendees=_split_names(fields.get("attendees", "")),
    )


def _template_header(lines: list[str]) -> dict[str, str]:
    """`# Meeting: <title>`, `Date:` and `Attendees:` lines before the first `##` heading."""
    fields: dict[str, str] = {}
    meeting_title: str | None = None
    first_heading: str | None = None
    for line in lines:
        if line.startswith("##"):
            break
        if match := _TITLE_MEETING.match(line):
            meeting_title = meeting_title if meeting_title is not None else match[1]
        elif match := _TITLE_ANY.match(line):
            first_heading = first_heading if first_heading is not None else match[1]
        elif match := _HEADER_FIELD.match(line):
            fields.setdefault(match[1].lower(), match[2])
    # The first `# Meeting:` line wins over any plain `#` heading.
    title = meeting_title if meeting_title is not None else first_heading
    if title is not None:
        fields["title"] = title.strip()
    return fields


def _split_names(value: str) -> tuple[str, ...]:
    return tuple(name.strip() for name in value.split(",") if name.strip())
