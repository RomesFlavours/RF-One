"""Mercury Sandbox HTTP client — the minimum surface Tips needs
(TASK_TIPS_CORE2_PILOT §6): read account/availableBalance, resolve a
recipient reference, submit a payment, read a transaction back.

Every endpoint and field used here was verified empirically against the real
Mercury Sandbox (`https://api-sandbox.mercury.com/api/v1/`) and against
Mercury's own published API reference during this task's preparation work —
nothing is invented. No webhook support is used (Mercury sandbox does not
offer it); outcome observation is by polling `get_transaction` only.

Error interpretation is intentionally isolated HERE, not left to callers to
re-derive from raw text each time (`Tips Payment Execution.md`, "Failure
classes"): Mercury returns structured HTTP status classes but only a free-
form `message` string for the actual reason, so this module is the one place
that inspects that string and turns it into a typed, stable exception.
Callers (`rfone_data_store.tips.payment_instruction`) branch on exception
TYPE, never on message text.

Sensitive fields (`accountNumber`, `routingNumber`, and any nested bank
routing/ownership info) are stripped from every parsed response before it
leaves this module — no caller of this client ever sees them, so no
downstream code (logs, UI, reports) can accidentally surface them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import requests

DEFAULT_SANDBOX_BASE_URL = "https://api-sandbox.mercury.com/api/v1/"

_SENSITIVE_KEYS = {
    "accountNumber", "routingNumber", "electronicRoutingInfo", "domesticWireRoutingInfo",
    "realTimePaymentRoutingInfo", "checkInfo", "details",
}


def _strip_sensitive(obj: Any) -> Any:
    """Recursively removes bank-account-identifying fields from a parsed
    JSON response. Applied to every response this client returns — see
    module docstring. Never mutates in place (returns a new structure), so a
    caller cannot accidentally bypass it by holding a reference to the raw
    dict."""
    if isinstance(obj, dict):
        return {k: _strip_sensitive(v) for k, v in obj.items() if k not in _SENSITIVE_KEYS}
    if isinstance(obj, list):
        return [_strip_sensitive(v) for v in obj]
    return obj


class MercuryConnectorError(Exception):
    """Base class for every error this connector raises. `http_status` is
    always present when the provider actually responded; `None` only for a
    transport-level failure (`MercuryUnavailableError`)."""

    def __init__(self, message: str, *, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


class MercuryAuthError(MercuryConnectorError):
    """The token was rejected (401) — an authentication/authorization
    problem, never a business-data problem. Never retried automatically by
    any caller in this codebase (Tips Payment Execution.md, Failure class E)."""


class MercuryValidationError(MercuryConnectorError):
    """The request was rejected before any Transaction was created (400) —
    e.g. "recipient is not configured to receive ACH payments." This is a
    recipient/payment configuration problem, isolated to the one Payment
    Instruction that triggered it (Failure class A)."""


class MercuryDuplicateProtectionError(MercuryValidationError):
    """Mercury's own duplicate-payment heuristic rejected the request (400,
    message contains "duplicate") — same recipient + same amount within its
    lookback window, independent of `idempotencyKey` (Failure class B, see
    `Tips Payment Execution.md`, "Mercury duplicate protection is a safety
    net, never the primary guard"). RF-One's own idempotency
    (`payment_instruction.build_idempotency_key`) is what must have already
    prevented resubmission before this could ever legitimately fire; seeing
    it in practice is itself a signal worth Attention."""


class MercuryNotFoundError(MercuryConnectorError):
    """404 — the referenced id does not exist in this Mercury environment."""


class MercuryUnavailableError(MercuryConnectorError):
    """Transport failure (timeout, connection error) or a 5xx/429 response —
    the provider itself, not a specific request, is the problem (Failure
    class E). Distinct from `MercuryValidationError` so a caller can safely
    retry class E later without ever retrying a class A/B rejection."""


def _raise_for_response(resp: requests.Response) -> None:
    if resp.ok:
        return
    try:
        body = resp.json()
    except ValueError:
        body = {}
    # Mercury's own shape is inconsistent across endpoints: sometimes
    # {"errors": {"message": ...}}, sometimes {"message": ...} directly —
    # both observed empirically against the real sandbox in this task.
    message = None
    errors = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errors, dict):
        message = errors.get("message")
    if message is None and isinstance(body, dict):
        message = body.get("message")
    message = message or f"Mercury returned HTTP {resp.status_code} with no message."

    if resp.status_code == 401:
        raise MercuryAuthError(message, http_status=401)
    if resp.status_code == 404:
        raise MercuryNotFoundError(message, http_status=404)
    if resp.status_code == 400:
        if "duplicate" in message.lower():
            raise MercuryDuplicateProtectionError(message, http_status=400)
        raise MercuryValidationError(message, http_status=400)
    if resp.status_code == 409:
        # Observed empirically (TASK_TIPS_CORE2_PILOT sandbox pilot run):
        # reusing an `idempotencyKey` whose FIRST use carried a different
        # payload (e.g. a different `recipientId`, after a Payment
        # Instruction's recipient reference was corrected) returns 409 with
        # no body message — a key-collision, not the amount/recipient-window
        # heuristic (which is 400 with an explicit message), but the same
        # remedy applies: never resubmit under an already-used key.
        raise MercuryDuplicateProtectionError(
            message if message else "Mercury rejected this idempotencyKey as already used (HTTP 409).",
            http_status=409,
        )
    if resp.status_code == 429 or resp.status_code >= 500:
        raise MercuryUnavailableError(message, http_status=resp.status_code)
    # Any other 4xx not specifically classified above — treated as a
    # validation-class problem (isolated to this one request), never as
    # provider-unavailable, so a caller never blindly retries it.
    raise MercuryValidationError(message, http_status=resp.status_code)


@dataclass
class MercuryAccount:
    id: str
    status: str
    type: str
    kind: str | None
    available_balance: Decimal
    current_balance: Decimal
    name: str | None = None


@dataclass
class MercuryRecipient:
    id: str
    name: str
    status: str
    default_payment_method: str | None


@dataclass
class MercuryTransaction:
    id: str
    status: str
    amount: Decimal
    counterparty_name: str | None
    posted_at: str | None
    estimated_delivery_date: str | None
    failed_at: str | None
    reason_for_failure: str | None
    account_id: str | None
    raw: dict = field(default_factory=dict, repr=False)


class MercuryClient:
    """Thin, synchronous HTTP client. One instance per (base_url, token) —
    stateless beyond that, safe to construct per request or reuse."""

    def __init__(self, *, base_url: str | None = None, token: str | None = None, timeout_seconds: float = 20.0):
        self._base_url = (base_url or DEFAULT_SANDBOX_BASE_URL).rstrip("/") + "/"
        self._token = token or os.environ.get("MERCURY_SANDBOX_API_TOKEN")
        if not self._token:
            raise MercuryConnectorError(
                "No Mercury sandbox token available — set MERCURY_SANDBOX_API_TOKEN. "
                "This connector never falls back to a production token/endpoint."
            )
        self._timeout = timeout_seconds

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def _get(self, path: str, *, params: dict | None = None) -> Any:
        try:
            resp = requests.get(self._base_url + path, headers=self._headers(), params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            raise MercuryUnavailableError(f"Transport error calling Mercury: {exc}") from exc
        _raise_for_response(resp)
        return _strip_sensitive(resp.json())

    def _post(self, path: str, *, json_body: dict) -> Any:
        try:
            resp = requests.post(
                self._base_url + path, headers={**self._headers(), "Content-Type": "application/json"},
                json=json_body, timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise MercuryUnavailableError(f"Transport error calling Mercury: {exc}") from exc
        _raise_for_response(resp)
        return _strip_sensitive(resp.json())

    # -- Accounts -----------------------------------------------------------

    def get_accounts(self) -> list[MercuryAccount]:
        data = self._get("accounts")
        return [
            MercuryAccount(
                id=a["id"], status=a.get("status", "unknown"), type=a.get("type", "unknown"),
                kind=a.get("kind"), available_balance=Decimal(str(a.get("availableBalance", 0))),
                current_balance=Decimal(str(a.get("currentBalance", 0))), name=a.get("name") or a.get("nickname"),
            )
            for a in data.get("accounts", [])
        ]

    # -- Recipients -----------------------------------------------------------

    def get_recipients(self, *, limit: int = 1000) -> list[MercuryRecipient]:
        data = self._get("recipients", params={"limit": limit})
        return [
            MercuryRecipient(
                id=r["id"], name=r.get("name", ""), status=r.get("status", "unknown"),
                default_payment_method=r.get("defaultPaymentMethod"),
            )
            for r in data.get("recipients", [])
        ]

    def find_recipient_by_name(self, name: str) -> MercuryRecipient | None:
        """Pilot-only convenience for resolving one of the sandbox's own
        pre-loaded recipients (e.g. "Alex Rivera") by exact name — the pilot
        deliberately does NOT create recipients (task §7: "non automatizzare
        la creazione Recipient in questo task"). Production Employee <->
        recipient resolution is `EmployeeExternalPaymentAccount`
        (`payment_instruction.py`), never a name lookup."""
        for r in self.get_recipients():
            if r.name == name:
                return r
        return None

    # -- Transactions -----------------------------------------------------------

    def create_transaction(
        self, *, account_id: str, recipient_id: str, amount: Decimal, payment_method: str, idempotency_key: str,
        purpose: str | None = None,
    ) -> MercuryTransaction:
        """Submits ONE payment. `idempotency_key` must be the deterministic
        RF-One-derived key (`payment_instruction.build_idempotency_key`) —
        this client never generates one itself, per task §5 ("la protezione
        primaria dal doppio pagamento deve essere RF-One"). `purpose` is
        only required by Mercury for `domesticWire` (not used by Tips ACH
        payouts today) — accepted here for completeness, never defaulted."""
        body: dict[str, Any] = {
            "recipientId": recipient_id, "amount": float(amount), "paymentMethod": payment_method,
            "idempotencyKey": idempotency_key,
        }
        if purpose is not None:
            body["purpose"] = purpose
        data = self._post(f"account/{account_id}/transactions", json_body=body)
        return self._parse_transaction(data)

    def get_transaction(self, transaction_id: str) -> MercuryTransaction:
        data = self._get(f"transaction/{transaction_id}")
        return self._parse_transaction(data)

    @staticmethod
    def _parse_transaction(data: dict) -> MercuryTransaction:
        return MercuryTransaction(
            id=data["id"], status=data.get("status", "unknown"), amount=Decimal(str(abs(data.get("amount", 0)))),
            counterparty_name=data.get("counterpartyName"), posted_at=data.get("postedAt"),
            estimated_delivery_date=data.get("estimatedDeliveryDate"), failed_at=data.get("failedAt"),
            reason_for_failure=data.get("reasonForFailure"), account_id=data.get("accountId"), raw=data,
        )
