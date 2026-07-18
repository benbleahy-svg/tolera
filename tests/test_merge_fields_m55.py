"""Merge-field rendering (M5.5) — the pure ``%%FIELD%%`` substitution.

Spec ``#settings`` Email Templates: the composer body carries ``%%QUOTE_NUMBER%%``
etc. These tests pin the *pure* renderer (no DB); the DB-backed value builder is
exercised in the composer send test.
"""

from __future__ import annotations

from app.merge_fields import MERGE_FIELDS, render_merge


def test_replaces_known_tokens() -> None:
    out = render_merge(
        "Angebot %%QUOTE_NUMBER%% für %%CUSTOMER_FIRST_NAME%%",
        {"QUOTE_NUMBER": "Q-1042", "CUSTOMER_FIRST_NAME": "Chris"},
    )
    assert out == "Angebot Q-1042 für Chris"


def test_missing_value_blanks_the_token_never_leaves_percent() -> None:
    # A known token with no value (e.g. FACILITY_PHONE, no field yet) → empty,
    # never the literal %%…%% and never invented (never-hallucinate invariant).
    out = render_merge("Tel: %%FACILITY_PHONE%%.", {})
    assert out == "Tel: ."
    assert "%%" not in out


def test_unknown_token_is_blanked_not_left_verbatim() -> None:
    out = render_merge("x %%NOT_A_FIELD%% y", {"NOT_A_FIELD": "should-ignore"})
    # NOT_A_FIELD is not in the catalog → blanked for customer-facing safety.
    assert out == "x  y"


def test_link_token_substituted_verbatim() -> None:
    link = "http://localhost:5173/q/eyJhbGciOi.abc.def"
    out = render_merge("Öffnen: %%QUOTE_LINK%%", {"QUOTE_LINK": link})
    assert out == f"Öffnen: {link}"


def test_repeated_token_all_replaced() -> None:
    out = render_merge("%%FACILITY_NAME%% — %%FACILITY_NAME%%", {"FACILITY_NAME": "Fechner"})
    assert out == "Fechner — Fechner"


def test_no_tokens_passthrough() -> None:
    assert render_merge("Plain text, kein Feld.", {"QUOTE_NUMBER": "X"}) == "Plain text, kein Feld."


def test_escape_html_escapes_values_not_template_markup() -> None:
    # A customer-supplied part number carrying markup must be neutralised when
    # merged into an HTML body — but the template's own markup stays intact.
    out = render_merge(
        "<p>Teile: %%PART_NUMBERS%%</p>",
        {"PART_NUMBERS": '<img src=x onerror="alert(1)">'},
        escape_html=True,
    )
    assert "<img" not in out
    assert "&lt;img" in out
    assert "<p>" in out  # the estimator-authored markup is preserved


def test_no_escape_leaves_value_verbatim() -> None:
    # Subject is plain text — no HTML escaping.
    out = render_merge("Angebot für %%CUSTOMER_FIRST_NAME%%", {"CUSTOMER_FIRST_NAME": "A&B"})
    assert out == "Angebot für A&B"


def test_catalog_covers_the_spec_set() -> None:
    expected = {
        "QUOTE_NUMBER",
        "QUOTE_LINK",
        "RFQ_NUMBER",
        "PART_NUMBERS",
        "CUSTOMER_FIRST_NAME",
        "CUSTOMER_LAST_NAME",
        "ESTIMATOR_FIRST_NAME",
        "ESTIMATOR_LAST_NAME",
        "ESTIMATOR_EMAIL",
        "SALESPERSON_FIRST_NAME",
        "SALESPERSON_LAST_NAME",
        "SALESPERSON_EMAIL",
        "FACILITY_NAME",
        "FACILITY_PHONE",
    }
    assert expected <= MERGE_FIELDS
