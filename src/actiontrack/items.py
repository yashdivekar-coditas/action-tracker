"""Find Action Items in a Meeting Note and split each into owner part, task and Due Phrase.

Pure: works on the note's text only (NFR-9). FR-4 (shapes), FR-5 (Decoys), FR-6 (split).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Shape(StrEnum):
    """How an Action Item was written (FR-4)."""

    CHECKBOX = "checkbox"


@dataclass(frozen=True)
class Occurrence:
    """One Action Item as written on one line of a note: the future Source of an item."""

    line_no: int  # 1-based, counted over the whole file
    raw_line: str
    shape: Shape
    checked: bool
    owner_part: str | None  # as written, resolved to Persons in spec 05
    task: str
    due_phrase: str | None  # raw, resolved to a Due Date in spec 03

    @property
    def line_key(self) -> str:
        """Identity of this occurrence within its note, for idempotent re-ingest (FR-11).

        Case, spacing and the checkbox mark are ignored, so ticking a box keeps the same item.
        """
        return " ".join(_CHECK_MARK.sub("[ ]", self.raw_line, count=1).split()).casefold()


_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<text>.*\S)\s*$")
_CHECK_MARK = re.compile(r"\[[xX]\]")


def extract(text: str) -> list[Occurrence]:
    """Every Action Item occurrence in `text`, in line order."""
    found: list[Occurrence] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if match := _CHECKBOX.match(line):
            owner, task, due = split(match["text"])
            found.append(
                Occurrence(line_no, line, Shape.CHECKBOX, match["mark"] in "xX", owner, task, due)
            )
    return found


# --- owner / task / Due Phrase split (FR-6) ----------------------------------------

_OWNER_SEPARATOR = " to "
# A name token: capitalised word, initial (`N.`), joiner, or the `?` placeholder.
_OWNER_TOKEN = re.compile(r"[A-Z][\w'’.-]*|[A-Z]\.|&|,|and|\?")
_OWNER_TOKENS = re.compile(r"[^\s,&]+|[,&]")

# Separators a Due Phrase may be attached with: `, by`, `— by`, ` - by`, or plain space.
_SEP = r"(?:\s*[,;—–]\s*|\s+-\s+|\s+)"
# A trailing `by <phrase>`; the phrase may not contain another ` by `, so the last one wins.
_BY_CLAUSE = re.compile(_SEP + r"by\s+(?P<phrase>(?:(?!\sby\s).)+?)\s*$", re.IGNORECASE)
_TASK_TRIM = " \t,;—–-"


def split(text: str) -> tuple[str | None, str, str | None]:
    """Split item text into (owner part, task, Due Phrase); owner and Due Phrase may be None."""
    owner, rest = _split_owner(text)
    task, due = _split_due(rest)
    return owner, task, due


def _split_owner(text: str) -> tuple[str | None, str]:
    head, sep, rest = text.partition(_OWNER_SEPARATOR)
    if sep and _is_owner_part(head):
        return head.strip(), rest
    return None, text


def _is_owner_part(text: str) -> bool:
    tokens = _OWNER_TOKENS.findall(text)
    return bool(tokens) and all(_OWNER_TOKEN.fullmatch(t) for t in tokens) and any(
        t not in {"&", ",", "and"} for t in tokens
    )


def _split_due(text: str) -> tuple[str, str | None]:
    if match := _BY_CLAUSE.search(text):
        return text[: match.start()].strip(_TASK_TRIM), match["phrase"]
    return text.strip(_TASK_TRIM), None
