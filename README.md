# icloud-mcp

Personal MCP servers for iCloud — read your iCloud Mail and Calendar/Reminders from inside Claude Code using a single Apple **app-specific password**.

Two servers, zero third-party dependencies for the core logic:

| Server | Protocol | What it does |
|---|---|---|
| `icloud-mail` | IMAP | Read/search/move/delete mail. Custom server on pure `imaplib`. |
| `icloud-cal` | CalDAV | List calendars, list/create/delete events, list reminders. |

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- An Apple ID **app-specific password** — generate at https://appleid.apple.com → Sign-In and Security → App-Specific Passwords

## Install

```bash
git clone https://github.com/Ontry57/icloud-mcp.git
cd icloud-mcp && ./install.sh
```

The installer:
1. Prompts for iCloud email + app-specific password (or reads `ICLOUD_USER` / `ICLOUD_APP_PASSWORD` from env)
2. Merges both MCP entries into `~/.claude.json`
3. Smoke-tests IMAP and CalDAV connections

Restart Claude Code after install.

## Tools — icloud-mail

- `list_mailboxes(account_name)` — list all folders
- `list_emails_metadata(account_name, mailbox, seen, flagged, since, before, subject, from_address, page, page_size, order)` — list emails with filters
- `get_emails_content(account_name, email_ids)` — fetch full body
- `mark_emails_as_read(account_name, email_ids)` — mark as read
- `move_emails(account_name, email_ids, destination)` — move to folder
- `delete_emails(account_name, email_ids)` — move to Trash

## Tools — icloud-cal

- `list_calendars()` — names + URLs of all calendars
- `list_events(days_ahead=14, calendar?)` — upcoming events
- `create_event(calendar, summary, start, end, location?, description?)` — ISO-8601 dates
- `delete_event(url)` — url from list/create
- `list_reminders(calendar?, include_completed=false)` — VTODO items

## Why this exists

iCloud has no public API — but it speaks standard IMAP/CalDAV. An app-specific password is simpler than OAuth. This is minimal glue to expose those protocols as MCP tools.

## License

MIT.
