"""Resolve a written owner part to Persons (FR-7).

Pure: works on the owner part, the meeting's Attendees and the People Roster only (NFR-9).
Unclear owners are never guessed: they become Ambiguous, Unknown or Unassigned.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from actiontrack.config import Person


class OwnerKind(StrEnum):
    PERSON = "person"  # one or more Persons (several for a shared item)
    TEAM = "team"  # every Attendee of the meeting
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"
    UNASSIGNED = "unassigned"


@dataclass(frozen=True)
class Resolution:
    """Who owns an item; `persons` are full names, `candidates` only for Ambiguous."""

    kind: OwnerKind
    persons: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()


# FR-7 step 1: names joined by `&`, `,` or `and` are separate Owners of one shared item.
_JOINERS = re.compile(r"\s*(?:&|,|\band\b)\s*", re.IGNORECASE)
_INITIAL = re.compile(r"^(?P<letter>\w)\.$")
_TEAM_WORDS = frozenset({"team", "everyone", "all"})  # FR-7 step 2
_UNASSIGNED_WORDS = frozenset({"tbd", "someone", "somebody", "anyone", "?"})  # FR-7 step 3


def resolve(owner_part: str | None, attendees: Sequence[str], roster: Sequence[Person] = ()) -> Resolution:
    """Resolve `owner_part` (as written) against the meeting's `attendees` (full names),
    then the People Roster for names no Attendee matches (FR-7 step 5; empty without a config).
    """
    names = [name.removeprefix("@") for name in _JOINERS.split(owner_part or "") if name.strip()]
    if not names:
        return Resolution(OwnerKind.UNASSIGNED)

    persons: list[str] = []
    candidates: list[str] = []
    unknown = False
    team = False
    for name in names:
        word = name.strip().casefold()
        if word in _TEAM_WORDS:
            team = True
            persons.extend(attendees)  # no Attendees: nobody, so the item ends up Unassigned
            continue
        if word in _UNASSIGNED_WORDS:
            continue
        matches = _matching(name, attendees) or _roster_matching(name, roster)
        if len(matches) == 1:
            persons.append(matches[0])
        elif matches:
            candidates.extend(matches)
        else:
            unknown = True

    # A shared item takes its least certain name's kind: Ambiguous wins over Unknown.
    if candidates:
        return Resolution(OwnerKind.AMBIGUOUS, candidates=_unique(candidates))
    if unknown:
        return Resolution(OwnerKind.UNKNOWN)
    if not persons:
        return Resolution(OwnerKind.UNASSIGNED)
    only_team = team and len(names) == 1
    return Resolution(OwnerKind.TEAM if only_team else OwnerKind.PERSON, persons=_unique(persons))


def _matching(name: str, people: Sequence[str]) -> list[str]:
    """`people` whose full name matches `name` (FR-7 step 4), ignoring case."""
    return [person for person in people if _names_match(name, person)]


def _roster_matching(name: str, roster: Sequence[Person]) -> list[str]:
    """Roster Persons whose full name matches `name` or who have it as an alias, ignoring case."""
    written = name.strip().casefold()
    return [
        person.name
        for person in roster
        if _names_match(name, person.name) or any(alias.casefold() == written for alias in person.aliases)
    ]


def _names_match(written: str, full_name: str) -> bool:
    """Full name, first name, or first name + surname initial (`Priya N.`)."""
    written_parts = written.casefold().split()
    full_parts = full_name.casefold().split()
    if written_parts == full_parts:
        return True
    if len(written_parts) == 1:
        return written_parts[0] == full_parts[0]
    if len(written_parts) == 2 and len(full_parts) >= 2 and (initial := _INITIAL.match(written_parts[1])):
        return written_parts[0] == full_parts[0] and full_parts[-1].startswith(initial["letter"])
    return False


def _unique(names: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))  # keeps first-seen order
