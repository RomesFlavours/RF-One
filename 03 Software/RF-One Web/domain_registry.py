"""Explicit, static registry of the RF-One Domains the general shell (V1)
knows about. This is the single source of truth for which `domain_code`
values are valid in `RFOneAccountDomainAccess.domain_code` — the database
itself never enforces this list (see that model's own docstring).

`future_path` remains the conceptual, eventual in-app path for a Domain
once it is actually integrated into RF-One Web (RF-ONE GENERAL WEB APP V1
§15: "Do NOT move Tips or Training into this app yet") — it is documentation
only and is never used to build a link.

`link` is the ONE field the Home page actually renders as the Domain
card's destination:
  - a relative path (e.g. Training's `/training`) for a Domain genuinely
    mounted inside this application;
  - an absolute URL for a Domain published as its own separate, reachable
    service (e.g. Tips's own App Runner URL) — never a local path like
    `/tips` that nothing here serves;
  - `None` for a Domain not actually published anywhere yet — the Home
    page renders it as a non-clickable "Not yet available" card rather
    than a link to a destination that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainDefinition:
    code: str
    display_name: str
    description: str
    future_path: str
    link: str | None = None


DOMAINS: tuple[DomainDefinition, ...] = (
    DomainDefinition(
        code="TRAINING",
        display_name="Training",
        description="Staff dish and wine knowledge training — self-check quizzes and trainer-assigned learning paths.",
        future_path="/training",
        link="/training",  # genuinely mounted inside this application
    ),
    DomainDefinition(
        code="TIPS",
        display_name="Tips",
        description="Tip Distribution Rule configuration and the Tip Distribution Engine.",
        future_path="/tips",
        link="https://mxgsc3nwha.us-east-1.awsapprunner.com/",  # Tips's own, separate App Runner service
    ),
    DomainDefinition(
        code="COMPENSATION",
        display_name="Compensation",
        description=(
            "Prepare, review and approve employee compensation, then communicate it to the "
            "Payroll Provider and reconcile the result — manual handoff in both directions (V1)."
        ),
        future_path="/compensation",
        # A real operational application inside RF-One Web itself
        # (`compensation_routes.py`), genuinely mounted here — no longer a
        # provisional page. Gated the same way as every other destination
        # here: `require_domain_access("COMPENSATION")` — an enabled access
        # row, never the Home link alone.
        link="/compensation",
    ),
    DomainDefinition(
        code="SELECTION",
        display_name="Selection — Work in progress",
        description="Candidate screening, interviews, and hiring decisions. Work in progress.",
        future_path="/selection",
        # Deliberately NOT `03 Software/Selection/app.py`'s own URL: that
        # app has no real authentication (`/identity/switch` is explicitly
        # documented, in its own code and templates, as "not a login
        # screen") and stores uploaded résumés on local container disk
        # (lost on every redeploy) — publishing it directly would expose
        # real candidate PII with no access control. This points at the
        # SAME provisional-page mechanism as Compensation
        # (`selection_work_in_progress`, gated by `require_domain_access
        # ("SELECTION")`) until Selection has server-side auth safe to put
        # on AWS. See `03 Software/Infrastructure/README.md` for the full
        # verification and what remains to connect the real app securely.
        link="/selection",
    ),
    DomainDefinition(
        code="BANK",
        display_name="Bank Reconciliation",
        description=(
            "Manual CSV import from Chase and First Citizens, normalization into the canonical "
            "PaymentInstrument/FinancialTransaction ledger, and duplicate detection (V1)."
        ),
        future_path="/bank",
        # A real operational application inside RF-One Web itself
        # (`bank_routes.py`), genuinely mounted here — gated the same way
        # as every other destination: `require_domain_access("BANK")`.
        link="/bank",
    ),
)

DOMAINS_BY_CODE: dict[str, DomainDefinition] = {d.code: d for d in DOMAINS}
