"""Supplier adapters — the mock-first external-sourcing lane (M6.7).

Every external connector in this package is **mock-first**: it is built against a
recorded fixture response (`fixtures/<supplier>/`) that *is* the contract, so real
credentials slot in with no code change (build-plan M6 "Adapter posture";
``DECISIONS.md`` 2026-06-14 *Würth API access*). :mod:`.base` holds the shared
``SupplierAdapter`` interface the later adapters — thyssenkrupp materials4me
(M6.7b, ``MaterialPricingFeed``) and the CNC quick-quote ``PartQuotingAdapter``
(M6.7c) — implement alongside Würth.
"""
