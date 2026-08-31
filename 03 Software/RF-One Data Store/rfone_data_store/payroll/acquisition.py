"""Payroll Result Acquisition adapters (TASK_PAYROLL_003).

Payroll calculation != Payroll result acquisition != Payment execution
(`01 Domains/Administration/Payroll/Payroll Result Acquisition.md`). This
module is the acquisition layer: it is responsible only for getting an ADP
`Payroll Detail` result's bytes into RF-One's process, normalized into the
same `ParsedPayrollDetail` structure regardless of how those bytes arrived,
and then handing off to `adp_importer.persist_parsed_import` — the single,
already-tested persistence/idempotency/provenance core every adapter here
shares unchanged. No adapter in this module contains its own persistence
logic, its own idempotency check, or its own Employee-mapping logic.

Three adapters:

- `LocalFileAcquisitionAdapter` — reads a local `.xlsx` file. This is the
  existing, fully supported TASK_PAYROLL_001 path (`adp_importer.py`),
  wrapped here only so callers can treat every acquisition path uniformly.
  The manual/local-file path remains a valid production fallback — never
  redefined as "automatic acquisition."
- `AdpSftpAcquisitionAdapter` — connects to a customer-controlled SFTP
  endpoint ADP's own "Automatic Export Service" (AES) delivers a scheduled
  report to, and downloads any not-yet-imported files. This is a genuinely
  automatic acquisition path: once ADP AES is configured (an ADP account
  action, external to this repository — see `07 Tasks/Reports/
  TASK_PAYROLL_003_REPORT.md`), no human downloads or uploads anything for
  each payroll run. Fully implemented and testable against any object
  satisfying the small `SftpTransport` protocol below; requires real SFTP
  connection details, supplied only via environment variables, never
  hard-coded or committed to Git.
- `AdpApiAcquisitionAdapter` — scaffold for ADP's official "Payroll Output
  API for RUN Powered by ADP." Verified to exist as a real, documented ADP
  product (OAuth 2.0 client-credentials + mutual TLS, relationship-gated
  access via ADP API Central or the ADP Marketplace partner program — see
  the task report). This adapter validates and loads credentials from the
  environment, but its actual HTTP request/response handling is
  **intentionally left unimplemented**: the exact endpoint path and JSON
  response schema live in ADP's protected developer documentation, which is
  only released once ADP grants API Central/Marketplace access — attempting
  to guess them would mean inventing an API contract, which this task
  explicitly forbids. Calling `fetch()` before that documentation is
  available and before credentials are configured raises a clear,
  actionable error rather than fabricating a response.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import adp_importer as adp

ACQUISITION_METHOD_XLSX_FILE = "ADP_XLSX_FILE"
ACQUISITION_METHOD_SFTP_AES = "ADP_SFTP_AES"
ACQUISITION_METHOD_API = "ADP_API"


class AcquisitionNotConfiguredError(RuntimeError):
    """Raised when an adapter's required external configuration (SFTP
    connection details, API credentials) is not present in the
    environment. Never silently skipped — the caller must see exactly what
    is missing."""


class AdpApiNotImplementedError(NotImplementedError):
    """Raised by `AdpApiAcquisitionAdapter.fetch()` unconditionally today:
    even with valid-looking credentials configured, the actual ADP Payroll
    Output API request/response mapping is not implemented, because its
    exact endpoint and schema are documented only in ADP's protected
    developer portal, released after ADP grants API Central/Marketplace
    access (see `07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md`, "Verified
    ADP acquisition mechanism"). Raising here — rather than guessing an
    endpoint/field mapping — is deliberate: this task does not invent API
    endpoints or contracts."""


@dataclass
class AcquiredPayrollFile:
    """One acquired ADP `Payroll Detail` result, normalized to the same
    shape regardless of acquisition method."""

    file_bytes: bytes
    source_file_name: str
    acquisition_method: str


class PayrollAcquisitionAdapter(Protocol):
    """The contract every acquisition adapter satisfies. `fetch()` returns
    zero or more not-yet-seen results; idempotency itself is enforced
    downstream by `adp_importer.persist_parsed_import` (content-hash
    keyed), so an adapter is free to return a file it has returned before
    without breaking anything — it only affects efficiency, never
    correctness."""

    def fetch(self) -> list[AcquiredPayrollFile]: ...


# ---------------------------------------------------------------------------
# Local file adapter — the existing TASK_PAYROLL_001 path, wrapped
# ---------------------------------------------------------------------------


@dataclass
class LocalFileAcquisitionAdapter:
    """Wraps a single local `.xlsx` file path as a `PayrollAcquisitionAdapter`
    — the manual/local-file fallback (TASK_PAYROLL_001), preserved unchanged
    and never redefined as automatic acquisition."""

    file_path: Path

    def fetch(self) -> list[AcquiredPayrollFile]:
        data = self.file_path.read_bytes()
        return [
            AcquiredPayrollFile(
                file_bytes=data,
                source_file_name=self.file_path.name,
                acquisition_method=ACQUISITION_METHOD_XLSX_FILE,
            )
        ]


# ---------------------------------------------------------------------------
# ADP SFTP (Automatic Export Service) adapter — real, genuinely automatic
# ---------------------------------------------------------------------------


class SftpTransport(Protocol):
    """The minimal subset of `paramiko.SFTPClient`'s interface this adapter
    needs — expressed as a Protocol so tests can supply a fake transport
    without a real SFTP server or network access, and so this module does
    not import `paramiko` at module load time (it is only imported inside
    `AdpSftpAcquisitionAdapter.from_environment()`, so environments that
    never use SFTP acquisition are not required to have it installed)."""

    def listdir(self, path: str) -> list[str]: ...
    def open(self, path: str, mode: str = "r"): ...


@dataclass
class SftpConnectionConfig:
    host: str
    username: str
    remote_directory: str
    port: int = 22
    password: str | None = None
    private_key_path: str | None = None


class AdpSftpAcquisitionAdapter:
    """Downloads not-yet-imported ADP `Payroll Detail` files from a
    customer-controlled SFTP endpoint that ADP's Automatic Export Service
    (AES) delivers a scheduled report to (TASK_PAYROLL_003, Part A/B —
    verified as a real, officially supported ADP RUN reporting
    mechanism: a one-time ADP-side setup requested by the account holder
    through ADP's Reporting module / an ADP representative; not an
    invented endpoint). Once configured on the ADP side, this adapter
    requires no human to download or upload anything for each payroll
    run — genuine automatic acquisition.

    Connection details are supplied only via environment variables, never
    hard-coded or committed to Git:

        ADP_SFTP_HOST                required
        ADP_SFTP_USERNAME            required
        ADP_SFTP_REMOTE_DIRECTORY    required
        ADP_SFTP_PORT                optional, default 22
        ADP_SFTP_PASSWORD            optional (one of password/private key required)
        ADP_SFTP_PRIVATE_KEY_PATH    optional (one of password/private key required)

    The actual downloaded bytes are parsed by the same
    `adp_importer.parse_payroll_detail_workbook_bytes` the local-file
    adapter's content ultimately feeds through
    `adp_importer.persist_parsed_import` — this adapter contributes no
    parsing logic of its own; it only moves bytes.
    """

    def __init__(self, config: SftpConnectionConfig, *, transport_factory=None) -> None:
        self._config = config
        self._transport_factory = transport_factory or self._connect_via_paramiko

    @classmethod
    def from_environment(cls, env: dict[str, str]) -> "AdpSftpAcquisitionAdapter":
        """Builds the adapter from environment variables, raising
        `AcquisitionNotConfiguredError` naming exactly what is missing
        rather than proceeding with a partial/guessed configuration."""
        missing = [
            name for name in ("ADP_SFTP_HOST", "ADP_SFTP_USERNAME", "ADP_SFTP_REMOTE_DIRECTORY")
            if not env.get(name)
        ]
        password = env.get("ADP_SFTP_PASSWORD")
        private_key_path = env.get("ADP_SFTP_PRIVATE_KEY_PATH")
        if not password and not private_key_path:
            missing.append("ADP_SFTP_PASSWORD or ADP_SFTP_PRIVATE_KEY_PATH")
        if missing:
            raise AcquisitionNotConfiguredError(
                "ADP SFTP acquisition is not configured — missing environment variable(s): "
                f"{', '.join(missing)}. These must be supplied externally (never committed to "
                "Git); see 07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md for what to request from "
                "ADP to activate the SFTP endpoint itself."
            )
        config = SftpConnectionConfig(
            host=env["ADP_SFTP_HOST"],
            username=env["ADP_SFTP_USERNAME"],
            remote_directory=env["ADP_SFTP_REMOTE_DIRECTORY"],
            port=int(env.get("ADP_SFTP_PORT", "22")),
            password=password,
            private_key_path=private_key_path,
        )
        return cls(config)

    def _connect_via_paramiko(self) -> SftpTransport:
        import paramiko  # imported lazily — only needed when SFTP acquisition actually runs

        transport = paramiko.Transport((self._config.host, self._config.port))
        if self._config.private_key_path:
            pkey = paramiko.RSAKey.from_private_key_file(self._config.private_key_path)
            transport.connect(username=self._config.username, pkey=pkey)
        else:
            transport.connect(username=self._config.username, password=self._config.password)
        return paramiko.SFTPClient.from_transport(transport)

    def fetch(self) -> list[AcquiredPayrollFile]:
        sftp = self._transport_factory()
        results: list[AcquiredPayrollFile] = []
        for filename in sftp.listdir(self._config.remote_directory):
            if not filename.lower().endswith(".xlsx"):
                continue
            remote_path = f"{self._config.remote_directory.rstrip('/')}/{filename}"
            with sftp.open(remote_path, "rb") as fh:
                data = fh.read()
            results.append(
                AcquiredPayrollFile(
                    file_bytes=data,
                    source_file_name=filename,
                    acquisition_method=ACQUISITION_METHOD_SFTP_AES,
                )
            )
        return results


# ---------------------------------------------------------------------------
# ADP Payroll Output API adapter — scaffold only, not activated
# ---------------------------------------------------------------------------


@dataclass
class AdpApiCredentials:
    base_url: str
    client_id: str
    client_secret: str
    client_cert_path: str
    client_key_path: str


class AdpApiAcquisitionAdapter:
    """Scaffold for ADP's official "Payroll Output API for RUN Powered by
    ADP" (verified to exist — see the task report). `from_environment()`
    validates that credential configuration is present; `fetch()` always
    raises `AdpApiNotImplementedError` today, because the exact endpoint
    path and response schema require ADP's protected API documentation,
    released only after ADP grants API Central/Marketplace access — this
    task does not guess them.

    Environment variables (never hard-coded or committed to Git):

        ADP_API_BASE_URL
        ADP_API_CLIENT_ID
        ADP_API_CLIENT_SECRET
        ADP_API_CLIENT_CERT_PATH   (mutual TLS client certificate)
        ADP_API_CLIENT_KEY_PATH    (mutual TLS client private key)
    """

    def __init__(self, credentials: AdpApiCredentials) -> None:
        self._credentials = credentials

    @classmethod
    def from_environment(cls, env: dict[str, str]) -> "AdpApiAcquisitionAdapter":
        required = (
            "ADP_API_BASE_URL", "ADP_API_CLIENT_ID", "ADP_API_CLIENT_SECRET",
            "ADP_API_CLIENT_CERT_PATH", "ADP_API_CLIENT_KEY_PATH",
        )
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise AcquisitionNotConfiguredError(
                "ADP Payroll Output API acquisition is not configured — missing environment "
                f"variable(s): {', '.join(missing)}. These are issued by ADP only after ADP "
                "grants API Central/Marketplace access to the Rome's Flavours ADP account; see "
                "07 Tasks/Reports/TASK_PAYROLL_003_REPORT.md."
            )
        return cls(AdpApiCredentials(
            base_url=env["ADP_API_BASE_URL"],
            client_id=env["ADP_API_CLIENT_ID"],
            client_secret=env["ADP_API_CLIENT_SECRET"],
            client_cert_path=env["ADP_API_CLIENT_CERT_PATH"],
            client_key_path=env["ADP_API_CLIENT_KEY_PATH"],
        ))

    def fetch(self) -> list[AcquiredPayrollFile]:
        raise AdpApiNotImplementedError(
            "ADP Payroll Output API credentials are configured, but the request/response "
            "mapping is not implemented — the exact endpoint path and JSON schema are documented "
            "only in ADP's protected 'Payroll Output API Guide for RUN Powered by ADP', released "
            "after ADP grants API Central/Marketplace access. Use AdpSftpAcquisitionAdapter (ADP "
            "Automatic Export Service) or the LocalFileAcquisitionAdapter fallback until that "
            "documentation is obtained and this method is completed against it."
        )


# ---------------------------------------------------------------------------
# Shared orchestration — every adapter feeds the same persistence core
# ---------------------------------------------------------------------------


def acquire_and_import(
    session,
    adapter: PayrollAcquisitionAdapter,
    *,
    source_system_id: int,
    restaurant_id: int,
    period_start,
    period_end,
    run_type: str,
    payroll_schedule_id: int | None = None,
    pay_date_override=None,
    payment_execution_provider: str | None = None,
) -> list[adp.PersistResult]:
    """Fetches every result the adapter currently offers and persists each
    through `adp_importer.persist_parsed_import` — the same idempotent,
    provenance-preserving core the local-file path already uses. Returns
    one `PersistResult` per acquired file (already-imported files come back
    with `created=False`, never duplicated — see `persist_parsed_import`).
    """
    results: list[adp.PersistResult] = []
    for acquired in adapter.fetch():
        parsed = adp.parse_payroll_detail_workbook_bytes(acquired.file_bytes)
        file_hash = adp.sha256_bytes(acquired.file_bytes)
        results.append(
            adp.persist_parsed_import(
                session,
                source_system_id=source_system_id,
                restaurant_id=restaurant_id,
                parsed=parsed,
                source_file_name=acquired.source_file_name,
                source_file_hash=file_hash,
                acquisition_method=acquired.acquisition_method,
                period_start=period_start,
                period_end=period_end,
                run_type=run_type,
                payroll_schedule_id=payroll_schedule_id,
                pay_date_override=pay_date_override,
                payment_execution_provider=payment_execution_provider,
            )
        )
    return results
