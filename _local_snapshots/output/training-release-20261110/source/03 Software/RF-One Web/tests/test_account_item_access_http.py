#!/usr/bin/env python
"""HTTP-level test for ACCOUNT_ITEM_ACCESS_001: access per Domain item, and
Organization as a Domain of its own.

Same convention as `test_accounts_and_domains_http.py`: a throwaway SQLite
database created and migrated BEFORE `app.py` is imported, Werkzeug's Flask
test client, `main()` returning an exit code. Never touches AWS or any
working database.

  A. whole Domain: every item of BANK opens, items added later included.
  B. selected items only: only those items open — pages AND operations,
     by direct URL too; the tabs show only them; Home enters on the first.
  C. no access: nothing of BANK or ORGANIZATION opens, even by direct URL.
  D. Organization for a non-administrator: it can be consulted, never
     changed (forms hidden, changes refused).
  E. previous accesses are kept: a row written without a scope (as every
     row before this task) is the whole Domain; an administrator without
     ORGANIZATION gets no bypass.
  F. the Access screen: hierarchical choice saved and shown back; "only
     selected items" with no item saves nothing.
  G. every route that belongs to an item is gated by its Domain.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_item_access_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from domain_registry import DOMAINS, DOMAINS_BY_CODE  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import organizational_responsibility_service as org_svc  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TAB_RE = re.compile(r'class="module-tab[^"]*"\s+href="([^"]+)"')
PASSWORD = "ItemAccess123!"
BANK_PAGES = {item.code: path for item, path in zip(DOMAINS_BY_CODE["BANK"].items, (
    "/bank", "/bank/review", "/bank/export", "/bank/sources", "/bank/ai-rules", "/bank/configuration",
    "/bank/instructions"))}
ORG_PAGES = {
    "chart": "/admin/organization", "positions": "/admin/org/positions",
    "process_ownerships": "/admin/org/process-ownerships", "fallback_policies": "/admin/org/fallback-policies",
    "coverage_check": "/admin/org/coverage-check", "attention": "/admin/org/attention",
    "ai_review": "/admin/org/ai-review",
}


def csrf_of(client, path="/") -> str:
    match = CSRF_RE.search(client.get(path).get_data(as_text=True))
    assert match, f"csrf_token not found on {path}"
    return match.group(1)


def login(username: str):
    client = web_app.app.test_client()
    resp = client.post("/login", data={"username": username, "password": PASSWORD, "csrf_token": csrf_of(client, "/login")})
    assert resp.status_code in (302, 303), f"login {username}: {resp.status_code}"
    return client


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        if not condition:
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    with SessionFactory() as s:
        def account(username, *, admin=False):
            a = account_service.create_account(s, username=username, display_name=username.title(),
                                               password=PASSWORD, status="ACTIVE", is_admin=admin)
            s.flush()
            return a.id

        admin_id = account("admin", admin=True)
        full_id = account("full")
        partial_id = account("partial")
        account("nobody")
        viewer_id = account("viewer")
        admin_no_org_id = account("adminnoorg", admin=True)
        legacy_id = account("legacy")
        for code in ("BANK", "ORGANIZATION"):
            account_service.set_domain_access(s, account_id=admin_id, domain_code=code, enabled=True, role_code=None,
                                              scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        account_service.set_domain_access(s, account_id=full_id, domain_code="BANK", enabled=True, role_code=None,
                                          scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        account_service.set_domain_access(s, account_id=viewer_id, domain_code="ORGANIZATION", enabled=True,
                                          role_code=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        account_service.set_domain_access(s, account_id=admin_no_org_id, domain_code="BANK", enabled=True,
                                          role_code=None)
        # A row as every row was written before this task: no scope given.
        account_service.set_domain_access(s, account_id=legacy_id, domain_code="BANK", enabled=True, role_code=None)
        position_id = org_svc.create_position(s, name="TEST Item Access Position").id
        s.commit()

    admin = login("admin")

    # ---- F: the Access screen ------------------------------------------------------------
    page = admin.get(f"/admin/accounts/{partial_id}/access").get_data(as_text=True)
    check("F: Access screen offers none / whole Domain / selected items for BANK",
          all(f'name="access_BANK" value="{v}"' in page for v in ("none", "all", "selected")))
    check("F: BANK items are listed under BANK (from the registry)",
          all(f'name="items_BANK" value="{i.code}"' in page for i in DOMAINS_BY_CODE["BANK"].items))
    check("F: Organization is assignable with its items",
          'name="access_ORGANIZATION" value="selected"' in page
          and all(f'name="items_ORGANIZATION" value="{c}"' in page for c in ORG_PAGES))
    check("F: a Domain without items offers no item choice (PROJECTS)",
          'name="access_PROJECTS" value="selected"' not in page and 'name="access_PROJECTS" value="all"' in page)

    csrf = csrf_of(admin, f"/admin/accounts/{partial_id}/access")
    resp = admin.post(f"/admin/accounts/{partial_id}/access", data={
        "csrf_token": csrf, "access_BANK": "selected", "access_ORGANIZATION": "all"})
    with SessionFactory() as s:
        rows = account_service.list_domain_access_for_account(s, partial_id)
    check("F: 'only selected items' with no item saves nothing", resp.status_code in (302, 303) and rows == [],
          f"{[(r.domain_code, r.enabled, r.scope) for r in rows]}")

    resp = admin.post(f"/admin/accounts/{partial_id}/access", data={
        "csrf_token": csrf, "access_BANK": "selected", "items_BANK": ["review", "export"],
        "access_ORGANIZATION": "selected", "items_ORGANIZATION": ["attention"]})
    check("F: selected items saved (redirect)", resp.status_code in (302, 303), str(resp.status_code))
    page = admin.get(f"/admin/accounts/{partial_id}/access").get_data(as_text=True)
    check("F: the saved choice is shown back (selected + ticked items)",
          re.search(r'name="access_BANK" value="selected"\s+checked', page) is not None
          and re.search(r'name="items_BANK" value="review"\s+checked', page) is not None
          and re.search(r'name="items_BANK" value="import"\s+checked', page) is None)

    # ---- A: whole Domain ----------------------------------------------------------------
    full = login("full")
    for code, path in BANK_PAGES.items():
        r = full.get(path)
        check(f"A: whole BANK opens {path}", r.status_code == 200, str(r.status_code))
    tabs = TAB_RE.findall(full.get("/bank/review").get_data(as_text=True))
    check("A: whole BANK shows every tab, in registry order", tabs == list(BANK_PAGES.values()), f"{tabs}")

    # ---- B: selected items only ---------------------------------------------------------
    partial = login("partial")
    for code, path in BANK_PAGES.items():
        r = partial.get(path)
        expected = 200 if code in ("review", "export") else 403
        check(f"B: selected BANK items — {path} answers {expected}", r.status_code == expected, str(r.status_code))
    tabs = TAB_RE.findall(partial.get("/bank/review").get_data(as_text=True))
    check("B: only the selected tabs are shown", tabs == ["/bank/review", "/bank/export"], f"{tabs}")
    csrf = csrf_of(partial, "/bank/review")
    for path in ("/bank/configuration/who", "/bank/upload", "/bank/ai-rules/save", "/bank/monthly/select",
                 "/bank/instruments/new"):
        r = partial.post(path, data={"csrf_token": csrf})
        check(f"B: operation of an unselected item refused by direct URL — POST {path}", r.status_code == 403,
              str(r.status_code))
    r = partial.get("/bank/whys/create-options")
    check("B: a helper shared by the whole Domain stays open", r.status_code != 403, str(r.status_code))
    home = partial.get("/").get_data(as_text=True)
    check("B: Home enters Bank on its first selected item", 'href="/bank/review"><strong>Bank</strong>' in home)
    check("B: Home enters Organization on its first selected item", 'href="/admin/org/attention"' in home)
    for code, path in ORG_PAGES.items():
        r = partial.get(path)
        expected = 200 if code == "attention" else 403
        check(f"B: selected ORGANIZATION items — {path} answers {expected}", r.status_code == expected,
              str(r.status_code))
    r = partial.get("/admin/organization/graph-data.json")
    check("B: the chart's data belongs to the chart item (403)", r.status_code == 403, str(r.status_code))

    # ---- C: no access ---------------------------------------------------------------------
    nobody = login("nobody")
    for path in list(BANK_PAGES.values()) + list(ORG_PAGES.values()) + [
            "/bank/whys/create-options", f"/admin/org/positions/{position_id}",
            f"/admin/organization/positions/{position_id}/fragment", "/admin/organization/graph-data.json"]:
        r = nobody.get(path)
        check(f"C: no access — GET {path} is 403", r.status_code == 403, str(r.status_code))
    csrf = csrf_of(nobody)
    for path in ("/bank/configuration/why", "/admin/org/positions/new", "/admin/org/process-ownerships/new"):
        r = nobody.post(path, data={"csrf_token": csrf})
        check(f"C: no access — POST {path} is 403", r.status_code == 403, str(r.status_code))
    home = nobody.get("/").get_data(as_text=True)
    check("C: Home shows neither Bank nor Organization", "/bank" not in home and "/admin/org" not in home)

    # ---- D: Organization for a non-administrator ------------------------------------------
    viewer = login("viewer")
    home = viewer.get("/").get_data(as_text=True)
    check("D: a non-admin granted ORGANIZATION sees the Organization card",
          'href="/admin/organization"' in home and "<div class=\"domain-name\">Organization</div>" in home)
    for path in list(ORG_PAGES.values()) + [f"/admin/org/positions/{position_id}",
                                             f"/admin/organization/positions/{position_id}/fragment",
                                             "/admin/organization/graph-data.json"]:
        r = viewer.get(path)
        check(f"D: non-admin consults {path} (200)", r.status_code == 200, str(r.status_code))
    detail = viewer.get(f"/admin/org/positions/{position_id}").get_data(as_text=True)
    check("D: Position page shows no change control to a non-admin",
          "<form" not in detail.split("<h1>", 1)[1] and "Assign Occupant" not in detail and "interview" not in detail)
    check("D: Process Ownerships shows no creation form to a non-admin",
          "New Process Ownership" not in viewer.get("/admin/org/process-ownerships").get_data(as_text=True))
    check("D: Positions list shows no 'New Position' to a non-admin",
          "New Position" not in viewer.get("/admin/org/positions").get_data(as_text=True))
    for path in ("/admin/org/positions/new", f"/admin/org/positions/{position_id}/interview"):
        r = viewer.get(path)
        check(f"D: non-admin cannot open the change form {path} (403)", r.status_code == 403, str(r.status_code))
    csrf = csrf_of(viewer)
    for path, data in (("/admin/org/positions/new", {"name": "Should not exist"}),
                       (f"/admin/org/positions/{position_id}/backup-required", {"backup_required": "on"}),
                       ("/admin/org/process-ownerships/new", {"position_id": position_id, "domain": "X", "process_name": "Y"}),
                       ("/admin/org/fallback-policies/new", {"fallback_position_id": position_id})):
        r = viewer.post(path, data={"csrf_token": csrf, **data})
        check(f"D: non-admin change refused — POST {path} (403)", r.status_code == 403, str(r.status_code))
    with SessionFactory() as s:
        check("D: nothing was changed by the refused requests",
              s.query(m.Position).count() == 1 and not s.get(m.Position, position_id).backup_required
              and s.query(m.ProcessOwnership).count() == 0 and s.query(m.OrganizationalFallbackPolicy).count() == 0)
    check("D: a non-admin still cannot manage accounts", viewer.get("/admin/accounts").status_code == 403)

    r = admin.get(f"/admin/org/positions/{position_id}").get_data(as_text=True)
    check("D: the administrator still sees the change controls", "Assign Occupant" in r and "interview" in r)
    csrf = csrf_of(admin)
    r = admin.post("/admin/org/positions/new", data={"csrf_token": csrf, "name": "TEST Admin Position"})
    check("D: the administrator can still change the organization", r.status_code in (302, 303), str(r.status_code))

    # ---- E: previous accesses kept, no bypass -------------------------------------------
    legacy = login("legacy")
    with SessionFactory() as s:
        row = account_service.list_domain_access_for_account(s, legacy_id)[0]
    check("E: a row written without a scope is the whole Domain", row.scope == m.DOMAIN_ACCESS_SCOPE_ALL)
    check("E: ... and opens every BANK item",
          all(legacy.get(p).status_code == 200 for p in BANK_PAGES.values()))
    admin_no_org = login("adminnoorg")
    check("E: an administrator without ORGANIZATION gets 403 — no is_admin bypass",
          admin_no_org.get("/admin/organization").status_code == 403)
    check("E: ... and no Organization card on Home",
          "/admin/organization" not in admin_no_org.get("/").get_data(as_text=True))
    check("E: Organization is no longer a Settings row",
          "Configure organization settings" not in admin.get("/").get_data(as_text=True))

    # ---- G: every route of an item is gated by its Domain --------------------------------
    ungated = []
    for rule in web_app.app.url_map.iter_rules():
        sample = re.sub(r"<[^>]+>", "1", rule.rule)
        for domain in DOMAINS:
            item = domain.item_for_path(sample)
            if item is None:
                continue
            view = web_app.app.view_functions[rule.endpoint]
            if getattr(view, "rfone_domain_gate", None) != domain.code:
                ungated.append(f"{rule.rule} ({domain.code}/{item.code})")
    check("G: every route owned by an item is gated by its Domain", not ungated, f"{ungated}")
    item_endpoints_ok = all(
        any(r.endpoint == i.endpoint for r in web_app.app.url_map.iter_rules())
        for d in DOMAINS for i in d.items)
    check("G: every item's navigation endpoint exists", item_endpoints_ok)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
