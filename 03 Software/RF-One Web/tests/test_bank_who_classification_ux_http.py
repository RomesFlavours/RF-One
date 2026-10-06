"""WHO Classification UX and Manual Only WHO (BANK_WHO_MANUAL_ONLY_001).

On a throwaway database migrated to head, with a small synthetic population,
proves: the Classification frame is the Bank frame; the WHO list is ordered
Needs Rule / Has Rule / Manual Only, alphabetical inside each group; Manual
Only persists, removes the Rule action, is refused by Apply, is ignored by
WHO-Rule discovery but not by structural or WHY discovery, leaves manual
reconciliation available, is undone cleanly, and never silently coexists
with an active WHO Rule; the wider Rule modal groups every selectable WHY
by its WHY navigation group; Apply returns to #who-classification with the
same filters; and rules, queues and accounting are otherwise unchanged.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_who_ux_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-who-ux-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import pattern_discovery as pd  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402
from rfone_data_store.bank_reconciliation import who_rules  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
ROW_RE = re.compile(r'<tr data-group="([A-Z_]*)">\s*<td data-label="WHO">([^<\n]+)')
CSS_PATH = os.path.join(APP_DIR, "static", "css", "rf-one.css")
JS_PATH = os.path.join(APP_DIR, "static", "js", "bank-who-rule.js")


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        account_service.create_account(s, username="whoux", display_name="Who UX",
                                       password="WhoUxRules123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="whoux").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="Who UX LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="UX Checking", institution="CHASE", last_four="0022",
                                       currency="USD")
        s.add(checking)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="6" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        food = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.code == "FOOD_PURCHASES")).one()
        linen_why = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.code == "JANITORIAL_CLEANING")).one()

        def who(name):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE",
                                 optional_notes="Canonical WHO.")
            s.add(o)
            s.flush()
            return o

        W = {n: who(n) for n in ("Zeta Diner", "alpha cafe", "Mango Grill", "Beta Linen", "Omega Payroll",
                                 "Kappa Bistro", "Delta Trattoria", "ALICE BAKER", "BRUNO CARUSO", "CARLA DIAZ")}
        for name, phrase in (("Beta Linen", "BETA LINEN SVC"), ("Omega Payroll", "OMEGA PAYROLL"),
                             ("Delta Trattoria", "DELTA TRATTORIA")):
            recognition.create_or_reuse_rule(
                s, match_type="CONTAINS_TEXT", normalized_pattern=phrase, occurrence_id=W[name].id,
                transaction_reason_id=None, payment_instrument_id=None, direction=None, auto_apply_enabled=True,
                created_from_transaction_id=None)
        s.add(m.BankOccurrenceReasonAssociation(occurrence_id=W["Beta Linen"].id, transaction_reason_id=linen_why.id,
                                                active=True))
        seq = [0]

        def tx(description, day, *, who_=None, why_=None):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=day, transaction_date=day, description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"whoux-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if who_ is not None:
                recognition._create_decision_row(
                    s, t, occurrence_id=who_.id, transaction_reason_id=why_.id if why_ else None,
                    recognition_rule_id=None, decision_source="HUMAN", decision_status="HUMAN_CONFIRMED",
                    confidence=None, explanation_notes="seed")
            return t

        gap_ids = []
        for i, day in enumerate(date(2025, mo, 12) for mo in range(1, 10)):
            # Structural pattern: Zelle "to <name> REF77…", human truth, one of them Mango Grill.
            for j, name in enumerate(("ALICE BAKER", "BRUNO CARUSO", "CARLA DIAZ", "Mango Grill")):
                tx(f"Zelle payment to {name.title()} REF77{i}{j}zz", day, who_=W[name], why_=food)
            # Mango Grill card spend: human WHO + WHY early, gap later -> a WHO-Rule candidate.
            if i < 4:
                tx(f"MANGO GRILL ORLANDO {i}8{i}", day, who_=W["Mango Grill"], why_=food)
            else:
                gap_ids.append(tx(f"MANGO GRILL ORLANDO {i}8{i}", day).id)
            tx(f"ZETA DINER POS {i}9{i}", day)
        # Last transaction: a same-day tie (the greater id wins) and a canonical
        # WHO whose merged (INACTIVE) WHO still holds the family's latest one.
        W["Tie Bistro"] = who("Tie Bistro")
        tie_first = tx("TIE BISTRO LUNCH 001", date(2025, 10, 1), who_=W["Tie Bistro"]).id
        tie_second = tx("TIE BISTRO DINNER 002", date(2025, 10, 1), who_=W["Tie Bistro"]).id
        W["Family Cafe"] = who("Family Cafe")
        tx("FAMILY CAFE ORLANDO 01", date(2025, 10, 1), who_=W["Family Cafe"])
        merged = m.BankOccurrence(canonical_name="FAMILY CAFE OLD SPELLING", occurrence_type_id=counterparty.id,
                                  status="INACTIVE", optional_notes="Merged into 'Family Cafe'.")
        s.add(merged)
        s.flush()
        s.add(m.BankOccurrenceAlias(occurrence_id=W["Family Cafe"].id, alias_text=merged.canonical_name,
                                    alias_key="FAMILY CAFE OLD SPELLING", source_family=who_rules.MERGED_WHO_NAME,
                                    source="HUMAN"))
        long_text = ("POS DEBIT FAMILY CAFE OLD SPELLING STORE 0042 ORLANDO FL CARD 1234 REF 9F8E7D6C5B4A "
                     "TERMINAL 77 AUTH 556677 SEQ 0001 MERCHANT CATEGORY 5812 EATING PLACES")
        family_latest = tx(long_text, date(2025, 10, 3), who_=merged).id
        s.commit()
        ids = {k: v.id for k, v in W.items()}
        food_id = food.id
        linen_why_id = linen_why.id
        delta_rule_id = s.scalars(select(m.BankRecognitionRule.id).where(
            m.BankRecognitionRule.occurrence_id == ids["Delta Trattoria"])).one()
        general_before = [(r.id, r.start_marker, r.end_marker, r.status) for r in s.scalars(select(m.BankGeneralRule))]
        snapshot = lambda: {t.id: (t.amount_minor, t.posting_date, t.explanation_id, t.accounting_status)  # noqa: E731
                            for t in s.scalars(select(m.FinancialTransaction))}
        accounting_before = snapshot()
        queues_before = review_queues.counts(s, review_queues.ReviewFilters())
        candidates_before, _ = pd.find_candidates(s)

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "whoux", "password": "WhoUxRules123!", "csrf_token": csrf})

    def page(url="/bank/classification"):
        return client.get(url).data.decode()

    def rows(html):
        return [(g, n.strip()) for g, n in ROW_RE.findall(html)]

    def manual(who_id, value, **extra):
        html = page()
        # Exactly what a row button sends: the shared form's fields, its own
        # WHO, and the direction in its formaction query.
        data = {"csrf_token": CSRF_RE.search(html).group(1), "occurrence_id": who_id,
                "return_to": "/bank/classification#who-classification", **extra}
        return client.post(f"/bank/who-rules/manual-only?manual_only={'1' if value else '0'}", data=data)

    # ------------------------------------------------------------------
    # LAYOUT (1-2)
    # ------------------------------------------------------------------
    html = page()
    review = page("/bank/review")
    wrap = lambda h: re.search(r'<div class="wrap ([^"]*)">', h).group(1).strip()  # noqa: E731
    check("1. Classification uses the normal Bank frame width (wrap-wide, like Review)",
          wrap(html) == "wrap-wide" == wrap(review), f"{wrap(html)!r} vs {wrap(review)!r}")
    check("2. the WHO Classification anchor exists, after Classification Learning and General Rules",
          html.count('id="who-classification"') == 1
          and html.index('id="classification-learning"') < html.index('id="general-rules"') < html.index('id="who-classification"'))

    # ------------------------------------------------------------------
    # MANUAL ONLY (8-9, 15) + ORDER (3-7)
    # ------------------------------------------------------------------
    response = manual(ids["Mango Grill"], True)
    manual(ids["Kappa Bistro"], True)
    with SessionFactory() as s:
        flags = {o.canonical_name: o.manual_only for o in s.scalars(select(m.BankOccurrence))}
    check("8. Manual Only persists on the canonical WHO (and redirects back to #who-classification)",
          flags["Mango Grill"] and flags["Kappa Bistro"] and not flags["Zeta Diner"]
          and response.status_code == 302 and response.headers["Location"].endswith("/bank/classification#who-classification"))

    html = page()
    listed = rows(html)
    groups = [g for g, _ in listed]
    names_in = lambda grp: [n for g, n in listed if g == grp]  # noqa: E731
    check("3. WHO without a Rule come before WHO with a Rule",
          "NEEDS_RULE" in groups and "HAS_RULE" in groups
          and max(i for i, g in enumerate(groups) if g == "NEEDS_RULE") < min(i for i, g in enumerate(groups) if g == "HAS_RULE"),
          str(listed))
    check("4. alphabetical inside Needs Rule (case-insensitive)",
          names_in("NEEDS_RULE") == sorted(names_in("NEEDS_RULE"), key=str.upper)
          and names_in("NEEDS_RULE")[:2] == ["ALICE BAKER", "alpha cafe"], str(names_in("NEEDS_RULE")))
    check("5. alphabetical inside Has Rule",
          names_in("HAS_RULE") == ["Beta Linen", "Delta Trattoria", "Omega Payroll"], str(names_in("HAS_RULE")))
    check("6. Manual Only comes last",
          groups and groups[-1] == "MANUAL_ONLY"
          and min(i for i, g in enumerate(groups) if g == "MANUAL_ONLY") > max(i for i, g in enumerate(groups) if g != "MANUAL_ONLY"))
    check("7. alphabetical inside Manual Only, with group headings and counts",
          names_in("MANUAL_ONLY") == ["Kappa Bistro", "Mango Grill"]
          and re.search(r"Needs Rule <span class=\"who-group-count\">\(\d+\)</span>", html)
          and "Has Rule <span class=\"who-group-count\">(3)</span>" in html
          and "Manual Only <span class=\"who-group-count\">(2)</span>" in html, str(names_in("MANUAL_ONLY")))

    def row_html(h, name):
        start = h.index(f'<td data-label="WHO">{name}')
        return h[start:h.index("</tr>", start)]

    mango_row = row_html(html, "Mango Grill")
    csrf = CSRF_RE.search(html).group(1)
    refused = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "occurrence_id": ids["Mango Grill"],
        "instruction": "Dove nella descrizione trovi MANGO GRILL il WHO è Mango Grill",
        "return_to": "/bank/classification#who-classification"})
    with SessionFactory() as s:
        mango_rules = who_rules.active_who_rules(s, ids["Mango Grill"])
    check("9. Rule action unavailable for a Manual Only WHO (no Rule button; Apply refused, nothing written)",
          "who-rule-open" not in mango_row and "Manual Only" in mango_row and "Remove Manual Only" in mango_row
          and 'formaction="/bank/who-rules/manual-only?manual_only=0"' in mango_row
          and f'name="occurrence_id" value="{ids["Mango Grill"]}"' in mango_row
          and refused.status_code == 400 and "Manual Only" in refused.get_json()["error"] and not mango_rules,
          refused.data.decode()[:200])
    summary = client.get(f"/bank/who-rules/who/{ids['Mango Grill']}").get_json()
    check("9b. the modal is told a WHO is Manual Only (when chosen from Review's combo)", summary["manual_only"] is True)

    # Active Rule conflict (15)
    conflict = manual(ids["Delta Trattoria"], True)
    html = page()
    with SessionFactory() as s:
        delta = s.get(m.BankOccurrence, ids["Delta Trattoria"])
        delta_rule = s.get(m.BankRecognitionRule, delta_rule_id)
        first = (delta.manual_only, delta_rule.status)
    confirm = manual(ids["Delta Trattoria"], True, disable_rules="1")
    with SessionFactory() as s:
        delta = s.get(m.BankOccurrence, ids["Delta Trattoria"])
        delta_rule = s.get(m.BankRecognitionRule, delta_rule_id)
        second = (delta.manual_only, delta_rule.status if delta_rule else None)
    check("15. an active WHO Rule conflict requires the explicit disable (rule kept, disabled — never deleted)",
          conflict.status_code == 302 and first == (False, "ACTIVE")
          and "Disable existing WHO Rule and mark Manual Only" in html and ">Cancel</a>" in html
          and second == (True, "INACTIVE"), f"{first} {second}")

    # ------------------------------------------------------------------
    # CLASSIFICATION LEARNING (10-12, 25)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        cands, summ = pd.find_candidates(s)
    who_targets = lambda cs: {c.proposal["who_id"] for c in cs if c.pattern_type == "WHO"}  # noqa: E731
    check("10. WHO-Rule discovery proposes Mango Grill before Manual Only, and excludes it after",
          ids["Mango Grill"] in who_targets(candidates_before) and ids["Mango Grill"] not in who_targets(cands)
          and summ["manual_only_who_excluded"] == 3, f"{who_targets(candidates_before)} {who_targets(cands)}")
    zelle = [c for c in cands if c.pattern_type == "STRUCTURAL" and c.proposal["start_marker"].startswith("ZELLE")]
    check("11. structural discovery still uses the Manual Only WHO's transactions (Zelle pattern kept)",
          len(zelle) == 1 and zelle[0].evidence["matches"] == 36, str([c.proposal for c in cands if c.pattern_type == "STRUCTURAL"]))
    mango_why = [c for c in cands if c.pattern_type == "WHY" and c.proposal["who_id"] == ids["Mango Grill"]]
    check("12. WHY discovery still allowed for a Manual Only WHO (human WHY evidence)",
          len(mango_why) == 1 and mango_why[0].proposal["why_id"] == food_id, str([c.proposal for c in mango_why]))
    fp = lambda cs: {c.fingerprint for c in cs}  # noqa: E731
    mango_who_fp = {c.fingerprint for c in candidates_before if c.pattern_type == "WHO" and c.proposal["who_id"] == ids["Mango Grill"]}
    check("25. Classification Learning unchanged except Manual Only filtering (same candidates minus the WHO-Rule target)",
          fp(candidates_before) - fp(cands) == mango_who_fp and fp(cands) <= fp(candidates_before))
    with SessionFactory() as s:
        # A WHO suggestion stored earlier for a WHO that is now Manual Only cannot be approved.
        stale = m.BankPatternSuggestion(
            fingerprint="whoux-stale", pattern_type="WHO", determinism="DETERMINISTIC", status="SUGGESTED",
            proposal=json.dumps({"phrase": "MANGO GRILL", "who_id": ids["Mango Grill"]}), evidence="{}",
            evidence_level="HUMAN_VERIFIED")
        s.add(stale)
        s.commit()
        try:
            pd.approve(s, suggestion_id=stale.id, account_id=None)
            approved_stale = True
        except ValueError:
            approved_stale = False
        s.rollback()
    check("10b. a stored WHO-Rule suggestion targeting a Manual Only WHO cannot be approved", not approved_stale)

    # ------------------------------------------------------------------
    # Manual reconciliation (13) — Review, Accounting (27, 28)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        queues_after_flags = review_queues.counts(s, review_queues.ReviewFilters())
        accounting_after_flags = snapshot()
    check("27. Review queues unchanged by Manual Only (a flag on the WHO, not a decision)",
          queues_after_flags == queues_before)
    check("28. accounting unchanged by Manual Only (amounts, dates, current decisions, accounting status)",
          accounting_after_flags == accounting_before)
    html = page("/bank/review")
    csrf = CSRF_RE.search(html).group(1)
    reconciled = client.post(f"/bank/transactions/{gap_ids[0]}/who-why", headers={"X-Requested-With": "fetch"},
                             data={"csrf_token": csrf, "occurrence_id": ids["Mango Grill"],
                                   "transaction_reason_id": food_id, "return_to": "/bank/review"})
    with SessionFactory() as s:
        t = s.get(m.FinancialTransaction, gap_ids[0])
        decision = s.get(m.BankTransactionExplanation, t.explanation_id)
    check("13. manual WHO / WHY reconciliation still works for a Manual Only WHO",
          reconciled.status_code == 200 and reconciled.get_json()["ok"]
          and decision.occurrence_id == ids["Mango Grill"] and decision.transaction_reason_id == food_id
          and decision.decision_source == "HUMAN", reconciled.data.decode()[:200])

    # ------------------------------------------------------------------
    # Unmark (14)
    # ------------------------------------------------------------------
    manual(ids["Mango Grill"], False)
    html = page()
    with SessionFactory() as s:
        cands_after, _ = pd.find_candidates(s)
    check("14. unmarking restores normal behaviour (Needs Rule, Rule button, WHO-Rule candidate again)",
          ("NEEDS_RULE", "Mango Grill") in rows(html) and "who-rule-open" in row_html(html, "Mango Grill")
          and ids["Mango Grill"] in who_targets(cands_after))

    # ------------------------------------------------------------------
    # RULE MODAL (16-21)
    # ------------------------------------------------------------------
    html = page()
    modal = html[html.index('id="who-rule-modal"'):html.index("bank-who-rule.js")]
    css = open(CSS_PATH, encoding="utf-8").read()
    js = open(JS_PATH, encoding="utf-8").read()
    check("16. the Rule modal is the wide two-column panel (about 88vw / 1500px, internal scrolling, fixed actions)",
          'class="org-modal-panel who-rule-panel"' in modal and 'class="who-rule-columns"' in modal
          and "width: min(88vw, 1500px)" in css and 'id="who-rule-apply"' in modal and "data-modal-close>Cancel" in modal)
    with SessionFactory() as s:
        grouped = who_rules.selectable_why_groups(s)
        selectable = {r.id for r in who_rules.selectable_whys(s)}
        active_groups = {g.name for g in s.scalars(select(m.BankReasonGroup).where(m.BankReasonGroup.active.is_(True)))}
        stored_order = [g.code for g in s.scalars(select(m.BankReasonGroup).order_by(m.BankReasonGroup.display_order))]
    shown_groups = [html_lib.unescape(g) for g in
                    re.findall(r'<details class="who-rule-why-group" open data-group="([^"]+)"', modal)]
    named = [g for g in shown_groups if g != "Other"]
    check("17. Possible WHY grouped by BankReasonGroup (the one WHY grouping)",
          len(shown_groups) >= 10 and shown_groups == [g for g, _ in grouped] and set(named) <= active_groups,
          str(shown_groups))
    check("17b. WHY groups shown alphabetically by name (a trailing 'Other' only for ungrouped WHY)",
          named == sorted(named, key=str.casefold) and shown_groups[:len(named)] == named, str(shown_groups))
    in_group = {html_lib.unescape(g): [html_lib.unescape(n) for n in re.findall(r'<input type="checkbox" name="transaction_reason_id" value="\d+"> <span>([^<]+)</span>', body)]
                for g, body in re.findall(r'<details class="who-rule-why-group" open data-group="([^"]+)"[^>]*>(.*?)</details>', modal, re.S)}
    check("17c. WHY alphabetical inside each group (case-insensitive)",
          in_group and all(names == sorted(names, key=str.casefold) for names in in_group.values()),
          str({g: n[:4] for g, n in in_group.items()})[:300])
    with SessionFactory() as s:
        popup_groups = [g["name"] for g in client.get("/bank/manual-reconciliation/why-catalog").get_json()["groups"]]
        stored_after = [g.code for g in s.scalars(select(m.BankReasonGroup).order_by(m.BankReasonGroup.display_order))]
    popup_named = [g for g in popup_groups if g != "Other"]
    check("17d. the Select WHO / WHY popup (also Create New WHY and the edit modal) lists the groups alphabetically too; "
          "the stored display order is not rewritten",
          popup_named == sorted(popup_named, key=str.casefold) and stored_after == stored_order, str(popup_groups))
    boxes = {int(v) for v in re.findall(r'name="transaction_reason_id" value="(\d+)"', modal)}
    check("18. every selectable active WHY is reachable, exactly once",
          boxes == selectable and len(re.findall(r'name="transaction_reason_id"', modal)) == len(selectable),
          f"{len(boxes)} vs {len(selectable)}")
    haystacks_ok = all(
        group.lower() in hay for group, items in re.findall(
            r'data-group="([^"]+)"[^>]*>(.*?)</details>', modal, re.S)
        for hay in re.findall(r'data-haystack="([^"]+)"', items))
    check("19. search covers all groups and a result keeps its group (haystack carries the group; empty groups hide)",
          haystacks_ok and 'placeholder="Search WHY in every group"' in modal
          and "group.hidden = visible === 0" in js and 'id="who-rule-why-empty"' in modal)
    beta = client.get(f"/bank/who-rules/who/{ids['Beta Linen']}").get_json()
    check("20. existing WHO -> WHY associations are preselected (summary feeds the ticks, group counts show them)",
          beta["possible_why_ids"] == [linen_why_id] and "setWhyChecked(data.possible_why_ids)" in js
          and "refreshWhyCounts" in js)

    csrf = CSRF_RE.search(page("/bank/classification?q=zeta")).group(1)
    applied = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "occurrence_id": ids["Zeta Diner"],
        "instruction": "Dove nella descrizione trovi ZETA DINER il WHO è Zeta Diner",
        "transaction_reason_id": [food_id], "return_to": "/bank/classification?q=zeta#who-classification"})
    with SessionFactory() as s:
        zeta_txs = [t for t in s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.description_original.like("ZETA DINER%")))]
        zeta_decisions = [s.get(m.BankTransactionExplanation, t.explanation_id) for t in zeta_txs]
        zeta = s.get(m.BankOccurrence, ids["Zeta Diner"])
        zeta_assoc = {a.transaction_reason_id for a in s.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == zeta.id))}
    body = applied.get_json()
    check("21. the Rule still never chooses a WHY (WHO given, WHY left open; WHY only associated)",
          body["ok"] and len(zeta_decisions) == 9 and all(d is not None and d.occurrence_id == zeta.id
                                                          and d.transaction_reason_id is None for d in zeta_decisions)
          and zeta.default_transaction_reason_id is None and zeta_assoc == {food_id}, str(body))
    with SessionFactory() as s:
        zeta_rules = [r.normalized_pattern for r in who_rules.active_who_rules(s, ids["Zeta Diner"])]
    check("24. Simple WHO Rules unchanged (Apply saves the rule and gives the WHO to the 9 matching transactions)",
          zeta_rules == ["ZETA DINER"] and body.get("redirect") is not None, str(zeta_rules))

    # ------------------------------------------------------------------
    # RETURN POSITION (22-23)
    # ------------------------------------------------------------------
    check("22. Apply returns to #who-classification", body["redirect"].endswith("#who-classification"), body["redirect"])
    filtered = page("/bank/classification?q=diner&page=1")
    returns = set(re.findall(r'name="return_to" value="([^"]+)"', filtered))
    check("23. filters / query preserved on the way back (search, page) for Apply and Manual Only",
          returns == {"/bank/classification?q=diner&amp;page=1#who-classification"}
          and body["redirect"] == "/bank/classification?q=zeta#who-classification"
          and "goBack(data.redirect)" in js and "window.location.reload()" in js, str(returns))

    # ------------------------------------------------------------------
    # LAST TRANSACTION (LT1-LT9)
    # ------------------------------------------------------------------
    html = page()

    def cell(h, name):
        row = row_html(h, name)
        start = row.index('<td data-label="Last transaction"')
        return row[start:row.index("</td>", start)]

    with SessionFactory() as s:
        ti = {t.id: t for t in s.scalars(select(m.FinancialTransaction))}
        mango_family = [t for t in ti.values() if "Mango Grill" in t.description_original or "MANGO GRILL" in t.description_original]
        mango_latest = max((t for t in mango_family if t.explanation_id is not None
                            and s.get(m.BankTransactionExplanation, t.explanation_id).occurrence_id == ids["Mango Grill"]),
                           key=lambda t: (t.posting_date, t.id))
    who_part = html[html.index('id="who-classification"'):]
    header = who_part[who_part.index("<thead>"):who_part.index("</thead>")]
    check("LT1. the WHO table has a LAST TRANSACTION column, after Transactions and before Recognised when",
          re.search(r"<th>Transactions</th><th[^>]*>Last transaction</th><th>Recognised when</th>", header) is not None
          and 'colspan="6"' in html, header)
    mango = cell(html, "Mango Grill")
    check("LT2. the latest posting date of the WHO's own transactions is shown",
          mango_latest.posting_date.isoformat() in mango and html_lib.escape(mango_latest.description_original) in mango,
          mango)
    tie = cell(html, "Tie Bistro")
    check("LT3. a same-day tie is broken by the greater transaction id (deterministic)",
          "TIE BISTRO DINNER 002" in tie and "TIE BISTRO LUNCH 001" not in tie, tie)
    family = cell(html, "Family Cafe")
    check("LT4. the bank's original description is shown, in full on hover (title), not a WHO label",
          f'title="{html_lib.escape(long_text)}"' in family and family.count(html_lib.escape(long_text)) == 2, family[:300])
    check("LT5. the instrument / account is shown", "· UX Checking ·" in tie, tie)
    with SessionFactory() as s:
        tie_amount = s.get(m.FinancialTransaction, tie_second).amount_minor
    check("LT6. the amount is shown, signed, two decimals",
          f"−{abs(tie_amount) / 100:,.2f}</span>" in tie, tie)
    check("LT7. a canonical WHO answers for its merged WHO: the family's latest transaction (held by the merged "
          "WHO) is the one shown", "2025-10-03" in family and "FAMILY CAFE ORLANDO 01" not in family, family[:300])
    alpha = cell(html, "alpha cafe")
    check("LT8. a WHO with no transaction shows a dash and the page does not fail",
          '<span class="muted">&mdash;</span>' in alpha, alpha)
    from sqlalchemy import event  # noqa: E402
    counts = []
    for size in (2, 50):
        with SessionFactory() as s:  # a fresh session each time: nothing cached from the other run
            n = [0]
            listener = lambda *a, **k: n.__setitem__(0, n[0] + 1)  # noqa: E731
            event.listen(s.get_bind(), "before_cursor_execute", listener)
            page_rows = who_rules.occurrence_page(s, page_size=size).rows
            event.remove(s.get_bind(), "before_cursor_execute", listener)
            counts.append((len(page_rows), n[0]))
    with SessionFactory() as s:
        latest_direct = who_rules.latest_transactions(s, [ids["Tie Bistro"], ids["Family Cafe"], ids["alpha cafe"]])
    check("LT9. no N+1: the same number of queries for 2 WHO as for a full page (latest transaction in one query)",
          counts[0][1] == counts[1][1] and counts[1][0] > counts[0][0]
          and latest_direct[ids["Tie Bistro"]].transaction_id == tie_second
          and latest_direct[ids["Family Cafe"]].transaction_id == family_latest
          and ids["alpha cafe"] not in latest_direct, str(counts))

    # ------------------------------------------------------------------
    # GENERAL RULES (26)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        general_after = [(r.id, r.start_marker, r.end_marker, r.status) for r in s.scalars(select(m.BankGeneralRule))]
    check("26. General Rules unchanged", general_after == general_before)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
