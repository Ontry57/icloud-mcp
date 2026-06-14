"""iCloud Mail IMAP MCP server (stdio).

Tools: list_mailboxes, list_emails_metadata, get_emails_content,
       mark_emails_as_read, move_emails, delete_emails.
Credentials from env: ICLOUD_USER, ICLOUD_APP_PASSWORD.
"""
import email
import email.header
import email.policy
import imaplib
import os
import ssl
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP


def _load_secrets():
    from pathlib import Path
    p = Path(__file__).parent.parent / "secrets.env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_secrets()

IMAP_HOST = os.environ.get("ICLOUD_IMAP_HOST", "imap.mail.me.com")
IMAP_PORT = int(os.environ.get("ICLOUD_IMAP_PORT", "993"))
USER = os.environ["ICLOUD_USER"]
PWD = os.environ["ICLOUD_APP_PASSWORD"]

mcp = FastMCP("icloud-mail")


def _connect() -> imaplib.IMAP4_SSL:
    ctx = ssl.create_default_context()
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx)
    imap.login(USER, PWD)
    return imap


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _search_uids(imap: imaplib.IMAP4_SSL, criteria: list[str]) -> list[str]:
    query = " ".join(criteria) if criteria else "ALL"
    status, data = imap.uid("SEARCH", None, query)
    # iCloud returns [None] for empty results — guard against it
    if status != "OK" or not data or data[0] is None or not data[0]:
        return []
    # Some servers prefix response with 'SEARCH' — filter non-numeric parts
    return [p.decode() for p in data[0].split() if p.isdigit()]


def _build_criteria(
    seen: Optional[bool],
    flagged: Optional[bool],
    answered: Optional[bool],
    since: Optional[str],
    before: Optional[str],
    subject: Optional[str],
    from_address: Optional[str],
    to_address: Optional[str],
) -> list[str]:
    c = []
    if seen is True:
        c.append("SEEN")
    elif seen is False:
        c.append("UNSEEN")
    if flagged is True:
        c.append("FLAGGED")
    elif flagged is False:
        c.append("UNFLAGGED")
    if answered is True:
        c.append("ANSWERED")
    elif answered is False:
        c.append("UNANSWERED")
    if since:
        dt = datetime.fromisoformat(since)
        c.append(f'SINCE "{dt.strftime("%d-%b-%Y")}"')
    if before:
        dt = datetime.fromisoformat(before)
        c.append(f'BEFORE "{dt.strftime("%d-%b-%Y")}"')
    if subject:
        c.append(f'SUBJECT "{subject}"')
    if from_address:
        c.append(f'FROM "{from_address}"')
    if to_address:
        c.append(f'TO "{to_address}"')
    return c or ["ALL"]


def _fetch_headers(imap: imaplib.IMAP4_SSL, uids: list[str]) -> list[dict]:
    if not uids:
        return []
    uid_set = ",".join(uids)
    status, data = imap.uid("FETCH", uid_set, "(FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
    if status != "OK":
        return []

    results = []
    i = 0
    while i < len(data):
        item = data[i]
        if not isinstance(item, tuple):
            i += 1
            continue
        meta, raw_headers = item
        meta_str = meta.decode() if isinstance(meta, bytes) else str(meta)

        # Extract UID
        uid = ""
        for part in meta_str.split():
            if part.isdigit() and "UID" in meta_str:
                idx = meta_str.upper().find("UID")
                after = meta_str[idx:].split()
                if len(after) >= 2 and after[1].isdigit():
                    uid = after[1]
                    break

        # Parse flags
        flags = []
        if "\\Seen" in meta_str:
            flags.append("\\Seen")
        if "\\Flagged" in meta_str:
            flags.append("\\Flagged")
        if "\\Answered" in meta_str:
            flags.append("\\Answered")

        # Parse date from INTERNALDATE
        date_str = ""
        if "INTERNALDATE" in meta_str:
            try:
                start = meta_str.index('INTERNALDATE "') + len('INTERNALDATE "')
                end = meta_str.index('"', start)
                date_str = meta_str[start:end]
            except ValueError:
                pass

        msg = email.message_from_bytes(raw_headers if isinstance(raw_headers, bytes) else raw_headers.encode())
        results.append({
            "email_id": uid,
            "subject": _decode_header(msg.get("Subject", "")),
            "sender": _decode_header(msg.get("From", "")),
            "recipients": _decode_header(msg.get("To", "")),
            "date": date_str or msg.get("Date", ""),
            "seen": "\\Seen" in flags,
            "flagged": "\\Flagged" in flags,
            "answered": "\\Answered" in flags,
        })
        i += 1

    return results


def _get_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
        # fallback to html
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="replace")
    return ""


# ── Tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def list_available_accounts() -> list[str]:
    """List configured email accounts."""
    return ["iCloud"]


@mcp.tool()
def list_mailboxes(account_name: str) -> list[str]:
    """List all mailboxes/folders in the account."""
    imap = _connect()
    try:
        status, data = imap.list()
        boxes = []
        for item in data:
            if isinstance(item, bytes):
                parts = item.decode().split('"/"')
                if parts:
                    name = parts[-1].strip().strip('"')
                    boxes.append(name)
        return sorted(boxes)
    finally:
        imap.logout()


@mcp.tool()
def list_emails_metadata(
    account_name: str,
    mailbox: str = "INBOX",
    seen: Optional[bool] = None,
    flagged: Optional[bool] = None,
    answered: Optional[bool] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
    subject: Optional[str] = None,
    from_address: Optional[str] = None,
    to_address: Optional[str] = None,
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List email metadata. Returns email_id, subject, sender, date, seen/flagged status."""
    imap = _connect()
    try:
        imap.select(f'"{mailbox}"', readonly=True)
        criteria = _build_criteria(seen, flagged, answered, since, before, subject, from_address, to_address)
        uids = _search_uids(imap, criteria)

        # Sort by UID (higher = newer)
        uids.sort(key=lambda u: int(u), reverse=(order == "desc"))
        total = len(uids)

        start = (page - 1) * page_size
        page_uids = uids[start:start + page_size]

        emails = _fetch_headers(imap, page_uids)
        return {"total": total, "page": page, "page_size": page_size, "emails": emails}
    finally:
        imap.logout()


@mcp.tool()
def get_emails_content(account_name: str, email_ids: list[str], mailbox: str = "INBOX") -> list[dict]:
    """Fetch full content (body) of emails by their IDs."""
    imap = _connect()
    try:
        imap.select(f'"{mailbox}"', readonly=True)
        results = []
        uid_set = ",".join(email_ids)
        status, data = imap.uid("FETCH", uid_set, "(FLAGS BODY[])")
        if status != "OK":
            return []

        i = 0
        while i < len(data):
            item = data[i]
            if not isinstance(item, tuple):
                i += 1
                continue
            meta, raw = item
            meta_str = meta.decode() if isinstance(meta, bytes) else str(meta)

            uid = ""
            idx = meta_str.upper().find("UID")
            if idx != -1:
                after = meta_str[idx:].split()
                if len(after) >= 2 and after[1].isdigit():
                    uid = after[1]

            msg = email.message_from_bytes(raw if isinstance(raw, bytes) else raw.encode())
            results.append({
                "email_id": uid,
                "subject": _decode_header(msg.get("Subject", "")),
                "sender": _decode_header(msg.get("From", "")),
                "recipients": _decode_header(msg.get("To", "")),
                "date": msg.get("Date", ""),
                "body": _get_body(msg),
            })
            i += 1
        return results
    finally:
        imap.logout()


@mcp.tool()
def mark_emails_as_read(account_name: str, email_ids: list[str], mailbox: str = "INBOX") -> dict:
    """Mark emails as read."""
    imap = _connect()
    try:
        imap.select(f'"{mailbox}"')
        uid_set = ",".join(email_ids)
        imap.uid("STORE", uid_set, "+FLAGS", "\\Seen")
        return {"ok": True, "marked": len(email_ids)}
    finally:
        imap.logout()


@mcp.tool()
def move_emails(account_name: str, email_ids: list[str], destination: str, mailbox: str = "INBOX") -> dict:
    """Move emails to another mailbox."""
    imap = _connect()
    try:
        imap.select(f'"{mailbox}"')
        uid_set = ",".join(email_ids)
        # Try MOVE (RFC 6851), fall back to COPY + delete
        if b"MOVE" in imap.capabilities:
            imap.uid("MOVE", uid_set, f'"{destination}"')
        else:
            imap.uid("COPY", uid_set, f'"{destination}"')
            imap.uid("STORE", uid_set, "+FLAGS", "\\Deleted")
            imap.expunge()
        return {"ok": True, "moved": len(email_ids)}
    finally:
        imap.logout()


@mcp.tool()
def delete_emails(account_name: str, email_ids: list[str], mailbox: str = "INBOX") -> dict:
    """Delete emails (move to Trash)."""
    imap = _connect()
    try:
        imap.select(f'"{mailbox}"')
        uid_set = ",".join(email_ids)
        # Try to find Trash folder
        _, folders = imap.list()
        trash = None
        for f in folders:
            if isinstance(f, bytes):
                name = f.decode().split('"/"')[-1].strip().strip('"')
                if name.lower() in ("trash", "deleted messages", "корзина"):
                    trash = name
                    break
        if trash:
            imap.uid("COPY", uid_set, f'"{trash}"')
        imap.uid("STORE", uid_set, "+FLAGS", "\\Deleted")
        imap.expunge()
        return {"ok": True, "deleted": len(email_ids)}
    finally:
        imap.logout()


if __name__ == "__main__":
    mcp.run()
