"""Maps PayPal's own `transaction_status` vocabulary to RF-One's small
canonical `FinancialTransaction.status` set (COMPLETED / PENDING /
REVERSED / FAILED / UNKNOWN — `ck_ft_status`) — mirrors
`technical/connectors/clover/mapping.py`'s source-vocabulary ->
canonical-vocabulary convention.

PayPal's own status/event code is NEVER discarded by this mapping — it is
preserved verbatim as `FinancialTransaction.native_transaction_type`
(`PayPalTransaction.event_code`, set by `ingest.py`). This module only
decides RF-One's own small OPERATIONAL status; it never decides RF-One's
business classification. Ported unchanged from `feature/purchased-invoice-
intake-alignment` — canonical-model-independent, and the status vocabulary
is identical to `FinancialTransaction`'s.
"""

from __future__ import annotations

# PayPal Transaction Search API `transaction_status` values observed in
# PayPal's own API reference (single-letter forms) plus longer forms used
# by some PayPal documentation/webhooks for the same states — mapped
# defensively; an unrecognized code is never guessed into a canonical
# value, it maps to UNKNOWN instead.
_STATUS_MAP: dict[str, str] = {
    "S": "COMPLETED",
    "SUCCESS": "COMPLETED",
    "COMPLETED": "COMPLETED",
    "P": "PENDING",
    "PENDING": "PENDING",
    "V": "REVERSED",
    "REVERSED": "REVERSED",
    "REFUNDED": "REVERSED",
    "D": "FAILED",
    "DENIED": "FAILED",
    "FAILED": "FAILED",
}


def to_canonical_status(paypal_status: str | None) -> str:
    if not paypal_status:
        return "UNKNOWN"
    return _STATUS_MAP.get(paypal_status.strip().upper(), "UNKNOWN")
