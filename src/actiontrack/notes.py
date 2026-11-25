"""Turn a file's bytes into a Meeting Note or a Malformed reason (FR-2, FR-3).

Pure: no I/O beyond the bytes it is given (NFR-9).

Two header styles are understood:
- YAML front-matter, only when the first line is `---`. Just the `key: value` and
  `key: [a, b]` forms are supported, which covers `title`, `date` and `attendees`
  without a YAML library (NFR-7).
- The house template: the first `# Meeting:` line (else the first `#` heading) is the
  title, and `Date:` / `Attendees:` lines are read anywhere before the first `##`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import PurePath

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


# Malformed reasons (FR-3). `ingest` adds "unreadable: <error>" for anything unexpected.
NOT_TEXT = "not text"
EMPTY = "empty"
NO_MEETING_DATE = "no meeting date"
UNRESOLVABLE_MEETING_DATE = "unresolvable meeting date"

_FRONT_MATTER_FENCE = "---"
_KEY_VALUE = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$")
_TITLE_MEETING = re.compile(r"^#\s+Meeting:\s*(.*)$", re.IGNORECASE)
_TITLE_ANY = re.compile(r"^#\s+(.*)$")
_HEADER_FIELDS = frozenset({"date", "attendees"})


def parse(data: bytes, file_name: str) -> Note | Malformed:
    """Parse one note. `file_name` (without `.md`) is the title fallback when the note has none."""
    try:
        text = data.decode("utf-8-sig")  # NFR-8: a UTF-8 byte-order mark is accepted
    except UnicodeDecodeError:
        return Malformed(NOT_TEXT)
    if "\x00" in text:  # valid UTF-8 can still be binary
        return Malformed(NOT_TEXT)
    if not text.strip():
        return Malformed(EMPTY)

    lines = text.splitlines()
    if lines[0].strip() == _FRONT_MATTER_FENCE:
        fields = _front_matter(lines[1:])
    else:
        fields = _template_header(lines)

    raw_date = fields.get("date", "")
    if not raw_date:
        return Malformed(NO_MEETING_DATE)
    meeting_date = dates.parse_meeting_date(raw_date)
    if meeting_date is None:
        return Malformed(f"{UNRESOLVABLE_MEETING_DATE}: {raw_date}")

    return Note(
        title=fields.get("title") or PurePath(file_name).stem,
        meeting_date=meeting_date,
        attendees=_split_names(fields.get("attendees", "")),
    )


def _front_matter(lines: list[str]) -> dict[str, str]:
    """`key: value` pairs up to the closing `---` (or the end, if it is never closed)."""
    fields: dict[str, str] = {}
    for line in lines:
        if line.strip() == _FRONT_MATTER_FENCE:
            break
        if match := _KEY_VALUE.match(line):
            fields.setdefault(match[1].lower(), _unquote(match[2]))
    return fields


def _template_header(lines: list[str]) -> dict[str, str]:
    """Title, `Date:` and `Attendees:` from the lines before the first `##` heading."""
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
        elif (match := _KEY_VALUE.match(line)) and match[1].lower() in _HEADER_FIELDS:
            fields.setdefault(match[1].lower(), match[2])
    # The first `# Meeting:` line wins over any plain `#` heading.
    title = meeting_title if meeting_title is not None else first_heading
    if title is not None:
        fields["title"] = title.strip()
    return fields


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _split_names(value: str) -> tuple[str, ...]:
    """Attendees from `a, b` or `[a, b]`, trimmed, blanks dropped."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    names = (_unquote(name.strip()) for name in value.split(","))
    return tuple(name for name in names if name)
