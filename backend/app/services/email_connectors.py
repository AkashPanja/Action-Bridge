"""Mailbox connectors (FR-6.4).

EmailConnector is the interface every mailbox type implements. IMAP (password /
app-password) is fully implemented. Microsoft Graph and Gmail API share the
OAuth credential plumbing and raise a clear error until OAuth is configured —
their method shapes are fixed now so adding them needs no interface changes.
"""

import email
import email.policy
import imaplib
import re
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.message import EmailMessage


@dataclass
class MailAttachment:
    filename: str
    content: bytes
    mime: str


@dataclass
class MailMessage:
    uid: str
    message_id: str
    sender: str
    to: str
    subject: str
    date: str
    body_text: str
    attachments: list[MailAttachment] = field(default_factory=list)


class ConnectorError(RuntimeError):
    """Connection/auth failure (transient-aware via .transient)."""

    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class EmailConnector(ABC):
    """One mailbox connection. All blocking I/O — callers run it in a thread."""

    @abstractmethod
    def connect(self) -> None:
        """Authenticate. Raises ConnectorError."""

    @abstractmethod
    def list_uids(self, folder: str, since_uid: int = 0, since_date: str | None = None,
                  readonly: bool = True) -> list[str]:
        """UIDs to consider, oldest first. since_date is an IMAP date string
        (e.g. '01-Oct-2026') used only when the trigger was never synced."""

    @abstractmethod
    def fetch_envelope(self, uid: str) -> MailMessage:
        """Headers + body text, no attachment bytes (for dry runs)."""

    @abstractmethod
    def fetch_full(self, uid: str) -> MailMessage:
        """Headers + body + attachment bytes."""

    @abstractmethod
    def mark_read(self, uid: str) -> None:
        ...

    @abstractmethod
    def move(self, uid: str, folder: str) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


def _fetch_bytes(data: list) -> bytes:
    """Flatten an imaplib FETCH response to message bytes.

    imaplib mixes bare bytes with (descriptor, literal, ...) tuples — the
    literals (tuple[1:]) are the actual content, the descriptor and lone
    b")" closers are protocol framing and must be excluded.
    """
    out: list[bytes] = []
    for part in data:
        if isinstance(part, tuple):
            out.extend(b for b in part[1:] if isinstance(b, bytes))
        elif isinstance(part, bytes) and part.strip() != b")":
            out.append(part)
    return b"".join(out)


def _text_body(raw: bytes) -> str:
    """Best-effort visible text from a BODY[TEXT] literal (no download of
    attachments involved — this only filters what the server already sent).

    Single-part mail returns as-is. Multipart mail without its outer
    Content-Type header looks like bare boundary delimiters: keep text/plain
    sections that are not base64, drop encoded attachment chunks so body
    filters match human text, not base64 noise.
    """
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("--"):
        return text.strip()[:20000]
    delim = lines[0].strip()
    out: list[str] = []
    buf: list[str] = []
    part_headers: list[str] = []
    in_headers = True  # part headers follow the opening delimiter directly
    keep = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        if keep and body:
            out.append(body)

    for line in lines[1:]:
        s = line.strip()
        if s == delim or s == delim + "--":
            flush()
            buf, part_headers, keep = [], [], False
            if s == delim + "--":
                in_headers = False
                break
            in_headers = True
            continue
        if in_headers:
            if s == "":
                h = "\n".join(part_headers).lower()
                keep = "text/plain" in h and "base64" not in h
                in_headers = False
            else:
                part_headers.append(s)
        elif keep:
            buf.append(line)
    else:
        flush()
    return "\n\n".join(out)[:20000]


def parse_message(raw: bytes, uid: str) -> MailMessage:
    """Parse a raw RFC822 message into MailMessage (attachments included)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    message_id = (msg.get("Message-ID") or "").strip()
    sender = str(msg.get("From", ""))
    to = str(msg.get("To", ""))
    subject = str(msg.get("Subject", ""))
    date = str(msg.get("Date", ""))

    body_parts: list[str] = []
    attachments: list[MailAttachment] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = (part.get_content_disposition() or "").lower()
            filename = part.get_filename()
            if disp == "attachment" or filename:
                try:
                    content = part.get_content()
                except Exception:
                    continue
                if isinstance(content, str):
                    content = content.encode("utf-8", "replace")
                if not isinstance(content, (bytes, bytearray)) or not content:
                    continue
                attachments.append(MailAttachment(
                    filename=filename or "attachment.bin",
                    content=bytes(content),
                    mime=part.get_content_type(),
                ))
            elif part.get_content_type() == "text/plain" and disp != "inline":
                try:
                    text = part.get_content()
                    if isinstance(text, str) and text.strip():
                        body_parts.append(text.strip())
                except Exception:
                    continue
    else:
        try:
            text = msg.get_content()
            if isinstance(text, str):
                body_parts.append(text.strip())
        except Exception:
            pass

    return MailMessage(
        uid=uid,
        message_id=message_id,
        sender=sender,
        to=to,
        subject=subject,
        date=date,
        body_text="\n\n".join(body_parts)[:20000],
        attachments=attachments,
    )


class ImapConnector(EmailConnector):
    """IMAP over SSL with password / app password."""

    def __init__(self, host: str, port: int, username: str, password: str, timeout: int = 30):
        self.host = host
        self.port = port or 993
        self.username = username
        self.password = password
        self.timeout = timeout
        self._conn: imaplib.IMAP4_SSL | None = None
        self._folder: str | None = None

    def connect(self) -> None:
        try:
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx, timeout=self.timeout)
            conn.login(self.username, self.password)
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ConnectorError(f"IMAP login failed for {self.username}@{self.host}: {exc}") from exc
        self._conn = conn

    def _select(self, folder: str, readonly: bool) -> None:
        assert self._conn is not None, "not connected"
        if self._folder == folder:
            return
        typ, _ = self._conn.select(self._quote(folder), readonly=readonly)
        if typ != "OK":
            raise ConnectorError(f"Cannot open folder {folder!r}")
        self._folder = folder

    @staticmethod
    def _quote(folder: str) -> str:
        return f'"{folder.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'

    def _uid(self, command: str, *args) -> tuple[str, list]:
        assert self._conn is not None, "not connected"
        try:
            typ, data = self._conn.uid(command, *args)
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ConnectorError(f"IMAP command failed: {exc}", transient=True) from exc
        if typ != "OK":
            raise ConnectorError(f"IMAP command failed: {command}", transient=True)
        return typ, data or []

    def list_uids(self, folder: str, since_uid: int = 0, since_date: str | None = None,
                  readonly: bool = True) -> list[str]:
        self._select(folder, readonly=readonly)
        if since_uid > 0:
            _, data = self._uid("SEARCH", f"UID {since_uid + 1}:*")
        elif since_date:
            _, data = self._uid("SEARCH", f"SINCE {since_date}")
        else:
            _, data = self._uid("SEARCH", "ALL")
        out: list[str] = []
        for chunk in data:
            if isinstance(chunk, bytes):
                out.extend(chunk.decode("ascii", "ignore").split())
        return [u for u in out if u.isdigit()]

    def fetch_envelope(self, uid: str) -> MailMessage:
        if self._folder is None:
            raise ConnectorError("No folder selected")
        # HEADER and TEXT are fetched separately: servers may return multiple
        # body parts in any order, and concatenating them breaks parsing.
        _, hdata = self._uid(
            "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS"
            " (FROM TO SUBJECT DATE MESSAGE-ID)])")
        _, tdata = self._uid("FETCH", uid, "(BODY.PEEK[TEXT])")
        head_raw = _fetch_bytes(hdata)
        text_raw = _fetch_bytes(tdata)
        if not head_raw and not text_raw:
            raise ConnectorError(f"Empty response for UID {uid}", transient=True)
        msg = parse_message(head_raw, uid)
        msg.body_text = _text_body(text_raw)
        # Envelopes skip attachment bytes, but dry-run matching needs the
        # filenames (must_have_attachment / allowed_types). BODYSTRUCTURE
        # gives names + types with no content download.
        msg.attachments = self._envelope_attachments(uid)
        return msg

    def _envelope_attachments(self, uid: str) -> list["MailAttachment"]:
        try:
            _, data = self._uid("FETCH", uid, "(BODYSTRUCTURE)")
        except ConnectorError:
            return []
        blob = _fetch_bytes(data).decode("utf-8", "ignore")
        names = re.findall(r'"(?:FILENAME|NAME)"\s+"([^"]+)"', blob, re.IGNORECASE)
        out: list[MailAttachment] = []
        seen: set[str] = set()
        for name in names:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                out.append(MailAttachment(filename=name, content=b"", mime=""))
        return out

    def fetch_full(self, uid: str) -> MailMessage:
        if self._folder is None:
            raise ConnectorError("No folder selected")
        # PEEK: full content without implicitly setting \Seen — read state is
        # governed solely by after_action.mark_read.
        _, data = self._uid("FETCH", uid, "(BODY.PEEK[])")
        raw = _fetch_bytes(data)
        if not raw:
            raise ConnectorError(f"Empty response for UID {uid}", transient=True)
        return parse_message(raw, uid)

    def mark_read(self, uid: str) -> None:
        self._uid("STORE", uid, "+FLAGS", "(\\Seen)")

    def move(self, uid: str, folder: str) -> None:
        _, data = self._uid("COPY", uid, self._quote(folder))
        if not data:
            raise ConnectorError(f"Move target rejected: {folder!r}")
        self._uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        assert self._conn is not None
        try:
            self._conn.expunge()
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ConnectorError(f"Expunge failed: {exc}", transient=True) from exc

    def close(self) -> None:
        conn, self._conn = self._conn, None
        self._folder = None
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                pass


class GraphConnector(EmailConnector):
    """Microsoft Graph (Outlook). Requires OAuth — see FR-2.7."""

    def __init__(self, *args, **kwargs):
        raise ConnectorError(
            "Outlook via Microsoft Graph needs OAuth (Azure app registration). "
            "Use an IMAP basic credential until OAuth is configured."
        )

    def connect(self) -> None: ...
    def list_uids(self, folder="", since_uid=0, since_date=None): ...
    def fetch_envelope(self, uid): ...
    def fetch_full(self, uid): ...
    def mark_read(self, uid): ...
    def move(self, uid, folder): ...
    def close(self) -> None: ...


class GmailApiConnector(EmailConnector):
    """Gmail API. Requires OAuth — see FR-2.7."""

    def __init__(self, *args, **kwargs):
        raise ConnectorError(
            "Gmail API needs OAuth (Google Cloud consent). "
            "Use an IMAP basic credential with an app password until then."
        )

    def connect(self) -> None: ...
    def list_uids(self, folder="", since_uid=0, since_date=None): ...
    def fetch_envelope(self, uid): ...
    def fetch_full(self, uid): ...
    def mark_read(self, uid): ...
    def move(self, uid, folder): ...
    def close(self) -> None: ...


def build_connector(kind: str, **kwargs) -> EmailConnector:
    kinds = {"imap": ImapConnector, "graph": GraphConnector, "gmail_api": GmailApiConnector}
    if kind not in kinds:
        raise ConnectorError(f"Unknown connector kind: {kind}")
    return kinds[kind](**kwargs)
