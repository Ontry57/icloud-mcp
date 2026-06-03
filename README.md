# icloud-mcp

Personal MCP servers for iCloud — read your iCloud Mail and Calendar/Reminders from inside Claude Code (or any MCP client) using a single Apple **app-specific password**.

Two servers:

| Server | Protocol | What it does |
|---|---|---|
| `icloud-mail` | IMAP + SMTP | Read/search/send mail, download attachments. Uses upstream [`mcp-email-server`](https://github.com/ai-zerolab/mcp-email-server). |
| `icloud-cal` (this repo) | CalDAV | List calendars, list/create/delete events, list reminders (VTODO). |

## Prerequisites

- macOS (Linux works too, just change the cert path)
- [uv](https://github.com/astral-sh/uv) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- An Apple ID **app-specific password** — generate at https://appleid.apple.com → Sign-In and Security → App-Specific Passwords

## Install

```bash
git clone https://github.com/Ontry57/icloud-mcp.git ~/.config/icloud-mcp
```

Then add the MCP entries to `~/.claude.json` under `mcpServers` (or the equivalent for your MCP client). See [`claude.example.json`](claude.example.json) for the full block — copy it in and replace the placeholder credentials.

Restart Claude Code. You should now have tools like `mcp__icloud-cal__list_events`.

## Configuration

Both servers read credentials from env vars set in the MCP config:

| Var | Used by | Example |
|---|---|---|
| `ICLOUD_USER` | icloud-cal | `you@me.com` |
| `ICLOUD_APP_PASSWORD` | icloud-cal | `abcd-efgh-ijkl-mnop` |
| `MCP_EMAIL_SERVER_IMAP_USER_NAME` | icloud-mail | `you@me.com` |
| `MCP_EMAIL_SERVER_IMAP_PASSWORD` | icloud-mail | same app-password |
| `SSL_CERT_FILE` | both | `/etc/ssl/cert.pem` (macOS) |

The `SSL_CERT_FILE` var is needed because the Python runtime that `uv` spins up doesn't trust the system keychain by default — without it, TLS handshake to iCloud fails with `CERTIFICATE_VERIFY_FAILED`.

## Tools (icloud-cal)

- `list_calendars()` — names + URLs of all calendars
- `list_events(days_ahead=14, calendar?)` — upcoming events, optionally filtered
- `create_event(calendar, summary, start, end, location?, description?)` — start/end are ISO-8601
- `delete_event(url)` — url returned from list/create
- `list_reminders(calendar?, include_completed=false)` — VTODO items

## Why this exists

iCloud has no public API for Mail or Calendar — but it speaks standard IMAP/SMTP/CalDAV. An app-specific password is much simpler than Google OAuth (no Cloud Console, no consent screen, no token refresh).

This repo is the minimal glue to expose those protocols as MCP tools.

## License

MIT.
