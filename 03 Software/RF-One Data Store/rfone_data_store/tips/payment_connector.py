"""Tip payment connector resolution — the provider-neutral seam between
Tips payment execution (`payment_instruction.py`, `payment_cycle_service.py`,
`payout_process.py`, `scheduler.py`) and the actual technical connector that
executes a payment (`technical.connectors.mercury.client` today; any future
connector tomorrow) (STEP 12B integration; `01 Domains/Business Domain/
Restaurant/Tips/Tips Payment Execution.md`).

Product Owner decision this module implements: `TipPaymentInstruction`
records WHAT must be paid and stays provider-neutral (`models.py`). Payment
mode/configuration (`TipsPaymentScheduleConfig.connector_code`) records
WHICH connector executes it — this module resolves that configured code to
an actual connector implementation. Execution code above this module never
imports `technical.connectors.mercury` directly; Mercury is registered like
any other connector would be, never wired in as a silent default.

Connector-neutral exceptions (`PaymentConnectorError` and its subclasses)
let `payment_instruction.py` classify a failure without importing/catching
a provider-specific exception type — `MercuryPaymentConnector` below is the
ONLY place a `Mercury*Error` is ever caught.

Fails closed by construction (mandatory requirement): `resolve_connector`
raises `ConnectorNotConfiguredError`/`UnknownConnectorError` rather than
ever returning a default connector — there is no fallback branch to
accidentally reach. A small, explicit, deterministic registry — no plugin
framework, no dynamic discovery, no speculative future connectors."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from ..technical.connectors.mercury.client import (
    MercuryAuthError, MercuryClient, MercuryConnectorError, MercuryDuplicateProtectionError, MercuryNotFoundError,
    MercuryUnavailableError, MercuryValidationError,
)

CONNECTOR_CODE_MERCURY = "MERCURY"


class PaymentConnectorError(Exception):
    """Base for every connector-neutral payment execution failure —
    `payment_instruction.py` catches these, never a provider-specific
    exception type directly."""


class ConnectorAuthError(PaymentConnectorError):
    pass


class ConnectorDuplicateError(PaymentConnectorError):
    pass


class ConnectorValidationError(PaymentConnectorError):
    pass


class ConnectorUnavailableError(PaymentConnectorError):
    pass


class ConnectorNotFoundError(PaymentConnectorError):
    pass


class ConnectorConfigurationError(PaymentConnectorError):
    """Fail-closed: missing/unknown connector configuration (mandatory
    "no silent Mercury fallback" requirement) — never silently resolved to
    a default connector."""


class ConnectorNotConfiguredError(ConnectorConfigurationError):
    pass


class UnknownConnectorError(ConnectorConfigurationError):
    pass


@dataclass
class ConnectorAccount:
    id: str
    type: str
    status: str
    kind: str | None
    available_balance: Decimal


@dataclass
class ConnectorTransaction:
    id: str
    status: str
    posted_at: str | None
    reason_for_failure: str | None = None


@dataclass
class ConnectorRecipient:
    id: str
    name: str


class PaymentConnector(Protocol):
    """The minimum surface Tips payment execution needs from ANY connector
    — deliberately just the three operations `payment_instruction.py`
    already called directly on `MercuryClient` before this module existed,
    renamed to provider-neutral verbs. A future second real connector
    implements exactly this, nothing more."""

    connector_code: str

    def create_transaction(
        self, *, account_id: str, recipient_id: str, amount: Decimal, payment_method: str, idempotency_key: str,
    ) -> ConnectorTransaction: ...

    def get_transaction(self, transaction_id: str) -> ConnectorTransaction: ...

    def get_accounts(self) -> list[ConnectorAccount]: ...

    def find_recipient_by_name(self, name: str) -> ConnectorRecipient | None: ...


class MercuryPaymentConnector:
    """Adapter: wraps `technical.connectors.mercury.client.MercuryClient`
    (RF-One's one currently-implemented connector — `Tips Payment
    Execution.md`: "this pilot's one implemented connector, not the
    canonical payment model") behind the connector-neutral `PaymentConnector`
    surface, translating every Mercury-specific exception to its
    connector-neutral equivalent. Every Mercury-specific detail (its
    client, its exception types, its own account/transaction shape, its
    sandbox source-account fallback below) stays inside this adapter —
    nothing above this module ever imports `technical.connectors.mercury`
    again."""

    connector_code = CONNECTOR_CODE_MERCURY

    def __init__(self, client: MercuryClient | None = None):
        if client is not None:
            self._client = client
            return
        try:
            self._client = MercuryClient()
        except MercuryConnectorError as exc:
            raise ConnectorUnavailableError(str(exc)) from exc

    def create_transaction(
        self, *, account_id: str, recipient_id: str, amount: Decimal, payment_method: str, idempotency_key: str,
    ) -> ConnectorTransaction:
        try:
            txn = self._client.create_transaction(
                account_id=account_id, recipient_id=recipient_id, amount=amount,
                payment_method=payment_method, idempotency_key=idempotency_key,
            )
        except MercuryAuthError as exc:
            raise ConnectorAuthError(str(exc)) from exc
        except MercuryDuplicateProtectionError as exc:
            raise ConnectorDuplicateError(str(exc)) from exc
        except MercuryValidationError as exc:
            raise ConnectorValidationError(str(exc)) from exc
        except MercuryUnavailableError as exc:
            raise ConnectorUnavailableError(str(exc)) from exc
        return ConnectorTransaction(id=txn.id, status=txn.status, posted_at=txn.posted_at)

    def get_transaction(self, transaction_id: str) -> ConnectorTransaction:
        try:
            txn = self._client.get_transaction(transaction_id)
        except MercuryNotFoundError as exc:
            raise ConnectorNotFoundError(str(exc)) from exc
        except (MercuryAuthError, MercuryUnavailableError) as exc:
            raise ConnectorUnavailableError(str(exc)) from exc
        return ConnectorTransaction(
            id=txn.id, status=txn.status, posted_at=txn.posted_at, reason_for_failure=txn.reason_for_failure,
        )

    def get_accounts(self) -> list[ConnectorAccount]:
        try:
            accounts = self._client.get_accounts()
        except (MercuryAuthError, MercuryUnavailableError) as exc:
            raise ConnectorUnavailableError(str(exc)) from exc
        return [
            ConnectorAccount(id=a.id, type=a.type, status=a.status, kind=a.kind, available_balance=a.available_balance)
            for a in accounts
        ]

    def find_recipient_by_name(self, name: str) -> ConnectorRecipient | None:
        try:
            recipient = self._client.find_recipient_by_name(name)
        except MercuryConnectorError as exc:
            raise ConnectorUnavailableError(str(exc)) from exc
        if recipient is None:
            return None
        return ConnectorRecipient(id=recipient.id, name=recipient.name)

    def resolve_fallback_source_account_id(self) -> str | None:
        """Mercury-specific fallback ONLY when a Restaurant has not yet
        configured `TipsPaymentScheduleConfig.mercury_source_account_id`:
        the first active Mercury `checking` account with a positive
        balance. Stays inside this connector's own boundary — a future
        connector defines its own fallback (or none) entirely
        independently, never through this method."""
        for account in self.get_accounts():
            if account.type == "mercury" and account.status == "active" and account.kind == "checking" and account.available_balance > 0:
                return account.id
        return None


# Deterministic, explicit registry — no plugin framework, no dynamic
# discovery, only the minimum routing needed now. Adding a second real
# connector means adding one more entry here and widening
# `ck_tips_payment_schedule_connector_code`, never touching this
# resolution logic.
_CONNECTOR_FACTORIES = {
    CONNECTOR_CODE_MERCURY: MercuryPaymentConnector,
}


def known_connector_codes() -> tuple[str, ...]:
    """A live view of the registry, not a snapshot — module-level code that
    reads `KNOWN_CONNECTOR_CODES` once at import time would otherwise never
    see a connector registered afterward (e.g. a test's temporary
    registration for `resolve_connector`)."""
    return tuple(_CONNECTOR_FACTORIES)


KNOWN_CONNECTOR_CODES: tuple[str, ...] = tuple(_CONNECTOR_FACTORIES)


def resolve_connector(connector_code: str | None, **kwargs) -> PaymentConnector:
    """`configured connector identifier -> registered connector
    implementation`. Fails closed: `None`/empty raises
    `ConnectorNotConfiguredError`; any code not in the registry raises
    `UnknownConnectorError` — NEVER a silent Mercury default. `kwargs` are
    passed straight through to the resolved connector's constructor (e.g.
    `client=` a fake `MercuryClient`-shaped object in tests)."""
    if not connector_code:
        raise ConnectorNotConfiguredError(
            "No payment connector is configured for this payment mode — Tips payment execution requires an "
            "explicit connector_code (e.g. 'MERCURY') on the effective TipsPaymentScheduleConfig."
        )
    factory = _CONNECTOR_FACTORIES.get(connector_code)
    if factory is None:
        raise UnknownConnectorError(
            f"Configured payment connector {connector_code!r} is not a registered connector "
            f"(known: {sorted(_CONNECTOR_FACTORIES)})."
        )
    return factory(**kwargs)
