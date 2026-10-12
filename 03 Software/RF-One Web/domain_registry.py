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
    service;
  - Tips is its own App Runner service, published on the SAME host as
    this application under `/tips/` (one CloudFront entry in front of both,
    UI_NAVIGATION_AND_LOCAL_TIME_001) so both share the RF-One login.
    `RFONE_TIPS_URL` overrides that address (e.g. a local Tips on another
    port);
  - `None` for a Domain not actually published anywhere yet — the Home
    page renders it as a non-clickable "Not yet available" card rather
    than a link to a destination that does not exist.

`items` (ACCOUNT_ITEM_ACCESS_001) is the ONE list of a Domain's functional
items — the sections its own navigation shows (Bank's tabs, Organization's
pages). The same list drives that navigation, the item choices in
Settings › Accounts › Access, and the check made on every route of the
Domain (`require_domain_access`), so an item hidden from someone is also
closed to them by direct URL. An item owns the URL paths listed in
`paths` (that path, or anything below it) and `exact_paths` (that path
only); a Domain path no item owns is a helper shared by the whole Domain
(e.g. Bank's WHO/WHY pickers, used from several sections) and needs only
the Domain. A Domain without items is granted whole or not at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Where Tips's own home page is served — a path on this host by default.
TIPS_HOME_URL = (os.environ.get("RFONE_TIPS_URL") or "").strip() or "/tips/"


@dataclass(frozen=True)
class DomainItem:
    code: str
    label: str
    endpoint: str  # the item's own page, for navigation (`url_for`)
    paths: tuple[str, ...] = ()
    exact_paths: tuple[str, ...] = ()

    def owns(self, path: str) -> bool:
        return path in self.exact_paths or any(path == p or path.startswith(p + "/") for p in self.paths)


@dataclass(frozen=True)
class DomainDefinition:
    code: str
    display_name: str
    description: str
    future_path: str
    link: str | None = None
    items: tuple[DomainItem, ...] = field(default=())

    def item(self, code: str) -> DomainItem | None:
        return next((i for i in self.items if i.code == code), None)

    def item_for_path(self, path: str) -> DomainItem | None:
        return next((i for i in self.items if i.owns(path)), None)


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
        link=TIPS_HOME_URL,  # Tips's own App Runner service, same host under /tips/
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
        display_name="Selection",
        description="Candidate screening, interviews, and hiring decisions.",
        future_path="/selection",
        # SELECTION_AWS_PUBLISH_001 — on RF-One's official host, CloudFront
        # sends `/selection` and `/selection/*` to the Selection service
        # (`rfone-selection`), which requires the SAME RF-One login and the
        # SAME SELECTION Domain access as this app, ties its acting identity
        # to the account and keeps résumés in a private S3 bucket. This
        # app's own `/selection` route is only reached when RF-One Web runs
        # alone (local development). See `03 Software/Infrastructure/README.md`.
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
        # The Bank tabs, in the Product Owner's order (2026-10-05,
        # BANK_SOURCE_AND_IMPORT_REVIEW_001): the monthly work first —
        # import, review, export — then Source, AI Rules, Configuration and
        # the explanation. `_bank_macros.html` `module_nav` renders exactly
        # this list. Not owned by any item (shared by the whole Domain):
        # the WHO/WHY pickers and creation dialogs (/bank/whos, /bank/whys,
        # /bank/who-rules, /bank/manual-reconciliation), used from several tabs.
        items=(
            DomainItem("import", "Import and Review", "bank_home", exact_paths=("/bank",),
                       paths=("/bank/upload", "/bank/import", "/bank/batches", "/bank/monthly")),
            DomainItem("review", "Review Transactions", "bank_review",
                       paths=("/bank/review", "/bank/reconciliation", "/bank/transactions")),
            DomainItem("export", "Monthly Export", "bank_export", paths=("/bank/export",)),
            DomainItem("source", "Source", "bank_sources",
                       paths=("/bank/sources", "/bank/source-profiles", "/bank/instruments", "/bank/entities",
                              "/bank/accounting-dedup")),
            DomainItem("ai_rules", "AI Rules", "bank_ai_rules", paths=("/bank/ai-rules",)),
            DomainItem("configuration", "Configuration", "bank_configuration", paths=("/bank/configuration",)),
            DomainItem("instructions", "Instructions", "bank_instructions", paths=("/bank/instructions",)),
        ),
    ),
    DomainDefinition(
        code="CLOVER_ACQUISITION",
        display_name="Clover Acquisition",
        description="Start Sync Now and Historical Backfill from Clover, and follow their progress.",
        future_path="/clover-acquisition",
        # Product Owner decision (CLOVER_ACQUISITION_IDENTITY_001,
        # 2026-09-26): the access that allows starting a manual Clover
        # acquisition is a dedicated entry of THIS list, granted account by
        # account through the existing access screen — not a new role or
        # hierarchy. It gates a platform capability (the Clover Technical
        # Connector), not a business Domain; it is listed here because this
        # list is where RF-One access codes live. Shown on Home under
        # Administration. `clover_acquisition_routes.py`.
        link="/clover-acquisition",
    ),
    DomainDefinition(
        code="WINES",
        display_name="Wines",
        description=(
            "Restaurant wine types, the catalog of purchasable wines, and each Entity's "
            "Wine lists with their prices."
        ),
        future_path="/restaurant/wines",
        # Restaurant module (RESTAURANT_WINES_FIRST_RELEASE_001) mounted in
        # this application (`restaurant_wines_routes.py`), gated by
        # `require_domain_access("WINES")`.
        link="/restaurant/wines",
    ),
    DomainDefinition(
        code="PROJECTS",
        display_name="Project Management",
        description="Projects with their chapters, tasks and subtasks, prerequisites and a printable Gantt (MyRF).",
        future_path="/projects",
        # MyRF Project Management (Product Owner approval, 2026-10-12): a
        # Home card granted account by account through the existing access
        # screen. `projects_routes.py`; see
        # `01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md`.
        link="/projects",
    ),
    DomainDefinition(
        code="ORGANIZATION",
        display_name="Organization",
        description="Positions, occupants and backups, Process Ownership, coverage and Attention routing.",
        future_path="/admin/organization",
        # ACCOUNT_ITEM_ACCESS_001 (2026-10-12): the Organization pages, until
        # then an administrators' Settings entry, become a Domain of their
        # own, granted account by account. The URLs stay where they were
        # (/admin/organization, /admin/org/...). Entering the Domain lets an
        # account consult it; every change to the organization stays reserved
        # to administrators (`organizational_responsibility_routes.py`).
        # Future destination of evaluations — see `10 System/Organizational
        # Responsibility and Attention Management/README.md`.
        link="/admin/organization",
        items=(
            DomainItem("chart", "Organization Chart", "admin_organization",
                       exact_paths=("/admin/organization", "/admin/organization/graph-data.json", "/admin/org/chart"),
                       paths=("/admin/organization/positions",)),
            DomainItem("positions", "Positions", "admin_org_positions", paths=("/admin/org/positions",)),
            DomainItem("process_ownerships", "Process Ownerships", "admin_org_process_ownerships",
                       paths=("/admin/org/process-ownerships",)),
            DomainItem("fallback_policies", "Organizational Fallback Policy", "admin_org_fallback_policies",
                       paths=("/admin/org/fallback-policies",)),
            DomainItem("coverage_check", "Full Coverage Check", "admin_org_coverage_check",
                       paths=("/admin/org/coverage-check",)),
            DomainItem("attention", "Attention Items", "admin_org_attention", paths=("/admin/org/attention",)),
            DomainItem("ai_review", "AI Consistency Review (boundary)", "admin_org_ai_review",
                       paths=("/admin/org/ai-review",)),
        ),
    ),
)

DOMAINS_BY_CODE: dict[str, DomainDefinition] = {d.code: d for d in DOMAINS}
