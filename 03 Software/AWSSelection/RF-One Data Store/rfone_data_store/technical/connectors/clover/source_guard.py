"""Clover source guard — "Clover answered, and the answer is empty" is never
the same thing as "RF-One could not read Clover" (CLOVER_ACQUISITION_SAFETY_001).

Before this module, a Clover read that failed (401/403, wrong merchant, 404,
429, 5xx, network) came back to the acquisition engine as an EMPTY list,
and the engine applied it as such: on 2026-09-26 a wrong merchant id made
Employees/Tenders/Shifts unreadable and the engine cleared the Employee and
Tender links of 203 Orders / 217 Payments. This module makes that
impossible:

1. `verify_clover_access()` — run by `acquisition.import_clover_period()`
   right after taking the Location's lock and BEFORE any fetch or write:
   the configured merchant must be the Location's merchant, Clover must
   confirm that merchant, and every source the job will read must answer.
   Any failure stops the job before a single row is touched.
2. `require_complete()` — every Clover collection the engine reads goes
   through it. Only a successful, complete answer returns its elements
   (possibly an empty list — a real, valid "nothing"); anything else raises.

Mandatory sources: every source a job reads is mandatory — the project
defines no Clover source as optional, so none is treated as optional here.
A raised `CloverAcquisitionError` makes the engine roll back everything the
run wrote and end it FAILED with this module's human message; the last
successful synchronization point does not move.
"""

from __future__ import annotations

from typing import Any, Protocol


class CloverAcquisitionError(RuntimeError):
    """A Clover read the acquisition depends on did not succeed. Its message
    is written for a person and is shown as-is in the job history."""


class CloverSourceUnavailableError(CloverAcquisitionError):
    def __init__(self, source: str, *, status_code: int | None, detail: str | None):
        self.source = source
        self.status_code = status_code
        self.detail = detail
        super().__init__(
            f"RF-One could not read {source} from Clover: {_explain(status_code, detail)}. "
            "The acquisition stopped and no RF-One data was changed."
        )


class CloverMerchantMismatchError(CloverAcquisitionError):
    def __init__(self, *, location_label: str, expected_merchant: str, configured_merchant: str, reason: str):
        self.expected_merchant = expected_merchant
        self.configured_merchant = configured_merchant
        super().__init__(
            f"Wrong Clover merchant for {location_label}: it expects Clover merchant {expected_merchant}, "
            f"but the configured Clover merchant is {configured_merchant or '(none)'} — {reason}. "
            "The acquisition was refused and no RF-One data was changed."
        )


def _explain(status_code: int | None, detail: str | None) -> str:
    if status_code in (401, 403):
        return (f"Clover refused the credentials or RF-One's permission for it (HTTP {status_code}) — "
                "check the Clover API token and merchant configuration")
    if status_code == 404:
        return "Clover does not know it for this merchant (HTTP 404) — check the configured merchant"
    if status_code == 429:
        return "Clover is rate-limiting RF-One (HTTP 429, retries exhausted) — try again later"
    if status_code is not None and 500 <= status_code < 600:
        return f"Clover had a server error (HTTP {status_code}) — try again later"
    if status_code == 0:
        return f"Clover could not be reached ({detail or 'network error'})"
    return detail or "unknown error"


def require_complete(result: Any, source: str) -> list[dict[str, Any]]:
    """The elements of a paginated Clover read, only if the read succeeded
    and is complete. An empty list returned here is Clover's real answer."""
    if not getattr(result, "ok", False):
        raise CloverSourceUnavailableError(
            source, status_code=getattr(result, "error_status_code", None), detail=getattr(result, "error", None),
        )
    if getattr(result, "truncated_by_safety_guard", False):
        raise CloverSourceUnavailableError(
            source, status_code=None, detail="the answer was cut short by the pagination safety limit (incomplete)",
        )
    return list(getattr(result, "elements", None) or [])


def require_ok(result: Any, source: str) -> Any:
    """The data of a single Clover GET, only if it succeeded."""
    if not getattr(result, "ok", False):
        raise CloverSourceUnavailableError(
            source, status_code=getattr(result, "status_code", None), detail=getattr(result, "error", None),
        )
    return result.data


class _Client(Protocol):
    merchant_id: str

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...


# Exactly the collections a job reads, by the name a person sees in a
# message. Read in every mode:
CORE_SOURCES = {
    "orders": "Orders", "payments": "Payments", "refunds": "Refunds",
    "employees": "Employees", "shifts": "Shifts",
}
# Read additionally by full-scope modes (Historical Backfill, Sync Now).
# Live Sync does not read Tenders/Devices from Clover — it resolves them
# from what RF-One already holds (CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001) —
# so they are not a Live Sync precondition.
FULL_SCOPE_SOURCES = {
    "tenders": "Tenders (payment methods)", "devices": "Devices", "categories": "Categories", "modifier_groups": "Modifier Groups",
    "discounts": "Discounts", "tax_rates": "Tax Rates", "order_types": "Order Types",
    "items": "Items", "roles": "Roles",
}


def verify_clover_access(
    client: _Client, *, expected_merchant_id: str, location_label: str, full_scope: bool,
) -> None:
    """Pre-flight check, before any write. Raises `CloverAcquisitionError`
    (merchant mismatch, or any mandatory source unreadable); returns
    nothing when Clover is fully readable for this Location."""
    configured = getattr(client, "merchant_id", "") or ""
    if configured != expected_merchant_id:
        raise CloverMerchantMismatchError(
            location_label=location_label, expected_merchant=expected_merchant_id,
            configured_merchant=configured, reason="the configured merchant is not this location's merchant",
        )

    merchant = require_ok(client.get(f"/v3/merchants/{expected_merchant_id}"), "the merchant account")
    returned_id = merchant.get("id") if isinstance(merchant, dict) else None
    if returned_id != expected_merchant_id:
        raise CloverMerchantMismatchError(
            location_label=location_label, expected_merchant=expected_merchant_id,
            configured_merchant=str(returned_id), reason="Clover answered for a different merchant",
        )

    sources = dict(CORE_SOURCES)
    if full_scope:
        sources.update(FULL_SCOPE_SOURCES)
    for endpoint, label in sources.items():
        data = require_ok(client.get(f"/v3/merchants/{expected_merchant_id}/{endpoint}", params={"limit": 1}), label)
        if not isinstance(data, dict) or not isinstance(data.get("elements", []), list):
            raise CloverSourceUnavailableError(label, status_code=None, detail="unexpected answer shape")
