"""The GDPR-vs-GoBD retention policy, as data (M6.9 — pilot hardening).

DACH-DELTA-LAYER §5 grants data-subject rights (Auskunft / Löschung /
Portabilität) and §63 imposes the countervailing duty: *"GoBD (DE) retention:
invoices/quotes/order records retained **immutably ~10 years** with audit trail
— applies to Order/Invoice/Quote records and the e-invoice archive."*

Those two obligations collide on the same rows, so the block's acceptance
criterion is precisely the reconciliation: *"an erasure request removes/anonymizes
lawful data while **preserving GoBD-mandated immutable records**."*

This module is that reconciliation written down once, declaratively, so
:mod:`app.gdpr` is a small engine over a reviewable table rather than a pile of
special cases. Each entry says what happens to a column **and why**, and the
"why" is always a citation, never a judgement call invented here.

**Where the RETAIN reasons come from.** Two independent sources, both external
to this file:

* *Structural* — the table's ``tolera_app`` GRANT already forbids the write.
  ``email_message``, ``quote_status_event``, ``order_history_event`` are
  SELECT+INSERT only (migrations 0024, 0008, 0046). The app role **cannot**
  anonymise them; that was decided when those tables were built, and this module
  records the consequence rather than re-deciding it.
* *Regulatory* — DACH-DELTA §63's GoBD retention for order/quote records.

**What is deliberately NOT here: a retention *window*.** There is no timer, no
purge job, no "delete N months after last activity". CLAUDE.md §6.4 forbids
inventing a regulatory rule, and the specific window for vendor-contact personal
data is already an unresolved ``OPEN:`` in DECISIONS.md (M6.3, 2026-07-19). What
this module supports is **on-request** erasure — a settled data-subject right
that needs no window to be lawful. When the OPEN resolves, a scheduled job can
reuse :data:`ERASURE_POLICY` unchanged.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass


class Disposition(enum.StrEnum):
    """What an erasure request does to a column (or row)."""

    #: Overwrite with a tombstone. The row survives; the person does not.
    anonymize = "anonymize"
    #: Left untouched, with a cited reason. Reported back to the requester so
    #: the response is honest about what was kept and under what obligation.
    retain = "retain"


@dataclass(frozen=True)
class ColumnRule:
    """One column's disposition plus the citation that justifies it."""

    table: str
    column: str
    disposition: Disposition
    reason: str
    #: The tombstone value. ``None`` means SQL NULL (only valid on a nullable
    #: column). ``"unique-email"`` means a per-row unique reserved-domain address
    #: — needed where the column is NOT NULL and carries a live-unique index.
    tombstone: str | None = None


#: RFC 2606 reserves ``.invalid`` precisely so it can never resolve — a tombstone
#: address can therefore never be delivered to, even by a mis-wired job.
ANONYMOUS_EMAIL_DOMAIN = "anonymisiert.invalid"
#: German-first, matching the UI language (CLAUDE.md §5).
ANONYMOUS_NAME = "Gelöscht"


def tombstone_email(subject_key: uuid.UUID) -> str:
    """A per-request unique tombstone address.

    ``contact.email`` is NOT NULL under a live-unique index, so every erased row
    needs a distinct value; a shared constant would collide on the second
    erasure.
    """
    return f"geloescht+{subject_key}@{ANONYMOUS_EMAIL_DOMAIN}"


# --------------------------------------------------------------------------- #
# The policy
# --------------------------------------------------------------------------- #
_GOBD = (
    "GoBD/HGB retention — DACH-DELTA §63 keeps invoice/quote/order records "
    "immutable for ~10 years; erasure may not reach them."
)
_APPEND_ONLY = (
    "Structurally append-only: the tolera_app role holds SELECT+INSERT only on "
    "this table, so it cannot be rewritten (decided when the table was built)."
)

#: Direct-identifier columns an erasure request overwrites with a tombstone.
#: Ordered by table for review. Every entry sits on a table whose tolera_app
#: GRANT includes UPDATE — the policy can only promise what the role can do.
ERASURE_POLICY: tuple[ColumnRule, ...] = (
    # --- the customer contact: the archetypal data subject -----------------
    ColumnRule("contact", "email", Disposition.anonymize, "Direct identifier.", "unique-email"),
    ColumnRule(
        "contact", "first_name", Disposition.anonymize, "Direct identifier.", ANONYMOUS_NAME
    ),
    ColumnRule("contact", "last_name", Disposition.anonymize, "Direct identifier.", ANONYMOUS_NAME),
    ColumnRule("contact", "phone", Disposition.anonymize, "Direct identifier.", None),
    ColumnRule("contact", "phone_ext", Disposition.anonymize, "Direct identifier.", None),
    ColumnRule("contact", "role", Disposition.anonymize, "Personal attribute.", None),
    ColumnRule(
        "contact", "notes", Disposition.anonymize, "Free text written about the person.", None
    ),
    # --- the account: a company, but it carries person-reachable channels ---
    ColumnRule(
        "account", "email", Disposition.anonymize, "Person-reachable channel.", "unique-email"
    ),
    ColumnRule("account", "phone", Disposition.anonymize, "Person-reachable channel.", None),
    ColumnRule("account", "phone_ext", Disposition.anonymize, "Person-reachable channel.", None),
    # --- vendor contacts: B2B data subjects (DACH-DELTA §5) ----------------
    ColumnRule(
        "vendor_contact", "name", Disposition.anonymize, "Direct identifier.", ANONYMOUS_NAME
    ),
    ColumnRule(
        "vendor_contact", "email", Disposition.anonymize, "Direct identifier.", "unique-email"
    ),
    ColumnRule("vendor_contact", "phone", Disposition.anonymize, "Direct identifier.", None),
    # --- the intake RFQ: identifiers go, the letter itself stays -----------
    ColumnRule(
        "request_for_quote",
        "first_name",
        Disposition.anonymize,
        "Direct identifier.",
        ANONYMOUS_NAME,
    ),
    ColumnRule(
        "request_for_quote",
        "last_name",
        Disposition.anonymize,
        "Direct identifier.",
        ANONYMOUS_NAME,
    ),
    ColumnRule(
        "request_for_quote", "email", Disposition.anonymize, "Direct identifier.", "unique-email"
    ),
    ColumnRule("request_for_quote", "phone", Disposition.anonymize, "Direct identifier.", None),
    # --- external-access tokens -------------------------------------------
    ColumnRule(
        "quote_token",
        "recipient_email",
        Disposition.anonymize,
        "Direct identifier.",
        "unique-email",
    ),
    ColumnRule(
        "vendor_rfq_recipient",
        "contact_email",
        Disposition.anonymize,
        "Direct identifier (denormalised snapshot).",
        "unique-email",
    ),
)

#: Everything an erasure request knowingly leaves alone. Reported verbatim in the
#: erasure response so the answer is honest about what survived and why — an
#: erasure report that silently omits retained data is worse than no report.
RETENTION_POLICY: tuple[ColumnRule, ...] = (
    ColumnRule("order_", "company_name", Disposition.retain, _GOBD),
    ColumnRule("order_", "billing_address", Disposition.retain, _GOBD),
    ColumnRule("order_", "notes", Disposition.retain, _GOBD),
    ColumnRule("order_", "buyer_ust_id_nr", Disposition.retain, _GOBD),
    ColumnRule("quote", "private_notes", Disposition.retain, _GOBD),
    ColumnRule("quote_status_event", "*", Disposition.retain, _APPEND_ONLY),
    ColumnRule("order_history_event", "*", Disposition.retain, _APPEND_ONLY),
    ColumnRule("email_message", "*", Disposition.retain, _APPEND_ONLY),
    ColumnRule("quote_email_thread", "*", Disposition.retain, _APPEND_ONLY),
    ColumnRule(
        "request_for_quote",
        "description",
        Disposition.retain,
        "The customer's own enquiry text — the commercial letter itself, not an "
        "identifier the shop recorded about them. " + _GOBD,
    ),
    ColumnRule(
        "export_control_access",
        "*",
        Disposition.retain,
        "The export-control compliance log. " + _APPEND_ONLY + " Erasing it would "
        "defeat the audit obligation it exists to satisfy.",
    ),
    ColumnRule(
        "recent_view",
        "*",
        Disposition.retain,
        "Keyed to an internal AppUser (who opened what), not to a customer or "
        "vendor data subject — a contact erasure has nothing to erase here. "
        "Internal-user erasure is a platform-level action (see app_user).",
    ),
    ColumnRule(
        "app_user",
        "*",
        Disposition.retain,
        "A platform identity shared across organisations (E4-a multi-org): "
        "erasing it from one org's admin surface would reach into another "
        "tenant's data. Employee erasure is a platform-level action, not an "
        "org-admin one.",
    ),
)


def policy_report() -> list[dict[str, str]]:
    """The whole policy, flattened — the machine-readable half of the ROPA and
    what the erasure response embeds as its "retained" section."""
    rows: list[dict[str, str]] = []
    for rule in (*ERASURE_POLICY, *RETENTION_POLICY):
        rows.append(
            {
                "table": rule.table,
                "column": rule.column,
                "disposition": str(rule.disposition),
                "reason": rule.reason,
            }
        )
    return rows
