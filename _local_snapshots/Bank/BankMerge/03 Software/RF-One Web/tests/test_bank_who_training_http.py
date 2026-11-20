#!/usr/bin/env python
"""HTTP test for WHO Pattern Training (BANK_WHO_TRAINING_001), on an ISOLATED COPY of the local database.

The person's examples (selected movements, WHO, highlighted WHO, variable parts) become a deterministic
WHO rule built by code (no AI); the rule is tested on every movement, the examples apart from the
additional ones; wrong interceptions are excluded by a separating literal; single-movement
identifications never become a rule; approval is explicit and nothing changes a movement's decisions.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)
_SOURCE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
if not _SOURCE.exists():
    print("SKIPPED: no local Bank database to copy.")
    sys.exit(0)
_FOLDER = tempfile.mkdtemp(prefix="rfone_who_training_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_src = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True)
_dst = sqlite3.connect(_COPY)
_src.backup(_dst)
_dst.close()
_src.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "who-training-test-secret"
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"

import app as web_app  # noqa: E402
import bank_who_training as wt  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import flow  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')


def decisions(db):
    return sorted(tuple(r) for r in db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.explanation_id,
                                                      m.FinancialTransaction.description_original)).all()), \
        db.scalar(select(func.count(m.BankTransactionExplanation.id)))


def main() -> int:
    passed, failed = [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:400]}]"))

    # --- the rule derived from one example (code only) ---------------------------------------------------
    d = "Zelle payment to Alice Martini JPM99cxzwg7b"
    spec, who = wt.derive(d, [d.index("Alice"), d.index(" JPM")], [[d.index("JPM"), len(d)]])
    check("1. Zelle: highlighted name + variable reference -> anchored rule reading the name",
          who == "ALICE MARTINI" and spec["start"] == "Zelle payment to " and spec.get("prefix") == "Zelle"
          and spec["end_mode"] == "last_code" and flow.extract(spec, "Zelle payment to Tatiana Ceban JPM99abc") == "TATIANA CEBAN", spec)
    a = "ORIG CO NAME:PAYPAL        ORIG ID:PAYPALSI77 DESC DATE:260101"
    spec_a, who_a = wt.derive(a, [a.index("PAYPAL"), a.index("PAYPAL") + 6], [])
    check("2. ACH: the name glued to its label is read; it ends at the next fixed text",
          who_a == "PAYPAL" and spec_a["start"] == "ORIG CO NAME:" and spec_a["end_markers"] == ["ORIG"]
          and flow.extract(spec_a, "ORIG CO NAME:CLOVER FEES   ORIG ID:1") == "CLOVER FEES", spec_a)
    p = "POS SIG 03/19 VISA #5363 MILLER HARDWARE 5125 WINTER PARK FL"
    spec_p, who_p = wt.derive(p, [p.index("MILLER"), p.index(" 5125")], [[p.index("03/19"), p.index("03/19") + 5],
                                                                          [p.index("#5363") + 1, p.index("#5363") + 5],
                                                                          [p.index("5125"), p.index("5125") + 4]])
    check("3. POS: variable date and card number become placeholders; a variable number ends the WHO",
          who_p == "MILLER HARDWARE" and spec_p["start"] == "POS SIG {date} VISA #{number} " and spec_p["end_markers"] == [" {number}"]
          and flow.extract(spec_p, "POS SIG 11/02 VISA #0632 ACE HARDWARE 77 ORLANDO FL") == "ACE HARDWARE", spec_p)
    try:
        wt.derive("BAR WINTER 5", [0, 3], [[4, 10]])
        refused = False
    except ValueError:
        refused = True
    check("4. a variable part made of letters only is refused (no guessing)", refused)

    # --- the page --------------------------------------------------------------------------------------
    with SessionFactory() as db:
        before = decisions(db)
        account_service.create_account(db, username="wt_operator", display_name="wt_operator", password="OperatorPass123!",
                                       status="ACTIVE", is_admin=False)
        db.commit()
        op = db.query(m.RFOneAccount).filter_by(username="wt_operator").one()
        account_service.set_domain_access(db, account_id=op.id, domain_code="BANK", enabled=True, role_code=None,
                                          scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()
        rules_before = db.scalar(select(func.count(m.BankAiRule.id)))
    client = web_app.app.test_client()
    client.post("/login", data={"username": "wt_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    rules_page = client.get("/bank/ai-rules").data.decode()
    page = client.get("/bank/who-training").data.decode()
    csrf = BANK_CSRF_RE.search(page).group(1)
    # BANK_WHO_RULES_001: out of the main path (no link from Rules and profiles), still reachable by its address.
    check("5. the page is out of the main path, still reachable, and shows its path",
          'href="/bank/who-training"' not in rules_page and "WHO Pattern Training" in page
          and 'href="/bank/ai-rules">Rules and profiles' in page)
    data = client.get("/bank/who-training/data").get_json()
    mv = data["movements"]
    keys = [r["description"].strip().casefold() for r in mv]
    check("6. every movement is listed, alphabetically by description, with Source, date, amount",
          len(mv) == len(before[0]) and keys == sorted(keys) and all(r["source"] and r["date"] for r in mv), len(mv))

    zelle = [r for r in mv if r["description"].startswith("Zelle payment to Alice Martini JPM")]
    other = [r for r in mv if r["description"].startswith("Zelle payment to ") and "JPM" in r["description"]
             and "Alice Martini" not in r["description"]]
    z = zelle[0]["description"]
    who_name = "Alice Martini"   # the WHO is the name the rule reads (an existing WHO is reused)
    created = client.post("/bank/who-training/who", data={"csrf_token": csrf, "name": who_name}).get_json() or {}
    resp = client.post("/bank/who-training/examples", data={
        "csrf_token": csrf, "ids": ",".join(str(r["id"]) for r in zelle), "who": created.get("who", ""),
        "focus": zelle[0]["id"], "span": json.dumps([z.index("Alice"), z.index(" JPM")]),
        "variables": json.dumps([[z.index("JPM"), len(z)]])})
    check("7. selected movements are saved as examples with their WHO; the WHO was created (no duplicate)",
          resp.status_code == 200 and created.get("who"), resp.data[:200])
    ext = [r for r in mv if r["description"].startswith("CHECK ")][:1]
    client.post("/bank/who-training/examples", data={"csrf_token": csrf, "ids": str(ext[0]["id"]), "external": "yes",
                                                     "who": created["who"]})
    prop = client.post("/bank/who-training/propose", data={"csrf_token": csrf}).get_json() or {}
    data = client.get("/bank/who-training/data").get_json()
    proposals = data["proposals"]
    check("8. one rule is built from the examples; the external-knowledge example is not used",
          prop.get("added") == 1 and len(proposals) == 1 and proposals[0]["from_examples"] == [zelle[0]["id"]], proposals)
    full = client.get(f"/bank/who-training/proposals/{proposals[0]['id']}").get_json()["proposal"]["check"]
    rows = full["rows"]
    check("9. the rule is tested on every movement: examples apart from the additional ones",
          full["examples"] == len(zelle) and full["examples_agree"] == len(zelle) and full["additional"] >= len(other)
          and all(r["example"] for r in rows[:len(zelle)]), {k: full[k] for k in ("selected", "examples", "additional")})
    wrong = [r for r in rows if not r["example"] and "Tatiana" in r["description"]]
    resp = client.post(f"/bank/who-training/proposals/{proposals[0]['id']}/exclude",
                       data={"csrf_token": csrf, "ids": ",".join(str(r["id"]) for r in wrong)}).get_json() or {}
    full2 = client.get(f"/bank/who-training/proposals/{proposals[0]['id']}").get_json()["proposal"]
    check("10. wrong interceptions are excluded by a separating literal and the rule is tested again",
          resp.get("ok") and resp["after"] == resp["before"] - len(wrong) and "Tatiana" in " ".join(full2["spec"].get("exclude", []))
          and not any("Tatiana" in r["description"] for r in full2["check"]["rows"]), resp)
    s = data["summary"]
    check("11. the summary separates confirmed, single-movement, rule-read and to-examine; proposals not counted",
          s["confirmed"] == len(zelle) + 1 and s["single"] == 1 and s["proposals_pending"] == 1
          and s["to_examine"] == s["movements"] - s["known"], s)
    singles = [r for r in data["movements"] if r["example"] and r["example"].get("external")]
    check("12. the external-knowledge identification is kept for that movement only", [r["id"] for r in singles] == [ext[0]["id"]])
    with SessionFactory() as db:
        check("13. nothing changed on the movements before approval; no rule created", decisions(db) == before
              and db.scalar(select(func.count(m.BankAiRule.id))) == rules_before)
    no = client.post(f"/bank/who-training/proposals/{proposals[0]['id']}/approve", data={"csrf_token": csrf})
    yes = client.post(f"/bank/who-training/proposals/{proposals[0]['id']}/approve", data={"csrf_token": csrf, "confirm": "yes"})
    with SessionFactory() as db:
        rule_id = (client.get("/bank/who-training/data").get_json()["proposals"][0]).get("rule_id")
        active = [r.id for r, v, sp in flow.entries(db) if flow.kind((r, v, sp)) == "EXTRACTOR"]
        check("14. approval needs confirmation; then the rule is an active WHO extraction rule",
              no.status_code == 409 and yes.status_code == 200 and rule_id in active
              and db.scalar(select(func.count(m.BankAiRule.id))) == rules_before + 1, (no.status_code, yes.status_code, rule_id))
        check("15. no movement, WHO decision, WHY or WHAT changed", decisions(db) == before)
    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        try:
            from db import _engine
            _engine.dispose()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(code)
