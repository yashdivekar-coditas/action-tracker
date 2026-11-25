# actiontrack — Overview for Everyone

A plain-language guide to what actiontrack does, who it is for and how it keeps people's inboxes safe. Engineers should read [`technical_details.md`](technical_details.md).

## The problem

Our meeting notes are saved as text files. Each meeting ends with a list of action items, such as "Priya to send the revised quote by Friday", but then:

- the items get lost across dozens of files,
- nobody can easily see what is late or who owes what,
- follow-up emails are written late or not at all.

## What actiontrack does

actiontrack is a small command-line tool for whoever runs the team's meetings. It:

1. **Reads** every meeting note in a folder and picks out the action items: who owns each one, what the task is, and when it is due.
2. **Keeps a list** of all items and shows which are open, done or overdue. The list can be filtered by person or date.
3. **Lets you tick items off** when they're finished.
4. **Writes follow-up emails**, one per person, listing their open and overdue items, and saves them as **drafts in Gmail**. A human reads each draft and decides whether to send it.

## A typical week

```
Meetings happen → notes saved to the folder
        ↓
actiontrack ingest      "Read the new notes"
        ↓
actiontrack list        "What's open? What's late?"
        ↓
actiontrack followup    "Draft reminder emails"
        ↓
You open Gmail → Drafts, review, edit, and send yourself
        ↓
actiontrack done 12     "Mark item 12 finished"
```

## What it understands

Real notes are messy, and actiontrack is built for that:

| Situation | What happens |
|---|---|
| "by Friday", "tomorrow", "end of month", "mid-October" | Turned into a real date, counted from the day of the meeting. |
| The same item repeated in several meetings | Kept as **one** item that remembers every meeting it came up in. The most recent deadline is used. |
| An item ticked off in a later meeting | Marked done automatically. |
| Two people with the same first name (Priya Nair and Priya Shah) | Uses the meeting's attendee list to work out who is meant. If both were in the room and the note only says "Priya", the item is flagged as **unclear** and left out of emails rather than guessed. |
| "Priya N." | Matched to Priya Nair. |
| "Anita & Rahul to…" | One shared item for both. |
| "Team to…" | Given to everyone who attended that meeting. |
| "TBD to…", "Someone to…", or no name | Kept as **unassigned** and reported so someone can claim it. |
| A quoted suggestion, e.g. a forwarded wish from another team | Ignored, because it wasn't agreed in the meeting. |
| A broken note (empty file, image saved as a note, no date) | Skipped and named in a report. Nothing crashes, and every other note is still read. |

## Safety and privacy

- **It never sends email.** It only creates drafts. A person always reviews and sends.
- People it can't identify for sure are **never** emailed.
- Your Gmail password and login are not stored by actiontrack. They stay with the Gmail connector you set up once.
- Everything else stays on your computer, in one local file.

## What it does not do (yet)

- Edit, reassign or delete items. Instead, correct the meeting note and read it again.
- Read notes from Google Drive, Notion or other online tools. It reads local files only.
- Send emails, schedule reminders or use rich (HTML) formatting in emails.

## Things to keep in mind

- **Keep the people list up to date.** Follow-ups only go to people listed with an email address in the tool's settings file.
- **Write action items clearly.** "Name to do something by date" works best. Unclear owners are flagged, not guessed.
- **"Next Tuesday" means Tuesday of the following week.** Plain "by Tuesday" means the very next one.
- **Editing an old note** after it was read can leave an outdated copy of the item open. Mark it done to clear it.
- **Each follow-up run creates a new draft.** Delete any extra drafts you don't need. The tool warns if it drafted for someone in the last 24 hours.

## Glossary

The key words used here (Owner, Action Item, Overdue, Follow-up Draft, …) are defined in [`../GLOSSARY.md`](../GLOSSARY.md).
