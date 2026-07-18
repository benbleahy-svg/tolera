"""build_mime CC/BCC/HTML/attachment behaviour (M5.5).

The composer extends the M3.5 outbound path: Cc is a visible header, Bcc is NOT
(envelope-only, except the Gmail raw path), an HTML body becomes a
``multipart/alternative``, and attachments (the quote PDF) are carried.
"""

from __future__ import annotations

from app.email_providers import OutboundAttachment, OutboundEmail, build_mime


def _msg(**kw: object) -> OutboundEmail:
    base: dict[str, object] = {"to": ["a@kunde.de"], "subject": "Betreff", "body_text": "Text"}
    base.update(kw)
    return OutboundEmail(**base)  # type: ignore[arg-type]


def test_cc_is_a_header_bcc_is_not() -> None:
    mime, _ = build_mime(
        from_address="jan@shop.de",
        from_name="Jan",
        message=_msg(cc=["cc@kunde.de"], bcc=["bcc@intern.de"]),
    )
    assert mime["Cc"] == "cc@kunde.de"
    assert mime["Bcc"] is None  # BCC never leaks into headers by default


def test_gmail_path_includes_bcc_header() -> None:
    mime, _ = build_mime(
        from_address="jan@shop.de",
        from_name="Jan",
        message=_msg(bcc=["bcc@intern.de"]),
        with_bcc_header=True,
    )
    assert mime["Bcc"] == "bcc@intern.de"


def test_all_recipients_dedupes_across_to_cc_bcc() -> None:
    msg = _msg(to=["a@x.de"], cc=["a@x.de", "b@x.de"], bcc=["c@x.de"])
    assert msg.all_recipients == ["a@x.de", "b@x.de", "c@x.de"]


def test_html_alternative_and_attachment_present() -> None:
    mime, _ = build_mime(
        from_address="jan@shop.de",
        from_name="Jan",
        message=_msg(
            body_html="<p>Hallo</p>",
            attachments=[OutboundAttachment("Angebot.pdf", "application/pdf", b"%PDF-1.4")],
        ),
    )
    assert mime.is_multipart()
    types = {part.get_content_type() for part in mime.walk()}
    assert "text/plain" in types
    assert "text/html" in types
    assert "application/pdf" in types
    # The attachment keeps its filename.
    assert any(p.get_filename() == "Angebot.pdf" for p in mime.walk())
