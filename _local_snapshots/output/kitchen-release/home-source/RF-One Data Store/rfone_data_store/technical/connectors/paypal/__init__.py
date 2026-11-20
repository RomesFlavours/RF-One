"""The PayPal Technical Connector (TECHNICAL_CONNECTORS_STRUCTURE_001,
FINANCIAL_MODEL_CONVERGENCE_001 Phase 5).

Retrieves transaction data from PayPal's own Transaction Search API
(`client.py`), maps it into RF-One's canonical `FinancialTransaction`
representation (`parser.py`/`mapping.py`), and writes it idempotently
(`ingest.py`) — the same shape as `technical/connectors/clover/`: this
connector owns ONLY PayPal integration concerns (authentication, the API
client, mapping PayPal's own vocabulary to RF-One's canonical one,
idempotent upsert) — never cross-ledger reconciliation/classification logic
or any other Domain-specific decision logic. Nothing here is imported by
`rfone_data_store.models` — the dependency runs one way.

Phase 5 ports this connector from `feature/purchased-invoice-intake-
alignment` and retargets it from that branch's `PaymentInstrumentTransaction`
(not present on this branch) to the canonical `FinancialTransaction` ledger
already shared with CSV-sourced Bank Reconciliation — see `ingest.py`'s
module docstring for the exact field adaptation.
"""
