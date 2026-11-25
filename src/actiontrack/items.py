"""Find Action Items in a Meeting Note and split each into owner part, task and Due Phrase.

Pure: works on the note's text only (NFR-9). FR-4 (shapes), FR-5 (Decoys), FR-6 (split).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum


class Shape(StrEnum):
    """How an Action Item was written (FR-4)."""

    CHECKBOX = "checkbox"
    MENTION = "mention"
    TABLE = "table"
    ACTION_LINE = "action-line"


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

        Case, spacing, the bullet character and the checkbox mark are ignored, so ticking
        a box or restyling a bullet keeps the same item.
        """
        unmarked = _CHECKBOX_PREFIX.sub("- [ ] ", self.raw_line, count=1)
        return " ".join(unmarked.split()).casefold()


_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<text>.*\S)\s*$")
_CHECKBOX_PREFIX = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+")
_MENTION = re.compile(r"^@(?P<handle>[\w.-]+)\s*:\s*(?P<text>.*)$")
_ACTION_LINE = re.compile(r"^\s*ACTION:\s*(?P<text>.*\S)\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_DELIMITER = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-*:?\s*$")
_TABLE_COLUMNS = ("owner", "action", "due")  # FR-4: found by header name, any order or case
_EMPTY_CELLS = frozenset({"", "—", "–", "-", "n/a"})
_DUE_CELL_PREFIX = re.compile(r"^(?:results\s+)?(?:by|due)\s+", re.IGNORECASE)
_FENCE_OPEN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
_CODE_INDENT = 4  # columns; a tab counts as 4


def extract(text: str) -> list[Occurrence]:
    """Every Action Item occurrence in `text`, in line order."""
    found: list[Occurrence] = []
    lines = _without_decoys(text.splitlines())
    columns: dict[str, int] | None = None  # set while inside an Owner/Action/Due table body
    for index, line in enumerate(lines):
        line_no = index + 1
        if columns is not None:
            if _TABLE_ROW.match(line):
                if occurrence := _table_row(line_no, line, columns):
                    found.append(occurrence)
                continue
            columns = None
        if header := _table_header(line, lines[index + 1] if index + 1 < len(lines) else ""):
            columns = header
        elif match := _CHECKBOX.match(line):
            found.append(_checkbox(line_no, line, match))
        elif match := _ACTION_LINE.match(line):
            owner, task, due = split(match["text"])
            found.append(Occurrence(line_no, line, Shape.ACTION_LINE, False, owner, task, due))
    return found


def _without_decoys(lines: list[str]) -> list[str]:
    """`lines` with every Decoy line blanked (FR-5), so line numbers and table edges are kept.

    Decoys: lines in a fenced code block (an unclosed fence runs to the end), lines
    indented as a code block outside a list, and blockquote lines.
    """
    kept: list[str] = []
    fence: str | None = None  # the opening fence while inside a fenced block
    in_list = False
    for line in lines:
        stripped = line.strip()
        indent = len(line.expandtabs(_CODE_INDENT)) - len(line.expandtabs(_CODE_INDENT).lstrip())
        if fence is not None:
            # Closed by a run of the same fence character at least as long as the opener.
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            kept.append("")
            continue
        if match := _FENCE_OPEN.match(line):
            fence = match["fence"]
            kept.append("")
        elif not stripped:
            kept.append(line)  # blank lines end tables but keep list context
        elif stripped.startswith(">") or (indent >= _CODE_INDENT and not in_list):
            kept.append("")
        else:
            in_list = bool(_LIST_ITEM.match(line)) or (in_list and indent > 0)
            kept.append(line)
    return kept


def _checkbox(line_no: int, line: str, match: re.Match[str]) -> Occurrence:
    checked = match["mark"] in "xX"
    if mention := _MENTION.match(match["text"]):
        task, due = _split_due(mention["text"])
        if task:  # `@karan:` alone has no task, so it falls through to plain text below
            return Occurrence(line_no, line, Shape.MENTION, checked, mention["handle"], task, due)
    owner, task, due = split(match["text"])
    return Occurrence(line_no, line, Shape.CHECKBOX, checked, owner, task, due)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_header(line: str, next_line: str) -> dict[str, int] | None:
    """Column positions when `line` heads an Owner/Action/Due table (followed by a delimiter row)."""
    if not (_TABLE_ROW.match(line) and _TABLE_DELIMITER.match(next_line)):
        return None
    names = [cell.casefold() for cell in _cells(line)]
    if not all(column in names for column in _TABLE_COLUMNS):
        return None
    return {column: names.index(column) for column in _TABLE_COLUMNS}


def _table_row(line_no: int, line: str, columns: dict[str, int]) -> Occurrence | None:
    if _TABLE_DELIMITER.match(line):
        return None
    cells = _cells(line)

    def cell(column: str) -> str | None:
        position = columns[column]
        value = cells[position] if position < len(cells) else ""
        return None if value.casefold() in _EMPTY_CELLS else value

    task = cell("action")
    if task is None:
        return None
    due = cell("due")
    if due is not None:  # same stored form as a text Due Phrase: `by Fri` -> `Fri`
        due = _DUE_CELL_PREFIX.sub("", due).rstrip(_PHRASE_TRIM) or None
    return Occurrence(line_no, line, Shape.TABLE, False, cell("owner"), task, due)


# --- owner / task / Due Phrase split (FR-6) ----------------------------------------

_OWNER_SEPARATOR = " to "
# A name token: capitalised word, initial (`N.`), joiner, or the `?` placeholder.
_OWNER_TOKEN = re.compile(r"[A-Z][\w'’.-]*|[A-Z]\.|&|,|and|\?")
_OWNER_TOKENS = re.compile(r"[^\s,&]+|[,&]")

# Separators a Due Phrase may be attached with: `, by`, `— by`, ` - by`, or plain space.
# All three run on whitespace-collapsed text and avoid lazy-match-to-end patterns, so a
# hostile line is split in linear time (NFR-2).
# A `due <phrase>` clause; needs a separator or `results` first, so `the overdue invoices` stays task.
_DUE_CLAUSE = re.compile(
    r"(?:\s?[,;—–]\s?| - | (?=results ))(?:results )?due (?P<phrase>\S.*)$", re.IGNORECASE
)
# Each `by` that starts a Due Phrase; the lookahead leaves the next separator unconsumed,
# so in `by by Friday` the last `by` is still found. The last match wins.
_BY_KEYWORD = re.compile(r"(?:\s?[,;—–]\s?| - | )by(?= \S)", re.IGNORECASE)
# A bare trailing deadline word, e.g. `circulate the summary tomorrow` (FRD §6).
_BARE_DEADLINE = re.compile(r"(?:\s?[,;—–]\s?| - | )(?P<phrase>(?:EOD )?tomorrow|today|EOD)$", re.IGNORECASE)
_TASK_TRIM = " \t,;—–-"
_PHRASE_TRIM = _TASK_TRIM + ".!?"  # `by Friday.` -> `Friday`


def split(text: str) -> tuple[str | None, str, str | None]:
    """Split item text into (owner part, task, Due Phrase); owner and Due Phrase may be None."""
    text = " ".join(text.split())
    owner, rest = _split_owner(text)
    task, due = _split_due(rest)
    if not task:  # e.g. `Karan to by Friday`: keep everything written as the task
        return None, text.strip(), None
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
    text = " ".join(text.split())
    start: int | None = None
    phrase = ""
    if match := _DUE_CLAUSE.search(text):
        start, phrase = match.start(), match["phrase"]
    elif by := _last(_BY_KEYWORD.finditer(text)):
        start, phrase = by.start(), text[by.end():]
    elif match := _BARE_DEADLINE.search(text):
        start, phrase = match.start(), match["phrase"]
    if start is None:
        return text.strip(_TASK_TRIM), None
    return text[:start].strip(_TASK_TRIM), phrase.strip(_PHRASE_TRIM) or None


def _last(matches: Iterator[re.Match[str]]) -> re.Match[str] | None:
    last = None
    for last in matches:
        pass
    return last
