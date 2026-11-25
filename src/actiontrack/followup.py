"""Compose a Follow-up Draft's email from a Person's Open items (FR-16).

Pure: no I/O. The caller picks the items (the same query `list` uses), so the email
can never disagree with `list --owner <Person>`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from actiontrack.config import Person
from actiontrack.store import StoredItem


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


def compose(person: Person, items: Sequence[StoredItem], sender: str) -> Email:
    """The email for `person` listing `items` (all Open, in `list` order, Overdue first) signed by `sender`."""
    overdue = [item for item in items if item.days_overdue is not None]
    open_ = [item for item in items if item.days_overdue is None]
    lines = [f"Hi {person.name.split()[0]},", "", "Here are your open action items from recent meetings:"]
    for heading, section in (("OVERDUE", overdue), ("OPEN", open_)):
        if section:
            lines += ["", heading, *(line for item in section for line in _item_lines(item))]
    lines += ["", "Thanks,", sender]
    return Email(
        to=person.email,
        subject=f"Action items from recent meetings — {len(items)} open, {len(overdue)} overdue",
        body="\n".join(lines) + "\n",
    )


def _item_lines(item: StoredItem) -> list[str]:
    due = f"due {item.due_date or item.due_phrase}" if item.due_date or item.due_phrase else "no due date"
    if item.days_overdue is not None:
        days = item.days_overdue
        due += f" ({days} day{'' if days == 1 else 's'} overdue)"
    sources = "; ".join(f"{source.title}, {source.meeting_date}" for source in item.sources)
    return [f"- {item.task} — {due}", f"  from: {sources}"]
