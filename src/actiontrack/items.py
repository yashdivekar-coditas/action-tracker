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
        return value or None

    task = cell("action")
    if task is None:
        return None
    return Occurrence(line_no, line, Shape.TABLE, False, cell("owner"), task, cell("due"))


# --- owner / task / Due Phrase split (FR-6) ----------------------------------------

_OWNER_SEPARATOR = " to "
# A name token: capitalised word, initial (`N.`), joiner, or the `?` placeholder.
_OWNER_TOKEN = re.compile(r"[A-Z][\w'’.-]*|[A-Z]\.|&|,|and|\?")
_OWNER_TOKENS = re.compile(r"[^\s,&]+|[,&]")

# Separators a Due Phrase may be attached with: `, by`, `— by`, ` - by`, or plain space.
_SEP = r"(?:\s*[,;—–]\s*|\s+-\s+|\s+)"
# A `due <phrase>` clause; needs a separator or `results` first, so `the overdue invoices` stays task.
_DUE_CLAUSE = re.compile(
    r"(?:\s*[,;—–]\s*|\s+-\s+|\s+(?=results\s))(?:results\s+)?due\s+(?P<phrase>.+?)\s*$",
    re.IGNORECASE,
)
# A trailing `by <phrase>`; the phrase may not contain another ` by `, so the last one wins.
_BY_CLAUSE = re.compile(_SEP + r"by\s+(?P<phrase>(?:(?!\sby\s).)+?)\s*$", re.IGNORECASE)
# A bare trailing deadline word, e.g. `circulate the summary tomorrow` (FRD §6).
_BARE_DEADLINE = re.compile(_SEP + r"(?P<phrase>(?:EOD\s+)?tomorrow|today|EOD)\s*$", re.IGNORECASE)
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
    for clause in (_DUE_CLAUSE, _BY_CLAUSE, _BARE_DEADLINE):
        if match := clause.search(text):
            return text[: match.start()].strip(_TASK_TRIM), match["phrase"].rstrip(_TASK_TRIM)
    return text.strip(_TASK_TRIM), None
