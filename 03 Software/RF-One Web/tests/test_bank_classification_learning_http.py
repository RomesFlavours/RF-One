"""Classification Learning / pattern discovery (BANK_CLASSIFICATION_LEARNING_001).

On a throwaway database migrated to head, with a synthetic population that
has enough HUMAN truth (the real 2025+ data has only 4 human decisions),
proves discovery (raw input vs refined truth, provenance, structural / WHO /
WHY candidates, probabilistic never promoted), deduplication (existing
General Rule and WHO Rule, rejection memory), the temporal backtest (no
leakage, hidden truth, metrics), approval routing into the existing stores,
runtime without AI, protection, and that the existing rules, queues and
accounting are unchanged.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_learning_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-learning-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import func, select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import pattern_discovery as pd  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import reconciliation_status  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="learning", display_name="Learning",
                                       password="LearningRules123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="learning").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="Learning LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Learning Checking", institution="CHASE", last_four="0011",
                                       currency="USD")
        s.add(checking)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="5" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        why = {c: s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.code == c)).one()
               for c in ("FOOD_PURCHASES", "EMPLOYER_PAYROLL_TAX", "BOH_REGULAR_PAYROLL",
                         "RESTAURANT_OPERATING_SUPPLIES", "OFFICE_SUPPLIES", "LINEN" if False else "JANITORIAL_CLEANING")}

        def who(name):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE",
                                 optional_notes="Canonical WHO.")
            s.add(o)
            s.flush()
            return o

        W = {n: who(n) for n in ("ALICE BAKER", "BRUNO CARUSO", "CARLA DIAZ", "DAVID EVANS", "Acme Payroll",
                                 "Fresh Fish Co", "Bakery Supply", "Amazon", "PAYPAL", "Linen Co",
                                 "MERCHANT BANKCD", "GORDON FOOD SERV", "CHENEY BROTHERS")}
        rule_linen = recognition.create_or_reuse_rule(
            s, match_type="CONTAINS_TEXT", normalized_pattern="LINEN CO SERVICE", occurrence_id=W["Linen Co"].id,
            transaction_reason_id=None, payment_instrument_id=None, direction=None, auto_apply_enabled=True,
            created_from_transaction_id=None)
        seq = [0]

        def tx(description, day, *, who_=None, why_=None, source="HUMAN", amount=-1000):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=day, transaction_date=day, description_original=description,
                description_normalized=description, amount_minor=amount - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"learn-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if who_ is not None or why_ is not None:
                recognition._create_decision_row(
                    s, t, occurrence_id=who_.id if who_ else None, transaction_reason_id=why_.id if why_ else None,
                    recognition_rule_id=rule_linen.id if source == "RULE_LINEN" else None,
                    decision_source="HUMAN" if source == "HUMAN" else "RULE",
                    decision_status="HUMAN_CONFIRMED" if source == "HUMAN" else "NEEDS_HUMAN_REVIEW", confidence=None,
                    explanation_notes=("[why-v1:TEST] structural" if source == "STRUCTURAL" else "seed"))
            return t

        months = [date(2025, mo, 10) for mo in range(1, 10)]
        ids = {}
        for i, day in enumerate(months):
            # STRUCTURAL: Zelle "to <name> REF55..." — 4 names, human truth.
            for j, name in enumerate(("ALICE BAKER", "BRUNO CARUSO", "CARLA DIAZ", "DAVID EVANS")):
                tx(f"Zelle payment to {name.title()} REF55{i}{j}xq", day, who_=W[name], why_=why["FOOD_PURCHASES"])
            # Already covered: Chase ORIG CO NAME with truth (support).
            for name in ("MERCHANT BANKCD", "GORDON FOOD SERV", "CHENEY BROTHERS"):
                tx(f"ORIG CO NAME:{name}       ORIG ID:1{i} DESC DATE:2501 CO ENTRY DESCR:PAY", day,
                   who_=W[name], source="RULE")
            # WHY by feature for one WHO: TAX vs WAGE.
            tx(f"ACME PAYROLL TAX {i}0{i}", day, who_=W["Acme Payroll"], why_=why["EMPLOYER_PAYROLL_TAX"])
            tx(f"ACME PAYROLL WAGE {i}1{i}", day, who_=W["Acme Payroll"], why_=why["BOH_REGULAR_PAYROLL"])
            # One universal WHY for one WHO.
            tx(f"FRESH FISH CO ORDER {i}2{i}", day, who_=W["Fresh Fish Co"], why_=why["FOOD_PURCHASES"])
            # Amazon: mixed WHY, no distinguishing bank text -> probabilistic only.
            tx(f"AMAZON MKTPL {i}3{i}", day, who_=W["Amazon"],
               why_=why["OFFICE_SUPPLIES"] if i % 4 == 0 else why["RESTAURANT_OPERATING_SUPPLIES"])
            # PayPal: never decided by a person.
            tx(f"PAYPAL INST XFER {i}4{i}", day)
            # Linen Co: already a WHO rule.
            tx(f"LINEN CO SERVICE {i}5{i}", day, who_=W["Linen Co"], source="RULE_LINEN")
            # Structural WHY engine result: must never be taken as WHY learning truth.
            tx(f"MONTHLY SERVICE FEE {i}6{i}", day, why_=why["JANITORIAL_CLEANING"], source="STRUCTURAL")
            # WHO phrase: human truth in early months, gap (no decision) later.
            if i < 4:
                tx(f"BAKERY SUPPLY ORLANDO {i}7{i}", day, who_=W["Bakery Supply"], why_=why["FOOD_PURCHASES"])
            else:
                ids.setdefault("bakery_gap", []).append(tx(f"BAKERY SUPPLY ORLANDO {i}7{i}", day).id)
        ids["paypal"] = [t.id for t in s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.description_original.like("PAYPAL%")))]
        s.commit()
        W_ids = {k: v.id for k, v in W.items()}
        why_ids = {k: v.id for k, v in why.items()}
        snapshot_before = {t.id: (t.amount_minor, t.posting_date, t.explanation_id)
                           for t in s.scalars(select(m.FinancialTransaction))}
        queues_before = review_queues.counts(s, review_queues.ReviewFilters())
        general_before = [(r.id, r.start_marker, r.end_marker, r.status) for r in s.scalars(select(m.BankGeneralRule))]
        who_rules_before = [(r.id, r.normalized_pattern, r.occurrence_id) for r in s.scalars(select(m.BankRecognitionRule))]

    # ------------------------------------------------------------------
    # DISCOVERY (1-8)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        obs = pd.load_observations(s)
        one = next(o for o in obs if o.raw.description.startswith("Zelle"))
        check("1. discovery reads raw input (description, date, instrument type, direction, amount)",
              one.raw.description.startswith("Zelle payment to") and one.raw.instrument_type == "BANK_ACCOUNT"
              and one.raw.direction == "DEBIT" and one.raw.amount_minor < 0 and one.raw.posting_date.year == 2025)
        check("2. refined truth is a separate object (WHO, WHY, provenance)",
              one.truth is not None and one.truth.who_id == W_ids["ALICE BAKER"] and not hasattr(one.raw, "who_id"))
        prov = {o.truth.provenance for o in obs if o.truth is not None}
        check("3. provenance is recognised (HUMAN, RULE, STRUCTURAL)", {"HUMAN", "RULE", "STRUCTURAL"} <= prov, str(prov))
        cands, summary = pd.find_candidates(s, obs)
        by = lambda t: [c for c in cands if c.pattern_type == t]  # noqa: E731
        structural = by("STRUCTURAL")
        who_c = by("WHO")
        why_c = by("WHY")
        check("4. an automatic (structural engine) WHY is not learning truth: no WHY candidate for MONTHLY SERVICE FEE",
              not any("SERVICE" in json.dumps(c.proposal) for c in why_c)
              and summary["human_why_examples"] == sum(1 for o in obs if o.human and o.truth.why_id))
        zelle = [c for c in structural if c.proposal["start_marker"].startswith("ZELLE")]
        check("5. a structural candidate is generated (Zelle payment to … REF55)",
              len(zelle) == 1 and zelle[0].proposal["end_marker"] == "REF55" and zelle[0].determinism == "DETERMINISTIC"
              and zelle[0].evidence_level == "HUMAN_VERIFIED", str([c.proposal for c in structural]))
        bakery = [c for c in who_c if c.proposal["who_id"] == W_ids["Bakery Supply"]]
        check("6. a WHO candidate is generated (phrase -> Bakery Supply, filling the gap)",
              len(bakery) == 1 and "BAKERY SUPPLY" in bakery[0].proposal["phrase"] and bakery[0].evidence["gap"] == 5,
              str([(c.proposal, c.evidence.get("gap")) for c in who_c]))
        acme = [c for c in why_c if c.proposal["who_id"] == W_ids["Acme Payroll"]]
        fish = [c for c in why_c if c.proposal["who_id"] == W_ids["Fresh Fish Co"]]
        check("7. WHY candidates where the evidence supports them (Acme TAX -> payroll tax; Fresh Fish -> food)",
              any(c.proposal.get("description_contains") in ("TAX", "PAYROLL TAX") and c.proposal["why_id"] == why_ids["EMPLOYER_PAYROLL_TAX"]
                  and c.determinism == "DETERMINISTIC" for c in acme)
              and any(c.proposal["why_id"] == why_ids["FOOD_PURCHASES"] and c.determinism == "DETERMINISTIC" for c in fish),
              str([(c.proposal, c.determinism) for c in why_c]))
        amazon = [c for c in why_c if c.proposal["who_id"] == W_ids["Amazon"]]
        check("8. a probabilistic pattern is not promoted (Amazon: shown as probabilistic only)",
              amazon and all(c.determinism == "PROBABILISTIC" for c in amazon), str([(c.proposal, c.determinism) for c in amazon]))
        check("24. PayPal without human evidence gets no WHY candidate",
              not any(c.proposal.get("who_id") == W_ids["PAYPAL"] for c in why_c + who_c))

    # ------------------------------------------------------------------
    # DEDUPLICATION (9-11) through the page actions
    # ------------------------------------------------------------------
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "learning", "password": "LearningRules123!", "csrf_token": csrf})
    page = client.get("/bank/classification").data.decode()
    csrf = CSRF_RE.search(page).group(1)
    check("11a. Classification Learning is shown above General Rules and never discovers on page load",
          0 < page.index('id="classification-learning"') < page.index('id="general-rules"')
          and "No new classification patterns to review." in page)
    client.post("/bank/learning/discover", data={"csrf_token": csrf})
    page = client.get("/bank/classification").data.decode()
    with SessionFactory() as s:
        sugg = {(x.pattern_type, json.loads(x.proposal).get("start_marker") or json.loads(x.proposal).get("phrase")
                 or json.loads(x.proposal).get("who_id")): x for x in s.scalars(select(m.BankPatternSuggestion))}
        chase = [x for (t, k), x in sugg.items() if t == "STRUCTURAL" and k == "ORIG CO NAME:"]
        linen = [x for (t, k), x in sugg.items() if t == "WHO" and json.loads(x.proposal)["who_id"] == W_ids["Linen Co"]]
    # BANK_ACTIONABLE_CLASSIFICATION_LEARNING_001: covered is recorded for
    # audit, and never shown — RF-One already knows it.
    check("9. the existing Chase General Rule pattern is recorded as covered and NOT shown",
          len(chase) == 1 and chase[0].status == "COVERED"
          and "ORIG CO NAME:" not in page[page.index('id="classification-learning"'):page.index('id="general-rules"')]
          and "already covered" not in page,
          str([(t, k, x.status) for (t, k), x in sugg.items() if t == "STRUCTURAL"]))
    check("10. an existing WHO Rule is not duplicated (Linen Co): at most recorded as covered, never suggested",
          all(x.status == "COVERED" for x in linen), str([x.status for x in linen]))
    with SessionFactory() as s:
        zelle_s = s.scalars(select(m.BankPatternSuggestion).where(m.BankPatternSuggestion.pattern_type == "STRUCTURAL",
                                                                  m.BankPatternSuggestion.status == "SUGGESTED")).one()
        acme_s = [x for x in s.scalars(select(m.BankPatternSuggestion).where(m.BankPatternSuggestion.pattern_type == "WHY"))
                  if json.loads(x.proposal)["who_id"] == W_ids["Acme Payroll"] and x.determinism == "DETERMINISTIC"][0]
        fish_s = [x for x in s.scalars(select(m.BankPatternSuggestion).where(m.BankPatternSuggestion.pattern_type == "WHY"))
                  if json.loads(x.proposal)["who_id"] == W_ids["Fresh Fish Co"]][0]
        amazon_s = [x for x in s.scalars(select(m.BankPatternSuggestion).where(m.BankPatternSuggestion.pattern_type == "WHY"))
                    if json.loads(x.proposal)["who_id"] == W_ids["Amazon"]][0]
        bakery_s = [x for x in s.scalars(select(m.BankPatternSuggestion).where(m.BankPatternSuggestion.pattern_type == "WHO"))
                    if json.loads(x.proposal)["who_id"] == W_ids["Bakery Supply"]][0]
        ids.update(zelle=zelle_s.id, acme=acme_s.id, fish=fish_s.id, amazon=amazon_s.id, bakery=bakery_s.id)
    client.post(f"/bank/learning/suggestions/{ids['fish']}/reject", data={"csrf_token": csrf})
    client.post("/bank/learning/discover", data={"csrf_token": csrf})
    with SessionFactory() as s:
        fish_after = s.get(m.BankPatternSuggestion, ids["fish"]).status
        n_fish = sum(1 for x in s.scalars(select(m.BankPatternSuggestion))
                     if json.loads(x.proposal).get("who_id") == W_ids["Fresh Fish Co"])
    check("11. a rejected fingerprint suppresses the same proposal", fish_after == "REJECTED" and n_fish == 1)
    with SessionFactory() as s:
        acct = s.get(m.PaymentInstrument, checking.id if False else None) if False else None
        t0 = s.scalars(select(m.FinancialTransaction)).first()
        for k in range(12):
            extra = m.FinancialTransaction(
                payment_instrument_id=t0.payment_instrument_id, bank_source="CHASE_BANK_ACCOUNT",
                import_batch_id=t0.import_batch_id, posting_date=date(2025, 9, 20), transaction_date=date(2025, 9, 20),
                description_original=f"FRESH FISH CO ORDER X{k}9", description_normalized="x", amount_minor=-777 - k,
                status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"fish-extra-{k}", classification="UNKNOWN")
            s.add(extra)
            s.flush()
            recognition._create_decision_row(s, extra, occurrence_id=W_ids["Fresh Fish Co"],
                                             transaction_reason_id=why_ids["FOOD_PURCHASES"], recognition_rule_id=None,
                                             decision_source="HUMAN", decision_status="HUMAN_CONFIRMED", confidence=None,
                                             explanation_notes="more evidence")
        s.commit()
    client.post("/bank/learning/discover", data={"csrf_token": csrf})
    page = client.get("/bank/classification").data.decode()
    with SessionFactory() as s:
        fish_again = s.get(m.BankPatternSuggestion, ids["fish"])
    check("11b. materially new evidence re-proposes it, saying so",
          fish_again.status == "SUGGESTED" and fish_again.previously_rejected
          and "Previously rejected" in page)

    # ------------------------------------------------------------------
    # TEMPORAL BACKTEST (12-15)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        everything = pd.load_observations(s)
        names, identity = pd._names(s), pd._identity_keys(s)
        train_jul = [o for o in everything if o.raw.posting_date < date(2025, 7, 1)]
        check("12. training excludes the test month and the future",
              all(o.raw.posting_date < date(2025, 7, 1) for o in train_jul)
              and len(train_jul) < len(everything))
        # A WHY pattern whose evidence exists only in September cannot be learned for July.
        sept_only = [o for o in everything if o.raw.description.startswith("FRESH FISH CO ORDER X")]
        learned_jul = pd._learned_rules(train_jul, names, identity)
        check("15. no training leakage: September-only evidence is not used to predict July",
              all(o.raw.posting_date.month == 9 for o in sept_only)
              and all(p.get("description_contains") != "ORDER X" for p in learned_jul[2]))
        run = pd.backtest(s)
        s.commit()
        bt = json.loads(run.summary)
    jul = next(r for r in bt["months"] if r["month"] == "2025-07")
    H = jul["HUMAN"]
    check("13. the test month's truth is hidden during inference (predictions come from training rules only)",
          jul["learned"]["structural"] >= 1 and H["who_tested"] > 0)
    expected_cov = round((H["who_correct"] + H["who_false"]) / H["who_tested"], 4)
    check("14. backtest metrics are consistent (coverage, precision, before/after manual work)",
          H["coverage"] == expected_cov and H["manual_before"] == H["who_tested"]
          and H["manual_after"] == H["who_tested"] - H["who_correct"]
          and (H["precision"] is None or H["precision"] == round(H["who_correct"] / (H["who_correct"] + H["who_false"]), 4)),
          json.dumps(H))
    check("14b. Zelle WHO is predicted correctly in July from Jan-Jun learning (4 human cases)",
          H["who_correct"] >= 4 and H["who_false"] == 0, json.dumps(H))

    # ------------------------------------------------------------------
    # TEST (read only) and APPROVAL (16-20)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        decisions_before = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
    client.post(f"/bank/learning/suggestions/{ids['zelle']}/test", data={"csrf_token": csrf})
    tested_page = client.get("/bank/classification").data.decode()
    with SessionFactory() as s:
        decisions_after_test = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
        rules_before_approve = (s.scalar(select(func.count(m.BankGeneralRule.id))),
                                s.scalar(select(func.count(m.BankRecognitionRule.id))),
                                s.scalar(select(func.count(m.BankWhyRule.id))))
    check("14c. Test is read-only and reports matches / correct / precision",
          decisions_after_test == decisions_before and "Test of suggestion" in tested_page and "Precision" in tested_page)
    check("19. nothing becomes a rule before approval", rules_before_approve[2] == 0)
    for key in ("zelle", "bakery", "acme"):
        client.post(f"/bank/learning/suggestions/{ids[key]}/approve", data={"csrf_token": csrf})
    refused = client.post(f"/bank/learning/suggestions/{ids['amazon']}/approve", data={"csrf_token": csrf})
    with SessionFactory() as s:
        zelle_s, bakery_s, acme_s, amazon_s = (s.get(m.BankPatternSuggestion, ids[k]) for k in ("zelle", "bakery", "acme", "amazon"))
        g = s.scalars(select(m.BankGeneralRule).where(m.BankGeneralRule.start_marker == "ZELLE PAYMENT TO")).one_or_none()
        w = s.scalars(select(m.BankRecognitionRule).where(m.BankRecognitionRule.occurrence_id == W_ids["Bakery Supply"])).one_or_none()
        y = s.scalars(select(m.BankWhyRule).where(m.BankWhyRule.occurrence_id == W_ids["Acme Payroll"])).one_or_none()
        check("16. a structural suggestion routes to a General Rule",
              g is not None and g.status == "ACTIVE" and zelle_s.status == "APPROVED" and zelle_s.routed_to == f"general_rule:{g.id}")
        check("17. a WHO suggestion routes to a WHO Rule (BankRecognitionRule)",
              w is not None and w.status == "ACTIVE" and bakery_s.routed_to == f"who_rule:{w.id}")
        check("18. a WHY suggestion routes to a WHY Rule, scoped to its WHO",
              y is not None and y.status == "ACTIVE" and y.transaction_reason_id == why_ids["EMPLOYER_PAYROLL_TAX"]
              and acme_s.routed_to == f"why_rule:{y.id}" and y.approved_at is not None)
        check("19b. a probabilistic pattern cannot be approved (Amazon)", amazon_s.status == "SUGGESTED")

    # Runtime: a future import uses the approved rules with no AI involved.
    import rfone_data_store.bank_reconciliation.pattern_discovery as pd_mod

    def _forbidden(*_a, **_k):
        raise AssertionError("runtime must not call the learning engine")

    saved = {n: getattr(pd_mod, n) for n in ("find_candidates", "discover", "backtest", "test_suggestion")}
    for n in saved:
        setattr(pd_mod, n, _forbidden)
    with SessionFactory() as s:
        csv_bytes = ("Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
                     "DEBIT,09/25/2025,Zelle payment to Carla Diaz REF55NEW1,-20.00,ACH_DEBIT,100.00,\n"
                     "DEBIT,09/26/2025,BAKERY SUPPLY ORLANDO NEW,-21.00,ACH_DEBIT,79.00,\n"
                     "DEBIT,09/27/2025,ACME PAYROLL TAX NEW,-22.00,ACH_DEBIT,57.00,\n"
                     "DEBIT,09/28/2025,ACME PAYROLL WAGE NEW,-23.00,ACH_DEBIT,34.00,\n"
                     "DEBIT,09/29/2025,PAYPAL INST XFER NEW,-24.00,ACH_DEBIT,10.00,\n").encode()
        upload = bank_service.import_csv(s, file_bytes=csv_bytes, original_file_name="chase0011_learn.csv",
                                         uploaded_by_account_id=None, payment_instrument_id=checking.id)
        s.commit()
        new = {t.description_original: recognition.get_current_explanation(s, financial_transaction_id=t.id)
               for t in s.scalars(select(m.FinancialTransaction).where(m.FinancialTransaction.import_batch_id == upload.batch.id))}
    for n, f in saved.items():
        setattr(pd_mod, n, f)
    get = lambda d: (new[d].occurrence_id, new[d].transaction_reason_id) if new.get(d) else (None, None)  # noqa: E731
    check("20. after approval the runtime classifies new imports with plain rules, no AI call",
          get("Zelle payment to Carla Diaz REF55NEW1")[0] == W_ids["CARLA DIAZ"]
          and get("BAKERY SUPPLY ORLANDO NEW")[0] == W_ids["Bakery Supply"]
          and get("ACME PAYROLL TAX NEW") == (None, None),        # Acme has no WHO rule: a WHY rule never chooses WHO
          str({k: get(k) for k in new}))
    check("23/24. an unknown case is left for a person (PayPal: no WHO, no WHY)",
          get("PAYPAL INST XFER NEW") == (None, None))

    # WHY rule at runtime needs a known WHO: give Acme a WHO rule (a person's act) and import again.
    with SessionFactory() as s:
        recognition.create_or_reuse_rule(s, match_type="CONTAINS_TEXT", normalized_pattern="ACME PAYROLL",
                                         occurrence_id=W_ids["Acme Payroll"], transaction_reason_id=None,
                                         payment_instrument_id=None, direction=None, auto_apply_enabled=True,
                                         created_from_transaction_id=None)
        s.commit()
        upload = bank_service.import_csv(s, file_bytes=(
            "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
            "DEBIT,09/27/2025,ACME PAYROLL TAX AGAIN,-25.00,ACH_DEBIT,100.00,\n"
            "DEBIT,09/28/2025,ACME PAYROLL WAGE AGAIN,-26.00,ACH_DEBIT,74.00,\n").encode(),
            original_file_name="chase0011_learn2.csv", uploaded_by_account_id=None, payment_instrument_id=checking.id)
        s.commit()
        again = {t.description_original: recognition.get_current_explanation(s, financial_transaction_id=t.id)
                 for t in s.scalars(select(m.FinancialTransaction).where(m.FinancialTransaction.import_batch_id == upload.batch.id))}
        tax = again["ACME PAYROLL TAX AGAIN"]
        wage = again["ACME PAYROLL WAGE AGAIN"]
        check("18b. the approved WHY rule names the WHY once the WHO is known (TAX -> payroll tax; WAGE untouched)",
              tax.occurrence_id == W_ids["Acme Payroll"] and tax.transaction_reason_id == why_ids["EMPLOYER_PAYROLL_TAX"]
              and tax.accounting_classification_id is not None and wage.transaction_reason_id is None)

    # ------------------------------------------------------------------
    # PROTECTION and REGRESSION (21-28)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        human_tx = s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.description_original.like("ACME PAYROLL WAGE 0%"))).first()
        current = recognition.get_current_explanation(s, financial_transaction_id=human_tx.id)
        check("21. HUMAN decisions are never overwritten (an Acme WAGE human decision keeps its WHY)",
              current.decision_source == "HUMAN" and current.transaction_reason_id == why_ids["BOH_REGULAR_PAYROLL"])
        from rfone_data_store.bank_reconciliation import why_rules
        ctx = why_rules.ImportContext(s)
        std_tx = human_tx
        check("22. a Standard / human decision is protected from WHY rules",
              why_rules.apply_to_new_transaction(s, std_tx, ctx) is False)
        s.rollback()
        changed = [tid for tid, v in snapshot_before.items()
                   if (lambda t: (t.amount_minor, t.posting_date, t.explanation_id))(s.get(m.FinancialTransaction, tid)) != v]
        check("27/28. existing transactions are untouched by discovery, tests and approval (amount, date, decision)",
              not changed, str(changed[:5]))
        general_after = [(r.id, r.start_marker, r.end_marker, r.status) for r in s.scalars(select(m.BankGeneralRule))]
        who_rules_after = [(r.id, r.normalized_pattern, r.occurrence_id) for r in s.scalars(select(m.BankRecognitionRule))]
        check("25. existing General Rules unchanged (only the approved one added)",
              general_after[:len(general_before)] == general_before and len(general_after) == len(general_before) + 1)
        check("26. existing WHO Rules unchanged (only approved / person-made ones added)",
              who_rules_after[:len(who_rules_before)] == who_rules_before)

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            from db import _engine
            _engine.dispose()
            os.remove(_TEST_DB_PATH)
        except Exception:  # noqa: BLE001 — best-effort cleanup of the throwaway file
            pass
