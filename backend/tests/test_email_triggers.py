"""Email trigger filter matching (FR-6.2 / FR-6.3): pure-function tests, no DB."""

from app.services.email_connectors import (
    ConnectorError,
    ImapConnector,
    MailAttachment,
    MailMessage,
    _fetch_bytes,
    _text_body,
    parse_message,
)
from app.services.email_poll import (
    attachment_allowed,
    message_matches,
)


def _msg(**kwargs):
    base = dict(
        uid="1",
        message_id="<abc@example.com>",
        sender="invoices@vendor.com",
        to="ap@company.com",
        subject="Invoice INV-1042 for October",
        date="",
        body_text="Please find attached. Amount due: 412.50",
        attachments=[MailAttachment(filename="inv.pdf", content=b"x", mime="application/pdf")],
    )
    base.update(kwargs)
    return MailMessage(**base)


class TestSenderMatching:
    def test_empty_rule_matches_anyone(self):
        ok, _ = message_matches({}, _msg())
        assert ok

    def test_exact_sender_case_insensitive(self):
        ok, _ = message_matches({"sender": "Invoices@Vendor.com"}, _msg())
        assert ok

    def test_exact_sender_rejects_other(self):
        ok, reason = message_matches({"sender": "other@x.com"}, _msg())
        assert not ok and "sender" in reason

    def test_domain_rule(self):
        ok, _ = message_matches({"sender": "@vendor.com"}, _msg())
        assert ok
        ok, _ = message_matches({"sender": "@other.com"}, _msg())
        assert not ok

    def test_regex_rule(self):
        ok, _ = message_matches({"sender": "/^invoices@.*\\.com$/"}, _msg())
        assert ok

    def test_invalid_regex_is_safe_no_match(self):
        ok, _ = message_matches({"sender": "/([/"}, _msg())
        assert not ok


class TestContentPatterns:
    def test_subject_pattern(self):
        ok, _ = message_matches({"subject_pattern": "inv-\\d+"}, _msg())
        assert ok
        ok, reason = message_matches({"subject_pattern": "purchase order"}, _msg())
        assert not ok and "subject" in reason

    def test_body_pattern(self):
        ok, _ = message_matches({"body_pattern": "amount due"}, _msg())
        assert ok
        ok, reason = message_matches({"body_pattern": "credit note"}, _msg())
        assert not ok and "body" in reason

    def test_invalid_pattern_is_safe_no_match(self):
        ok, _ = message_matches({"subject_pattern": "(["}, _msg())
        assert not ok


class TestAttachmentRules:
    def test_must_have_attachment(self):
        ok, reason = message_matches({"must_have_attachment": True}, _msg(attachments=[]))
        assert not ok and "attachment" in reason

    def test_allowed_types(self):
        ok, _ = attachment_allowed({"allowed_types": ["pdf"]}, "inv.PDF", 100)
        assert ok
        ok, reason = attachment_allowed({"allowed_types": ["pdf"]}, "photo.png", 100)
        assert not ok and "unsupported_type" in reason

    def test_max_size(self):
        ok, reason = attachment_allowed({"max_attachment_mb": 1}, "big.pdf", 2 * 1024 * 1024)
        assert not ok and "oversize" in reason
        ok, _ = attachment_allowed({"max_attachment_mb": 1}, "small.pdf", 100)
        assert ok

    def test_no_rules_allows_anything(self):
        ok, _ = attachment_allowed({}, "weird.xyz", 10**9)
        assert ok


class TestEnvelopeAttachments:
    """Dry runs fetch envelopes (no attachment bytes) but must still see
    filenames, or must_have_attachment filters match nothing."""

    def _connector(self, structure: bytes):
        conn = ImapConnector("h", 993, "u", "p")
        conn._uid = lambda *a: ("OK", [structure])  # type: ignore[method-assign]
        return conn

    def test_filenames_extracted_without_bytes(self):
        blob = (b'("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 12 1)'
                b'("APPLICATION" "PDF" ("NAME" "INV-1042.pdf") NIL NIL "BASE64" 3483)'
                b'"MIXED" ("ATTACHMENT" ("FILENAME" "INV-1042.pdf")) NIL NIL NIL')
        atts = self._connector(blob)._envelope_attachments("1")
        assert [a.filename for a in atts] == ["INV-1042.pdf"]
        assert atts[0].content == b""

    def test_no_attachments_gives_empty_list(self):
        blob = b'("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 12 1)'
        assert self._connector(blob)._envelope_attachments("1") == []

    def test_envelope_matching_sees_filenames(self):
        msg = _msg(attachments=[])
        msg.attachments = self._connector(
            b'("APPLICATION" "PDF" ("NAME" "INV-1042.pdf") NIL NIL "BASE64" 1)'
        )._envelope_attachments("1")
        ok, _ = message_matches(
            {"must_have_attachment": True,
             "subject_pattern": "INV-1042"}, msg)
        assert ok


class TestFetchResponseFlattening:
    """imaplib returns (descriptor, literal) tuples for FETCH bodies. Taking
    only bare bytes yields b")" and every email parses empty — nothing ever
    matches or ingests. Regression test with a realistic Gmail response."""

    RAW = (b"From: billing@acme.example\r\n"
           b"Subject: Invoice INV-1042\r\n"
           b"Message-ID: <abc@example.com>\r\n"
           b"Content-Type: text/plain\r\n"
           b"\r\nAmount due 2655.00")

    def test_tuple_form_keeps_literals_drops_framing(self):
        data = [(b'1576 (UID 1576 BODY[HEADER] {84}', self.RAW), b')']
        out = _fetch_bytes(data)
        assert out == self.RAW
        assert b"UID" not in out

    def test_envelope_end_to_end(self):
        header = (b"From: billing@acme.example\r\n"
                  b"Subject: Invoice INV-1042\r\n"
                  b"Message-ID: <abc@example.com>\r\n")
        text = (b"--===============123==\r\n"
                b'Content-Type: text/plain; charset="utf-8"\r\n'
                b"Content-Transfer-Encoding: 7bit\r\n\r\n"
                b"Amount due 2655.00\r\n"
                b"--===============123==\r\n"
                b"Content-Type: application/pdf\r\n"
                b"Content-Transfer-Encoding: base64\r\n\r\n"
                b"JVBERi0xLjQgZmFrZTQyAA==\r\n"
                b"--===============123==--\r\n")
        calls = iter([header, text])

        def fake_uid(*args):
            return ("OK", [(b"resp", next(calls)), b")"])

        conn = ImapConnector("h", 993, "u", "p")
        conn._folder = "INBOX"
        conn._uid = fake_uid  # type: ignore[method-assign]
        conn._envelope_attachments = lambda uid: [  # type: ignore[method-assign]
            MailAttachment(filename="INV-1042.pdf", content=b"", mime="")]
        msg = conn.fetch_envelope("1576")
        assert msg.subject == "Invoice INV-1042"
        assert "2655.00" in msg.body_text
        assert "JVBERi" not in msg.body_text  # base64 excluded
        ok, _ = message_matches({"subject_pattern": "INV-1042",
                                 "must_have_attachment": True}, msg)
        assert ok

    def test_text_body_single_part(self):
        assert _text_body(b"Hello world") == "Hello world"

    def test_text_body_skips_base64_parts(self):
        raw = (b"--b1\r\nContent-Type: text/plain\r\n\r\nnote here\r\n"
               b"--b1\r\nContent-Type: application/pdf\r\n"
               b"Content-Transfer-Encoding: base64\r\n\r\nQUJD\r\n"
               b"--b1--\r\n")
        assert _text_body(raw) == "note here"

    def test_full_end_to_end_with_attachment(self):
        from email.message import EmailMessage
        em = EmailMessage()
        em["From"] = "billing@acme.example"
        em["Subject"] = "Invoice INV-1042"
        em["Message-ID"] = "<abc@example.com>"
        em.set_content("Amount due 2655.00")
        em.add_attachment(b"%PDF-1.4 fake", maintype="application",
                          subtype="pdf", filename="INV-1042.pdf")
        full = em.as_bytes()
        conn = ImapConnector("h", 993, "u", "p")
        conn._folder = "INBOX"
        conn._uid = lambda *a: ("OK", [  # type: ignore[method-assign]
            (b'1576 (UID 1576 RFC822 {%d}' % len(full), full), b')'])
        msg = conn.fetch_full("1576")
        assert msg.subject == "Invoice INV-1042"
        assert [a.filename for a in msg.attachments] == ["INV-1042.pdf"]

    def test_full_fetch_uses_peek_never_marks_seen(self):
        seen_specs: list[str] = []

        def fake_uid(command, *args):
            seen_specs.append(" ".join([command, *args]))
            return ("OK", [])

        conn = ImapConnector("h", 993, "u", "p")
        conn._folder = "INBOX"
        conn._uid = fake_uid  # type: ignore[method-assign]
        try:
            conn.fetch_full("99")
        except ConnectorError:
            pass  # empty response is fine; we only assert the command shape
        assert seen_specs and all("PEEK" in s for s in seen_specs), seen_specs
        assert not any("RFC822" in s and "PEEK" not in s for s in seen_specs)
