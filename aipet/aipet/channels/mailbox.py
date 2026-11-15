"""The pet's email.

Two backends behind one interface:
  LocalMailbox    - JSON files under <home>/mail. Works offline; the owner drops
                    letters in with `aipet mail send` and reads replies with
                    `aipet mail outbox`.
  ImapSmtpMailbox - a real account (any IMAP/SMTP provider, e.g. a Gmail app
                    password or a dedicated address from your mail host).
"""
from __future__ import annotations

import email
import email.utils
import imaplib
import smtplib
import uuid
from dataclasses import asdict, dataclass, field
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from ..config import Config
from ..util import iso, read_json, write_json


@dataclass
class Message:
    id: str
    sender: str
    to: str
    subject: str
    body: str
    date: str = field(default_factory=iso)


def _addr(s: str) -> str:
    return (email.utils.parseaddr(s)[1] or s).strip().lower()


def _text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition", "").startswith("attachment"):
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


class Mailbox(Protocol):
    address: str

    def fetch_unread(self, limit: int = 10) -> list[Message]: ...
    def mark_read(self, msg_id: str) -> None: ...
    def send(self, to: str, subject: str, body: str) -> None: ...


class LocalMailbox:
    def __init__(self, root: Path, address: str = "pet@localhost"):
        self.root = root
        self.address = address
        (root / "inbox").mkdir(parents=True, exist_ok=True)
        (root / "sent").mkdir(parents=True, exist_ok=True)

    def deliver(self, sender: str, subject: str, body: str) -> Message:
        """Put a message in the pet's inbox (what the owner's CLI does)."""
        m = Message(id=f"m_{uuid.uuid4().hex[:10]}", sender=_addr(sender), to=self.address, subject=subject, body=body)
        write_json(self.root / "inbox" / f"{m.id}.json", {**asdict(m), "read": False})
        return m

    def fetch_unread(self, limit: int = 10) -> list[Message]:
        out = []
        for p in sorted((self.root / "inbox").glob("*.json")):
            d = read_json(p)
            if d and not d.get("read"):
                d.pop("read", None)
                out.append(Message(**d))
            if len(out) >= limit:
                break
        return out

    def mark_read(self, msg_id: str) -> None:
        p = self.root / "inbox" / f"{msg_id}.json"
        d = read_json(p)
        if d:
            d["read"] = True
            write_json(p, d)

    def send(self, to: str, subject: str, body: str) -> None:
        m = Message(id=f"s_{uuid.uuid4().hex[:10]}", sender=self.address, to=_addr(to), subject=subject, body=body)
        write_json(self.root / "sent" / f"{m.id}.json", asdict(m))

    def sent(self) -> list[Message]:
        return [Message(**read_json(p)) for p in sorted((self.root / "sent").glob("*.json"))]


class ImapSmtpMailbox:
    def __init__(self, config: Config):
        self.config = config
        self.address = config.email_address

    def _imap(self) -> imaplib.IMAP4:
        c = self.config
        box = imaplib.IMAP4_SSL(c.imap_host, c.imap_port) if c.imap_port == 993 else imaplib.IMAP4(c.imap_host, c.imap_port)
        box.login(c.email_user or c.email_address, c.email_password)
        return box

    def fetch_unread(self, limit: int = 10) -> list[Message]:
        box = self._imap()
        try:
            box.select("INBOX")
            status, data = box.search(None, "UNSEEN")
            ids = data[0].split()[:limit] if status == "OK" else []
            out = []
            for i in ids:
                status, parts = box.fetch(i, "(BODY.PEEK[])")
                if status != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                msg = email.message_from_bytes(parts[0][1])
                subject = str(make_header(decode_header(msg.get("Subject", "") or "")))
                out.append(
                    Message(
                        id=i.decode(),
                        sender=_addr(msg.get("From", "")),
                        to=_addr(msg.get("To", "")),
                        subject=subject,
                        body=_text_body(msg).strip(),
                        date=msg.get("Date", iso()),
                    )
                )
            return out
        finally:
            try:
                box.logout()
            except Exception:  # noqa: BLE001
                pass

    def mark_read(self, msg_id: str) -> None:
        box = self._imap()
        try:
            box.select("INBOX")
            box.store(msg_id.encode(), "+FLAGS", "\\Seen")
        finally:
            box.logout()

    def send(self, to: str, subject: str, body: str) -> None:
        c = self.config
        msg = EmailMessage()
        msg["From"] = c.email_address
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if c.smtp_port == 465:
            with smtplib.SMTP_SSL(c.smtp_host, c.smtp_port, timeout=30) as s:
                s.login(c.email_user or c.email_address, c.email_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(c.smtp_host, c.smtp_port, timeout=30) as s:
                s.ehlo()
                s.starttls()
                s.login(c.email_user or c.email_address, c.email_password)
                s.send_message(msg)


def make_mailbox(config: Config) -> Mailbox:
    if config.has_real_mail:
        return ImapSmtpMailbox(config)
    return LocalMailbox(config.mail_dir, config.pet_email)
