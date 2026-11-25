# Actiontrack

Turns a folder of meeting notes into tracked action items and drafts follow-up emails to their owners for a human to review and send.

## People

**Person**:
Someone listed in the People Roster with a full name and an email address; the only kind of Owner a follow-up can go to.
_Avoid_: User, member, contact

**People Roster**:
The maintained list of every Person, with their full name, email and any aliases.
_Avoid_: Directory, address book

**Attendee**:
A Person named in a meeting note's attendee list.

**Owner**:
The Person responsible for an action item, resolved from the name written in the note against that meeting's Attendees.
_Avoid_: Assignee, responsible

**Ambiguous Owner**:
An owner name that still matches more than one Attendee after resolution (e.g. a bare "Priya" when Priya Nair and Priya Shah both attended); the item is kept and reported but gets no follow-up.

**Unknown Owner**:
A written owner name that matches no Attendee and no Person in the People Roster; the item keeps the name as written, is reported, and gets no follow-up.

**Unassigned**:
An action item whose note gives no usable owner ("TBD", "Someone", or no name at all); it is tracked but gets no follow-up.

**Team Item**:
An action item addressed to "Team", owned by every Attendee of that meeting.

## Notes

**Meeting Note**:
One markdown file recording a single meeting: its Meeting Date, Attendees, discussion and action items.
_Avoid_: Minutes, doc, file

**Meeting Date**:
The date the meeting took place, read from the note's header; every relative Due Phrase in the note is resolved against it.

**Malformed Note**:
A Meeting Note that is not readable text, is empty, or has no resolvable Meeting Date; it is skipped and reported, never partly ingested.
_Avoid_: Invalid note, broken file

**Decoy**:
Text that looks like an action item but was not agreed, such as a quoted line or a line in a code block; it is never ingested.

## Action items

**Action Item**:
A single commitment agreed in a Meeting Note: a task, its Owner(s) and optionally a Due Date.
_Avoid_: Task, todo, action

**Source**:
A Meeting Note an Action Item appears in; an item repeated across meetings is one Action Item with many Sources, and its latest Source sets its Due Date.

**Duplicate**:
A repeat of an Action Item in another Meeting Note: same Owner(s) and the same task wording once case, punctuation, articles and the Due Phrase are ignored.
_Avoid_: Copy, repeat

**Open** / **Done** / **Overdue**:
An Action Item is Open until it is marked Done, either by a checked box in any Source or by a person; Done is final and a later unchecked mention does not reopen it. An Open item past its Due Date is Overdue.

**Due Phrase**:
The deadline as written in the note, without its leading "by" or "due" ("Friday" from "by Friday", "mid-October"); always kept, even when it cannot be resolved.

**Due Date**:
The calendar date a Due Phrase resolves to, relative to the Meeting Date; absent when the phrase is missing or unresolvable.
_Avoid_: Deadline

**Unresolved Due Phrase**:
A Due Phrase that matches no Due Date rule; the item keeps the phrase as written, has no Due Date, and the phrase is listed in the ingest report.

## Follow-ups

**Follow-up Draft**:
One Gmail draft per Owner listing their open and overdue items; it is never sent by actiontrack.
_Avoid_: Reminder, email, notification
