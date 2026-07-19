"""CRM connectors (M6.8) — same mock-first posture as ``app.services.suppliers``.

Every connector is built against a **recorded fixture response** that *is* the
contract (``fixtures/<provider>/``), so real credentials slot in through config
alone — no code change (build-plan M6 "Adapter posture"). HubSpot is adapter #1;
Salesforce and SAP are post-pilot implementations of the same
:class:`~app.services.crm.base.CrmAdapter` interface (spec ``#crm``: "One
CrmAdapter interface, one implementation per CRM").
"""
