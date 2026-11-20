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
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Where Tips's own home page is served — a path on this host by default.
TIPS_HOME_URL = (os.environ.get("RFONE_TIPS_URL") or "").strip() or "/tips/"


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
)

DOMAINS_BY_CODE: dict[str, DomainDefinition] = {d.code: d for d in DOMAINS}
