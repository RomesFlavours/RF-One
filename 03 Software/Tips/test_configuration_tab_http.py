#!/usr/bin/env python
"""CONFIGURATION_TAB_001 — Distribution Rules and Tips Configuration become
one Tips tab, "Configuration".

Proves:

  1. the Tips bar is Clover Acquisition, Calculate Tips, Saved Periods,
     Payment Control, Configuration (TIPS_NAVIGATION_STANDARD_001 order);
     no "Distribution Rules" or "Tips Configuration" tab;
  2. Configuration holds Distribution Rules, then General Configuration,
     with their former content;
  3. every former action still works and comes back to Configuration;
  4. the former URLs redirect to the matching section;
  5. breadcrumbs read RF-One > Tips > Configuration [> ...];
  6. the navigation follows Compensation's standard: breadcrumb first,
     header naming RF-One only, host audit under Calculate Tips, the same
     '›' separator.

Throwaway SQLite + Flask test client. Never touches AWS or Clover.

Usage:
    python test_configuration_tab_http.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import time
from types import SimpleNamespace

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_configuration_tab_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-configuration-tab-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.tips import review_mode_service as review_mode_svc  # noqa: E402


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with tips_app.SessionFactory() as s:
        source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        s.add(source)
        s.flush()
        merchant = m.Merchant(source_system_id=source.id, source_merchant_id="CFG-MERCH", name="CFG Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id="CFG-LOC",
                              name="Winter Park Test", currency="USD", timezone="America/New_York",
                              operating_day_cutoff_time=time(4, 0))
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="CFG Test Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        s.add_all([m.RestaurantRole(restaurant_id=restaurant.id, name="Server"),
                   m.RestaurantRole(restaurant_id=restaurant.id, name="Host")])
        s.commit()
        restaurant_id = restaurant.id
        server_id, host_id = [r.id for r in s.scalars(select(m.RestaurantRole).order_by(m.RestaurantRole.name.desc()))]

    client = tips_app.app.test_client()
    html = client.get("/configuration").get_data(as_text=True)

    # ---- 1. The Tips bar ----------------------------------------------------
    bar = re.search(r'<div class="nav-tabs">(.*?)</div>', html, re.S).group(1)
    tabs = re.findall(r'>([^<]+)</a>', bar)
    # TIPS_NAVIGATION_STANDARD_001 — the approved order, Configuration last;
    # Explain / Audit Host Tips is contextual (from Calculate Tips), not a tab.
    check("1. the bar is Clover Acquisition, Calculate Tips, Saved Periods, Payment Control, Configuration",
          tabs == ["Clover Acquisition", "Calculate Tips", "Saved Periods",
                   "Payment Control (Mercury Sandbox pilot)", "Configuration"], str(tabs))
    check("1. no 'Distribution Rules' tab", "Distribution Rules" not in tabs)
    check("1. no 'Tips Configuration' tab", "Tips Configuration" not in tabs and "Tips Configuration" not in html)
    check("1. Configuration is the active tab", 'class="active">Configuration</a>' in bar)

    # ---- 2. The two sections --------------------------------------------------
    d, g = html.find('id="distribution-rules"'), html.find('id="general-configuration"')
    check("2. Distribution Rules, then General Configuration", 0 <= d < g, f"{d} {g}")
    rules_part, general_part = html[d:g], html[g:]
    check("2. Distribution Rules keeps its content (describe a rule, rules list, new-rule form, roles)",
          "Describe the Tip Distribution Rule" in rules_part and 'action="/distribution-rules/new"' in rules_part
          and 'href="/roles"' in rules_part and "No Tip Distribution Rules configured yet" in rules_part)
    check("2. General Configuration keeps its content (Review Mode, Validation Mode, schedules, Run Calculation Now)",
          all(x in general_part for x in ("Review Mode", "Tips Validation Mode", "Calculation Schedule",
                                          "Payment Schedule", "Run Calculation Now")))

    # ---- 3. Actions still work and come back here ------------------------------
    resp = client.post("/distribution-rules/new", data={
        "source_role_id": str(server_id), "recipient_role_id": str(host_id), "calculation_base": "VOLUNTARY_TIP",
        "rate": "10.0000", "effective_from": "2026-01-01", "created_by": "tester",
    })
    check("3. creating a rule returns to Configuration > Distribution Rules",
          resp.status_code == 302 and resp.headers["Location"].endswith("/configuration#distribution-rules"),
          resp.headers.get("Location", ""))
    page = client.get("/configuration").get_data(as_text=True)
    check("3. the new rule is listed with its roles", "Server" in page and "Host" in page and "View / Edit / History" in page)
    with tips_app.SessionFactory() as s:
        rule = s.scalars(select(m.TipDistributionRule)).one()
        rule_id = rule.id
    resp = client.post(f"/distribution-rules/{rule_id}/toggle-active")
    check("3. activate/deactivate still works and returns to Configuration",
          resp.status_code == 302 and "/configuration#distribution-rules" in resp.headers["Location"])
    with tips_app.SessionFactory() as s:
        check("3. the rule's state changed", s.get(m.TipDistributionRule, rule_id).is_active is False)
    resp = client.post("/tips-configuration/review-mode", data={"review_mode": "AUTOMATIC"})
    check("3. Review Mode still saves and returns to Configuration > General Configuration",
          resp.status_code == 302 and resp.headers["Location"].endswith("/configuration#general-configuration"),
          resp.headers.get("Location", ""))
    with tips_app.SessionFactory() as s:
        check("3. the Review Mode value changed",
              review_mode_svc.get_review_mode(s, restaurant_id=restaurant_id) == m.TIPS_REVIEW_MODE_AUTOMATIC)

    # AI rule authoring renders the page itself (no redirect): both sections.
    ai = tips_app.rule_ai_svc
    real_interpret = ai.interpret_rule_statement
    try:
        def unavailable(*_a, **_k):
            raise ai.AIRuleAuthoringUnavailable("no provider in tests")
        ai.interpret_rule_statement = unavailable
        down = client.post("/distribution-rules/ai/interpret", data={"statement": "Hosts get 10%"}).get_data(as_text=True)
        check("3. AI unavailable: the Configuration page, both sections, with the message",
              "currently unavailable" in down and 'id="distribution-rules"' in down and 'id="general-configuration"' in down)
        ai.interpret_rule_statement = lambda *_a, **_k: SimpleNamespace(
            outcome=ai.OUTCOME_CLARIFICATION_NEEDED, clarification=SimpleNamespace(question="Which Host role?"))
        ask = client.post("/distribution-rules/ai/interpret", data={"statement": "Hosts get 10%"}).get_data(as_text=True)
        check("3. AI clarification: shown on the Configuration page, both sections",
              "Which Host role?" in ask and 'id="general-configuration"' in ask
              and 'class="active">Configuration</a>' in ask)
    finally:
        ai.interpret_rule_statement = real_interpret

    # ---- 4. Former URLs ---------------------------------------------------------
    old = client.get("/distribution-rules")
    check("4. /distribution-rules redirects to Configuration > Distribution Rules",
          old.status_code in (301, 302) and old.headers["Location"].endswith("/configuration#distribution-rules"))
    old = client.get("/tips-configuration")
    check("4. /tips-configuration redirects to Configuration > General Configuration",
          old.status_code in (301, 302) and old.headers["Location"].endswith("/configuration#general-configuration"))
    check("4. following a former URL lands on the one page", client.get("/tips-configuration", follow_redirects=True)
          .get_data(as_text=True).count('id="general-configuration"') == 1)

    # ---- 5. Breadcrumbs ----------------------------------------------------------
    crumbs = re.search(r'<nav class="breadcrumb".*?</nav>', html, re.S).group(0)
    check("5. RF-One > Tips > Configuration", '<a href="/">Tips</a>' in crumbs
          and '<span aria-current="page">Configuration</span>' in crumbs)
    detail = client.get(f"/distribution-rules/{rule_id}").get_data(as_text=True)
    dc = re.search(r'<nav class="breadcrumb".*?</nav>', detail, re.S).group(0)
    check("5. a rule: RF-One > Tips > Configuration > Rule #n",
          '<a href="/configuration">Configuration</a>' in dc and f"Rule #{rule_id}" in dc)
    roles = client.get("/roles").get_data(as_text=True)
    rc = re.search(r'<nav class="breadcrumb".*?</nav>', roles, re.S).group(0)
    check("5. roles: RF-One > Tips > Configuration > Roles", '<a href="/configuration">Configuration</a>' in rc)
    check("5. no page names Distribution Rules or Tips Configuration as its own level",
          ">Distribution Rules</a>" not in detail + roles and "Tips Configuration" not in detail + roles)

    # ---- 6. Navigation standard = Compensation (TIPS_NAVIGATION_STANDARD_001)
    check("6. the breadcrumb comes first, above the Tips menu (as in Compensation)",
          0 <= html.find('<nav class="breadcrumb"') < html.find('<div class="nav-tabs">'))
    check("6. the header names RF-One, not 'RF-One · Tips' (no second Tips navigation)",
          '<span class="brand-suffix">RF-One</span>' in html and "RF-One · Tips</span>" not in html)
    audit = client.get("/host-audit").get_data(as_text=True)
    ac = re.search(r'<nav class="breadcrumb".*?</nav>', audit, re.S).group(0)
    check("6. host audit: RF-One > Tips > Calculate Tips > Explain / Audit Host Tips",
          '<a href="/calculate-tips">Calculate Tips</a>' in ac
          and '<span aria-current="page">Explain / Audit Host Tips</span>' in ac, ac)
    audit_bar = re.search(r'<div class="nav-tabs">(.*?)</div>', audit, re.S).group(1)
    check("6. host audit highlights Calculate Tips, its parent", 'class="active">Calculate Tips</a>' in audit_bar)
    css = client.get("/static/css/rf-one.css").get_data(as_text=True)
    check("6. the breadcrumb separator is the same '›' (\\203A) as RF-One Web",
          '.breadcrumb li + li::before { content: "\\203A";' in css)

    print()
    print(f"Configuration tab HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
