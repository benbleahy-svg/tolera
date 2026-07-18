"""Impressum footer helper (M5.9).

The de-DE catalog block adds the legal Impressum / company-register (HRB) footer
to customer-facing PDFs + quote emails (DACH-DELTA §Email/§8). These tests pin the
"render only what's present, never invent" contract (CLAUDE.md §5) and the de-DE
labels.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.impressum import (
    REGISTER_LABEL,
    UST_ID_LABEL,
    impressum_footer_html,
    impressum_lines,
)


@dataclass
class _Org:
    name: str | None = "Fechner Zerspanung GmbH"
    facility_address: str | None = "Musterstr. 1\n80331 München"
    commercial_register: str | None = "Amtsgericht München, HRB 123456"
    ust_id_nr: str | None = "DE123456789"


def test_full_identity_renders_all_lines() -> None:
    lines = impressum_lines(_Org())
    values = [line.value for line in lines]
    assert "Fechner Zerspanung GmbH" in values
    assert "Musterstr. 1\n80331 München" in values
    # register + VAT-ID carry their de-DE labels
    labelled = {line.label: line.value for line in lines if line.label}
    assert labelled[REGISTER_LABEL] == "Amtsgericht München, HRB 123456"
    assert labelled[UST_ID_LABEL] == "DE123456789"


def test_absent_register_is_omitted_never_invented() -> None:
    lines = impressum_lines(_Org(commercial_register=None))
    assert all(line.label != REGISTER_LABEL for line in lines)
    # USt-IdNr alone still yields a footer
    assert any(line.label == UST_ID_LABEL for line in lines)


def test_bare_org_without_register_or_vatid_suppresses_footer() -> None:
    # Neither a register nor a USt-IdNr → nothing legally worth an Impressum block.
    org = _Org(commercial_register=None, ust_id_nr=None)
    assert impressum_lines(org) == []
    assert impressum_footer_html(org) == ""


def test_footer_html_has_heading_and_escapes() -> None:
    org = _Org(name="A & B <GmbH>", commercial_register=None)
    html = impressum_footer_html(org)
    assert "Impressum" in html
    assert "A &amp; B &lt;GmbH&gt;" in html  # escaped, not a raw sink
    assert "USt-IdNr." in html
    # multiline address becomes <br>, never a literal newline collapse
    assert "<br>" in html
