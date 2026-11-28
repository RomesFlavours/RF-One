#!/usr/bin/env python
"""HTTP test for TIPS_PER_SITE_001 (Product Owner, 2026-11-27): Winter Park
and Mount Dora each configure their own Tips roles, rules and percentages,
chosen with the site selector at the top of every Tips page.

Throwaway SQLite database + Flask test client, like the other Tips HTTP
tests. Never touches AWS or any production database.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_per_site_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import select  # noqa: E402

import app as tips_app  # noqa: E402
from tips_test_session import signed_in_client  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import restaurant_role_service as role_svc  # noqa: E402


def _site(s, source, code, name):
    merchant = m.Merchant(source_system_id=source.id, source_merchant_id=code, name=name)
    s.add(merchant)
    s.flush()
    location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id=code,
                          name=name, currency="USD", timezone="America/New_York",
                          operating_day_cutoff_time=time(4))
    restaurant = m.Restaurant(name=name, default_currency="USD")
    s.add_all([location, restaurant])
    s.flush()
    s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    s.flush()
    return restaurant.id


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        if not condition:
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with tips_app.SessionFactory() as s:
            source = s.scalars(select(m.SourceSystem).where(m.SourceSystem.code == "CLOVER")).first()
            if source is None:
                source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
                s.add(source)
                s.flush()
            wp = _site(s, source, "WPTEST", "Test Site - WP")
            md = _site(s, source, "MDTEST", "Test Site - MD")
            s.commit()

        client = signed_in_client(tips_app)

        resp = client.get("/configuration")
        page = resp.get_data(as_text=True)
        check("Configuration opens (200)", resp.status_code == 200)
        check("the site selector lists both sites", 'name="site"' in page
              and "Test Site - WP" in page and "Test Site - MD" in page)
        check("with no choice yet, the first site (WP) is selected",
              f'<option value="{wp}" selected' in page)

        # Winter Park: its own roles and a 10% rule.
        client.post("/roles/new", data={"name": "Server", "active": "on"})
        client.post("/roles/new", data={"name": "Host", "active": "on"})
        # Mount Dora: chosen with ?site=, its own roles and a 5% rule.
        resp = client.get(f"/configuration?site={md}")
        page = resp.get_data(as_text=True)
        check("?site=<MD> selects Mount Dora", f'<option value="{md}" selected' in page)
        client.post("/roles/new", data={"name": "Server", "active": "on"})
        client.post("/roles/new", data={"name": "Host", "active": "on"})
        with tips_app.SessionFactory() as s:
            wp_roles = {r.name: r.id for r in role_svc.list_roles(s, wp)}
            md_roles = {r.name: r.id for r in role_svc.list_roles(s, md)}
        check("each site has its own Server and Host roles",
              set(wp_roles) == {"Server", "Host"} and set(md_roles) == {"Server", "Host"}
              and not set(wp_roles.values()) & set(md_roles.values()))

        resp = client.post("/distribution-rules/new", data={
            "source_role_id": str(md_roles["Server"]), "recipient_role_id": str(md_roles["Host"]),
            "calculation_base": "VOLUNTARY_TIP", "rate": "5.0000", "effective_from": "2026-01-01",
        })
        check("a Mount Dora rule is saved while Mount Dora is selected", resp.status_code in (302, 303))
        resp = client.post("/distribution-rules/new", data={
            "source_role_id": str(wp_roles["Server"]), "recipient_role_id": str(wp_roles["Host"]),
            "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000", "effective_from": "2026-01-01",
        }, follow_redirects=True)
        check("a Winter Park role cannot be used for a Mount Dora rule",
              resp.status_code in (200, 400) and "does not belong to this Restaurant" in resp.get_data(as_text=True))

        client.get(f"/configuration?site={wp}")
        resp = client.post("/distribution-rules/new", data={
            "source_role_id": str(wp_roles["Server"]), "recipient_role_id": str(wp_roles["Host"]),
            "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000", "effective_from": "2026-01-01",
        })
        check("a Winter Park rule is saved after switching back to Winter Park", resp.status_code in (302, 303))

        with tips_app.SessionFactory() as s:
            rules = {r.restaurant_id: r for r in s.scalars(select(m.TipDistributionRule))}
            rates = {rid: [v.rate for v in s.scalars(select(m.TipDistributionRuleVersion).where(
                m.TipDistributionRuleVersion.rule_id == rule.id))] for rid, rule in rules.items()}
        check("exactly one rule per site, each with its own percentage",
              set(rules) == {wp, md} and [float(x) for x in rates[wp]] == [10.0]
              and [float(x) for x in rates[md]] == [5.0], str(rates))

        page = client.get("/configuration").get_data(as_text=True)
        check("Winter Park's configuration names Winter Park, not Mount Dora",
              "<strong>Test Site - WP</strong>" in page and "<strong>Test Site - MD</strong>" not in page)

        resp = client.get(f"/distribution-rules/{rules[md].id}")
        check("opening Mount Dora's rule works (200)", resp.status_code == 200)
        page = client.get("/configuration").get_data(as_text=True)
        check("opening a Mount Dora rule switches the selection to Mount Dora",
              f'<option value="{md}" selected' in page)

        page = client.get("/configuration?site=999999").get_data(as_text=True)
        check("an unknown site is ignored (selection unchanged)", f'<option value="{md}" selected' in page)

        page = client.get(f"/calculate-tips?site={wp}").get_data(as_text=True)
        check("Calculate Tips follows the selected site", f'<option value="{wp}" selected' in page)
    finally:
        try:
            tips_app._engine.dispose()
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\nTips per site HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
