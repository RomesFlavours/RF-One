"""Clover employee creation for "Crea in Clover" (REGISTRY_CLOVER_CREATE_001, Product Owner 2026-11-22).

The only Clover write RF-One performs: create ONE employee in ONE merchant with ONE already-existing Clover
role. It never creates, changes or deletes roles, permissions or other employees, and it never imports Clover
staff data into Registry. Reading here is limited to (a) the chosen role, to check that it exists and is at the
base Employee level, (b) the created employee, to confirm its role, and (c) employees carrying the RF-One
custom ID, to recover the link after an uncertain answer.

Writing is OFF unless the installation enables it explicitly:

    RFONE_CLOVER_EMPLOYEE_CREATE=sandbox     -> https://apisandbox.dev.clover.com,
                                                token CLOVER_SANDBOX_API_TOKEN__<MERCHANT_ID>
    RFONE_CLOVER_EMPLOYEE_CREATE=production  -> https://api.clover.com, the merchant's own token
                                                (the same per-merchant token used for reading)

The token needs the Clover permissions EMPLOYEES_R and EMPLOYEES_W (read/write employees). A POST is never
retried automatically: a retry could create a second employee.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

ENABLE_ENV = "RFONE_CLOVER_EMPLOYEE_CREATE"
SANDBOX_TOKEN_PREFIX = "CLOVER_SANDBOX_API_TOKEN__"
BASE_URLS = {"sandbox": "https://apisandbox.dev.clover.com", "production": "https://api.clover.com"}
BASE_SYSTEM_ROLE = "EMPLOYEE"
TIMEOUT_SECONDS = 20
PAGE_SIZE = 100


class WriterNotAvailable(ValueError):
    """Creation is not enabled, or this merchant has no write credentials. Nothing was sent."""


@dataclass
class RoleCheck:
    found: bool
    system_role: str | None = None
    name: str | None = None
    error: str | None = None           # Clover could not be read: nothing is sent


@dataclass
class CreateResult:
    outcome: str                       # CREATED | REFUSED | UNCERTAIN
    employee_id: str | None = None
    status_code: int = 0
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FindResult:
    ok: bool                           # False: Clover could not be read, the outcome stays uncertain
    employee_ids: list[str] = field(default_factory=list)
    error: str | None = None


class CloverEmployeeWriter(Protocol):
    merchant_id: str
    mode: str

    def check_role(self, role_id: str) -> RoleCheck: ...
    def create_employee(self, *, name: str, custom_id: str, role_id: str) -> CreateResult: ...
    def employee_role_ids(self, employee_id: str) -> list[str] | None: ...
    def find_by_custom_id(self, custom_id: str) -> FindResult: ...


def enabled_mode() -> str | None:
    mode = os.environ.get(ENABLE_ENV, "").strip().lower()
    return mode if mode in BASE_URLS else None


def _token(merchant_id: str, mode: str) -> str | None:
    if mode == "sandbox":
        return os.environ.get(SANDBOX_TOKEN_PREFIX + merchant_id.strip().upper(), "").strip() or None
    from .acquisition import _merchant_token_from_environment
    return _merchant_token_from_environment(merchant_id)


def availability(merchant_id: str) -> str | None:
    """None when a writer can be built for this merchant, else the reason (no network call)."""
    italian = os.environ.get("RFONE_UI_LANGUAGE") == "it"
    mode = enabled_mode()
    if mode is None:
        return (f"La creazione in Clover non è abilitata in questa installazione ({ENABLE_ENV} non impostata)."
                if italian else f"Creation in Clover is not enabled on this installation ({ENABLE_ENV} is not set).")
    try:
        token = _token(merchant_id, mode)
    except ValueError as exc:
        return str(exc)
    if not token:
        expected = (SANDBOX_TOKEN_PREFIX + merchant_id.upper()) if mode == "sandbox" else f"token {merchant_id}"
        return (f"Mancano le credenziali Clover {mode} del merchant {merchant_id} (atteso {expected})." if italian
                else f"No Clover {mode} credentials for merchant {merchant_id} (expected {expected}).")
    return None


def get_writer(merchant_id: str) -> "HttpCloverEmployeeWriter":
    reason = availability(merchant_id)
    if reason:
        raise WriterNotAvailable(reason)
    mode = enabled_mode()
    return HttpCloverEmployeeWriter(merchant_id=merchant_id, token=_token(merchant_id, mode), mode=mode)


class HttpCloverEmployeeWriter:
    def __init__(self, *, merchant_id: str, token: str, mode: str, session=None):
        import requests
        self.merchant_id, self.mode = merchant_id, mode
        self._base = BASE_URLS[mode]
        self._token = token
        self._session = session or requests.Session()

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json",
                "Content-Type": "application/json"}

    def _get(self, path, params=None):
        import requests
        try:
            response = self._session.get(self._base + path, headers=self._headers(), params=params,
                                         timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            return 0, None, f"network error: {exc.__class__.__name__}"
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data, None if response.ok else f"HTTP {response.status_code}"

    def check_role(self, role_id):
        status, data, error = self._get(f"/v3/merchants/{self.merchant_id}/roles/{role_id}")
        if status == 404:
            return RoleCheck(found=False)
        if error or not isinstance(data, dict):
            return RoleCheck(found=False, error=error or "unreadable answer")
        return RoleCheck(found=True, system_role=data.get("systemRole"), name=data.get("name"))

    def create_employee(self, *, name, custom_id, role_id):
        import requests
        body = {"name": name, "customId": custom_id, "role": BASE_SYSTEM_ROLE, "roles": [{"id": role_id}]}
        try:
            response = self._session.post(self._base + f"/v3/merchants/{self.merchant_id}/employees",
                                          headers=self._headers(), json=body, timeout=TIMEOUT_SECONDS)
        except requests.Timeout:
            return CreateResult("UNCERTAIN", message="Clover did not answer in time.")
        except requests.RequestException as exc:
            # A connection refused before sending is still treated as uncertain: RF-One cannot prove it.
            return CreateResult("UNCERTAIN", message=f"network error: {exc.__class__.__name__}")
        try:
            data = response.json()
        except ValueError:
            data = {}
        status = response.status_code
        if 200 <= status < 300 and isinstance(data, dict) and data.get("id"):
            return CreateResult("CREATED", employee_id=str(data["id"]), status_code=status, raw=data)
        if 400 <= status < 500 and status not in (408, 409, 429):
            message = (data.get("message") if isinstance(data, dict) else None) or f"HTTP {status}"
            return CreateResult("REFUSED", status_code=status, message=str(message)[:300])
        return CreateResult("UNCERTAIN", status_code=status, message=f"HTTP {status}")

    def employee_role_ids(self, employee_id):
        status, data, error = self._get(f"/v3/merchants/{self.merchant_id}/employees/{employee_id}",
                                        {"expand": "roles"})
        if error or not isinstance(data, dict):
            return None
        return [str(r.get("id")) for r in ((data.get("roles") or {}).get("elements") or []) if r.get("id")]

    def find_by_custom_id(self, custom_id):
        found, offset = [], 0
        while True:
            status, data, error = self._get(f"/v3/merchants/{self.merchant_id}/employees",
                                            {"filter": f"customId={custom_id}", "limit": PAGE_SIZE, "offset": offset})
            if error or not isinstance(data, dict):
                return FindResult(ok=False, error=error or "unreadable answer")
            elements = data.get("elements") or []
            # The filter is not trusted: only an exact custom ID counts.
            found += [str(e["id"]) for e in elements if e.get("customId") == custom_id and e.get("id")]
            if len(elements) < PAGE_SIZE:
                return FindResult(ok=True, employee_ids=sorted(set(found)))
            offset += PAGE_SIZE
