from __future__ import annotations

import email
import imaplib
import os
from email.header import decode_header as _decode_header_raw


def _decode_str(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    parts = _decode_header_raw(value)
    out = []
    for fragment, charset in parts:
        if isinstance(fragment, bytes):
            out.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(fragment)
    return "".join(out)


def _get_body(msg: email.message.Message) -> str:
    """Extract plain-text body from a message, up to 500 chars."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")[:500]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")[:500]
    return ""


class EmailSource:
    """Fetch real emails from 163 (or any IMAP server) using IMAP + auth code."""

    def __init__(
        self,
        user: str | None = None,
        password: str | None = None,
        host: str = "imap.163.com",
        port: int = 993,
        max_messages: int = 10,
    ) -> None:
        self.user = user or os.environ.get("EMAIL_USER", "")
        self.password = password or os.environ.get("EMAIL_PASSWORD", "")
        self.host = host
        self.port = port
        self.max_messages = max_messages

    def fetch(self) -> str:
        if not self.user or not self.password:
            return "(email source not configured — set EMAIL_USER and EMAIL_PASSWORD in .env)"

        with imaplib.IMAP4_SSL(self.host, self.port) as mail:
            mail.login(self.user, self.password)
            mail.select("INBOX", readonly=True)
            _, data = mail.search(None, "ALL")
            all_ids = data[0].split()
            recent_ids = all_ids[-self.max_messages:]  # latest N

            lines: list[str] = []
            for i, mid in enumerate(reversed(recent_ids), 1):
                _, raw = mail.fetch(mid, "(RFC822)")
                msg = email.message_from_bytes(raw[0][1])
                subject = _decode_str(msg.get("Subject"))
                from_ = _decode_str(msg.get("From"))
                date = msg.get("Date", "")
                body = _get_body(msg).strip().replace("\n", " ")[:200]
                lines.append(
                    f"({i}) From: {from_}\n"
                    f"    Subject: {subject}\n"
                    f"    Date: {date}\n"
                    f"    Body: {body}"
                )

        return "Inbox (" + str(len(lines)) + " messages):\n\n" + "\n\n".join(lines)
