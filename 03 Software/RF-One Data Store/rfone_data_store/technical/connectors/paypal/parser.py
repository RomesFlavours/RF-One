"""Raw PayPal Transaction Search API `transaction_details` entries ->
`PayPalTransaction`, a typed intermediate representation. No DB/session
code here (mirrors `technical/connectors/clover/parser.py`'s own
raw-JSON-to-typed-structure separation from `ingest.py`).

PayPal's Transaction Search response shape (PayPal's own API reference):
each `transaction_details` entry has a `transaction_info` block (id,
amounts, dates, event code, status) and a `payer_info` block (payer
identity). Only the fields RF-One's reconciliation model actually needs are
read into typed fields — the raw JSON itself is preserved separately,
unparsed, via `SourceRecord.raw_json`/`payload_hash` (`ingest.py`), so
nothing PayPal sent is ever discarded even though this parser only
interprets a subset of it. Ported unchanged from `feature/purchased-
invoice-intake-alignment` — canonical-model-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PayPalTransaction:
    """One PayPal Transaction Search `transaction_details` entry, parsed.
    `gross_amount_minor`/`fee_amount_minor`/`net_amount_minor` are kept
    separate (never pre-merged) so a downstream fee is never silently
    absorbed — `net_amount_minor` is what
    `technical/connectors/paypal/ingest.py` writes as
    `FinancialTransaction.amount_minor` (the net effect on the PayPal
    balance); gross/fee are preserved alongside it as enrichment."""

    transaction_id: str
    transaction_datetime: datetime
    gross_amount_minor: int | None
    fee_amount_minor: int | None
    net_amount_minor: int | None
    currency: str
    event_code: str | None  # PayPal's own T-code (e.g. "T0000"), preserved verbatim
    status: str | None  # PayPal's own transaction_status, preserved verbatim
    counterparty_name: str | None
    counterparty_identifier: str | None  # payer/payee email or account id
    description: str | None
    related_transaction_id: str | None  # PayPal's own paypal_reference_id, when present
    raw: dict[str, Any]


def _amount_to_minor(value: dict[str, Any] | None) -> int | None:
    """PayPal amounts are `{"currency_code": "...", "value": "12.34"}`
    strings — converts to a signed integer minor-units amount without
    binary-float rounding error (this schema's existing money convention,
    `models.py` module docstring, `Decimal` scaled and truncated to int)."""
    if not value or value.get("value") is None:
        return None
    decimal_value = Decimal(str(value["value"]))
    return int((decimal_value * 100).to_integral_value())


def _currency_of(*values: dict[str, Any] | None) -> str | None:
    for value in values:
        if value and value.get("currency_code"):
            return value["currency_code"]
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    # PayPal timestamps are ISO-8601 with a trailing "Z" (UTC).
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _payer_name(payer: dict[str, Any]) -> str | None:
    name_info = payer.get("payer_name") or {}
    if name_info.get("alternate_full_name"):
        return name_info["alternate_full_name"]
    given, surname = name_info.get("given_name"), name_info.get("surname")
    if given or surname:
        return " ".join(part for part in (given, surname) if part)
    return None


def parse_transaction_detail(raw: dict[str, Any]) -> PayPalTransaction:
    """Parses one raw `transaction_details` entry as returned by
    `PayPalClient.fetch_all_transactions` (or an equivalent fixture in
    tests — this function never calls PayPal itself)."""
    info = raw.get("transaction_info", {}) or {}
    payer = raw.get("payer_info", {}) or {}

    gross = info.get("transaction_amount")
    fee = info.get("fee_amount")
    gross_minor = _amount_to_minor(gross)
    fee_minor = _amount_to_minor(fee)
    # PayPal reports the fee already negative when one applies; net is not
    # always its own field in the response, so it is derived (gross + fee)
    # only when both are known — never guessed when either is missing.
    net_minor = gross_minor + fee_minor if gross_minor is not None and fee_minor is not None else gross_minor

    return PayPalTransaction(
        transaction_id=info["transaction_id"],
        transaction_datetime=(
            _parse_datetime(info.get("transaction_initiation_date"))
            or _parse_datetime(info.get("transaction_updated_date"))
        ),
        gross_amount_minor=gross_minor,
        fee_amount_minor=fee_minor,
        net_amount_minor=net_minor,
        currency=_currency_of(gross, fee) or "USD",
        event_code=info.get("transaction_event_code"),
        status=info.get("transaction_status"),
        counterparty_name=_payer_name(payer),
        counterparty_identifier=payer.get("email_address"),
        description=info.get("transaction_subject") or info.get("transaction_note"),
        related_transaction_id=info.get("paypal_reference_id"),
        raw=raw,
    )
