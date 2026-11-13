#!/usr/bin/env python
"""HTTP-level test for the Wines functions and the View Level (Product
Owner, 2026-11-11).

Same convention as `test_account_item_access_http.py`: a throwaway SQLite
database created and migrated BEFORE `app.py` is imported, Werkzeug's Flask
test client, `main()` returning an exit code. Never touches AWS or any
working database.

  A. "View Calculator" only: only the calculator opens (page and prices),
     Home enters on it, the other Wines pages are closed by direct URL.
  B. "Wines" only: the three Wines pages open, the calculator does not.
  C. View Level: every page can be consulted, edit buttons are hidden and
     every change is refused by direct URL.
  D. the highest Level wins: a View grant plus a User role can change.
  E. the calculator uses the SAME formula and parameters and stores nothing.
  F. both permission screens offer View for Wines only.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_wines_access_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "wines-access-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from domain_registry import DOMAINS  # noqa: E402
from rfone_data_store import access_profiles as profiles  # noqa: E402
from rfone_data_store import legal_entity_service  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.restaurant_wines import wine_lists  # noqa: E402
from rfone_data_store.restaurant_wines.pricing import calculate_prices  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
PASSWORD = "WinesAccess123!"
WINES_PAGES = ("/restaurant/wines", "/restaurant/wines/availability", "/restaurant/wines/types")
CALCULATOR = "/restaurant/wines/calculator"


def csrf_of(client, path="/") -> str:
    match = CSRF_RE.search(client.get(path).get_data(as_text=True))
    assert match, f"csrf_token not found on {path}"
    return match.group(1)


def login(username: str):
    client = web_app.app.test_client()
    resp = client.post("/login", data={"username": username, "password": PASSWORD,
                                       "csrf_token": csrf_of(client, "/login")})
    assert resp.status_code in (302, 303), f"login {username}: {resp.status_code}"
    return client


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        if not condition:
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            def account(username, *, admin=False):
                a = account_service.create_account(s, username=username, display_name=username.title(),
                                                   password=PASSWORD, status="ACTIVE", is_admin=admin)
                s.flush()
                return a.id

            def grant(account_id, *, role=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL, items=None):
                account_service.set_domain_access(s, account_id=account_id, domain_code="WINES", enabled=True,
                                                  role_code=role, scope=scope, item_codes=items)

            legal_entity_service.create_legal_entity(s, legal_name="RFWP")
            admin_id = account("admin", admin=True)
            calc_id = account("calconly")
            manage_id = account("winesonly")
            viewer_id = account("viewer")
            mixed_id = account("mixed")
            grant(calc_id, scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, items=["calculator"])
            grant(manage_id, scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, items=["wines"])
            grant(viewer_id, role="view")
            grant(mixed_id, role="view")
            # D: a company role giving Wines at the User Level, on top of the direct View.
            company = profiles.CompanyContext(name="WP", kind="COMPANY")
            s.add(company)
            s.flush()
            area = profiles.save_area(s, name="FOH")
            role = profiles.save_role(s, name="Wine steward", area_ids=[area.id])
            profiles.save_permissions(s, role.id, {"WINES": {"mode": "all", "role": "", "items": []}}, DOMAINS)
            member = profiles.membership(s, f"account:{mixed_id}", company.id)
            profiles.assign_role(s, membership_id=member.id, role_id=role.id, area_id=area.id)
            view_role = profiles.save_role(s, name="Wine viewer", area_ids=[area.id])
            profiles.save_permissions(s, view_role.id, {"WINES": {"mode": "all", "role": "view", "items": []}},
                                      DOMAINS)
            company_id = company.id
            s.commit()

        # ---- A: View Calculator only ----------------------------------------------------
        c = login("calconly")
        page = c.get(CALCULATOR)
        check("A: calculator page opens", page.status_code == 200, str(page.status_code))
        html = page.get_data(as_text=True)
        check("A: only the Price Calculator tab is shown",
              "Price Calculator</a>" in html and "Wine List</a>" not in html and "Wine Types</a>" not in html)
        for path in WINES_PAGES:
            check(f"A: {path} is closed by direct URL", c.get(path).status_code == 403)
        home = c.get("/").get_data(as_text=True)
        check("A: Home enters Wines on the calculator", f'href="{CALCULATOR}"' in home)
        answer = c.get(f"{CALCULATOR}/prices?cost=20&value=1.2").get_json()
        with SessionFactory() as s:
            expected = calculate_prices(Decimal("20"), Decimal("1.2"), wine_lists.current_parameters(s))
            settings_before = (wine_lists.get_settings(s).coefficient_a, wine_lists.get_settings(s).log_base_b)
            lists_before = s.query(m.WineList).count()
        check("E: calculator prices equal the Wine list formula",
              answer == {"ok": True, "bottle": expected.bottle, "glass": expected.glass, "priceable": True},
              str(answer))
        check("E: a cost of $1 or less has no price",
              c.get(f"{CALCULATOR}/prices?cost=1&value=1").get_json().get("priceable") is False)
        check("E: an invalid Value is refused",
              c.get(f"{CALCULATOR}/prices?cost=20&value=0").get_json().get("ok") is False)
        with SessionFactory() as s:
            check("E: the calculator stores nothing",
                  s.query(m.WineList).count() == lists_before
                  and (wine_lists.get_settings(s).coefficient_a, wine_lists.get_settings(s).log_base_b)
                  == settings_before)

        # ---- B: Wines only ----------------------------------------------------------------
        w = login("winesonly")
        for path in WINES_PAGES:
            check(f"B: {path} opens with Wines", w.get(path).status_code == 200)
        check("B: the calculator is closed without View Calculator", w.get(CALCULATOR).status_code == 403)
        check("B: calculator prices are closed too", w.get(f"{CALCULATOR}/prices?cost=20&value=1").status_code == 403)
        check("B: no calculator tab", "Price Calculator</a>" not in w.get("/restaurant/wines").get_data(as_text=True))
        csrf = csrf_of(w, "/restaurant/wines/types")
        check("B: a User can still create a wine type",
              w.post("/restaurant/wines/types/new", data={"csrf_token": csrf, "standard_name": "Merlot"}).status_code
              == 200)

        # ---- C: View Level ----------------------------------------------------------------
        v = login("viewer")
        for path in WINES_PAGES + (CALCULATOR,):
            check(f"C: View can consult {path}", v.get(path).status_code == 200)
        types_html = v.get("/restaurant/wines/types").get_data(as_text=True)
        check("C: no New wine type / Edit with View",
              'id="type-new"' not in types_html and 'data-edit-type="' not in types_html and "Merlot" in types_html)
        avail_html = v.get("/restaurant/wines/availability").get_data(as_text=True)
        check("C: no New wine / Edit with View", 'id="wine-new"' not in avail_html and 'data-edit-wine="' not in avail_html)
        list_html = v.get("/restaurant/wines").get_data(as_text=True)
        check("C: no list buttons and no Save parameters with View",
              'id="list-new"' not in list_html and 'id="item-new"' not in list_html
              and "Save parameters" not in list_html and "View only" in list_html)
        csrf = csrf_of(v, "/restaurant/wines/types")
        refused = {
            "/restaurant/wines/types/new": {"standard_name": "Syrah"},
            "/restaurant/wines/availability/new": {"producer": "X"},
            "/restaurant/wines/lists/new": {"entity_id": "1", "effective_from": "2030-01-01", "mode": "EMPTY"},
            "/restaurant/wines/settings": {"coefficient_a": "2", "log_base_b": "900", "glass_divisor_g": "3.5"},
            "/restaurant/wines/items/1/delete": {},
        }
        for path, data in refused.items():
            check(f"C: View change refused by direct URL {path}",
                  v.post(path, data=dict(data, csrf_token=csrf)).status_code == 403)
        with SessionFactory() as s:
            check("C: nothing changed by the refused requests",
                  s.query(m.WineType).filter_by(standard_name="Syrah").count() == 0
                  and wine_lists.get_settings(s).coefficient_a == settings_before[0])

        # ---- D: highest Level wins --------------------------------------------------------
        with SessionFactory() as s:
            merged = profiles.effective_permissions(s, mixed_id, company_id=company_id)["WINES"]
            check("D: View + User role merges to User", merged["role_code"] is None, str(merged))
            only_view = profiles.effective_permissions(s, viewer_id, company_id=None)["WINES"]
            check("D: View alone stays View", only_view["role_code"] == "view", str(only_view))
        mx = login("mixed")
        with mx.session_transaction() as browser:
            browser["rfone_company_context"] = company_id
        csrf = csrf_of(mx, "/restaurant/wines/types")
        check("D: the User role lets the person change despite the direct View",
              mx.post("/restaurant/wines/types/new", data={"csrf_token": csrf, "standard_name": "Syrah"}).status_code
              == 200)

        # ---- F: permission screens ------------------------------------------------------
        a = login("admin")
        access = a.get(f"/admin/accounts/{viewer_id}/access").get_data(as_text=True)
        wines_box = access.split('data-domain="WINES"')[1].split("</fieldset>")[0]
        bank_box = access.split('data-domain="BANK"')[1].split("</fieldset>")[0]
        check("F: direct access offers View for Wines, selected", 'value="view" selected' in wines_box)
        check("F: direct access lists the two Wines functions",
              'value="wines"' in wines_box and 'value="calculator"' in wines_box and "View Calculator" in wines_box)
        check("F: direct access offers no View elsewhere", 'value="view"' not in bank_box)
        roles = a.get("/admin/roles?tab=roles").get_data(as_text=True)
        role_wines = roles.split('data-domain="WINES"')[1].split("</fieldset>")[0]
        role_bank = roles.split('data-domain="BANK"')[1].split("</fieldset>")[0]
        check("F: role permissions offer View for Wines only",
              '<option value="view">View</option>' in role_wines and 'value="view"' not in role_bank)
        with SessionFactory() as s:
            try:
                profiles.save_permissions(s, role.id, {"BANK": {"mode": "all", "role": "view", "items": []}}, DOMAINS)
                refused_elsewhere = False
            except ValueError:
                refused_elsewhere = True
            s.rollback()
        check("F: View is refused for a Domain that does not offer it", refused_elsewhere)
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
