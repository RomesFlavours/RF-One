"""Decision 59 — recover previous Bank classifications, approve them by group.

Read-only recovery of what the operational Bank already holds for open C-Bank
movements (including unreviewed AI classifications, NEEDS_HUMAN_REVIEW), grouped
by WHO, beneficiary, WHY and category so incompatible classifications stay in
separate groups. Approval is a person's decision on explicitly chosen movements:
it is stored only in the C-Bank experimental store, never in Bank, never as a
permanent rule, and never over a human decision. No AI call.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from sqlalchemy import select

from . import engine as engine_mod, store
from .legacy import Catalog, m

ORIGINS = (
    ("CODEX_WHY_TRIAL", "AI batch (Codex trial), not reviewed"),
    ("CODEX_WHY_COMPLETION", "AI batch (Codex completion), not reviewed"),
    ("CODEX_PRIME_LINE_CORRECTION", "AI batch (PRIME LINE correction), not reviewed"),
    ("AI Rule", "Bank AI rule"),
    ("Foto segnaletica", "Bank recognition profile"),
    ("Reconciliation run", "Bank reconciliation run"),
)


def origin_of(explanation) -> str:
    if explanation is None:
        return "none"
    if explanation.decision_source == "HUMAN":
        return "human"
    note = explanation.explanation_notes or ""
    for prefix, label in ORIGINS:
        if note.startswith(prefix):
            ref = re.search(r"#(\d+)", note)
            return label + (f" #{ref.group(1)}" if ref and prefix in ("AI Rule", "Foto segnaletica") else "")
    return "Bank rule"


def recover(db, catalog: Catalog, results: list[dict], human: dict) -> dict[int, dict]:
    """{txn id: previous Bank classification} for open, unprotected movements."""
    open_rows = [r for r in results if r["status"] != engine_mod.RECONCILED and not r.get("protected")
                 and r["txn_id"] not in human]
    ids = [r["txn_id"] for r in open_rows]
    txns = {t.id: t for i in range(0, len(ids), 500)
            for t in db.scalars(select(m.FinancialTransaction).where(m.FinancialTransaction.id.in_(ids[i:i + 500])))}
    out = {}
    for r in open_rows:
        b = r.get("bank") or {}
        txn = txns.get(r["txn_id"])
        if not txn or not (b.get("who") and b.get("why_id")):
            continue
        e = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None
        origin = origin_of(e)
        if origin == "human":
            continue
        why = catalog.whys.get(b["why_id"])
        category = b.get("category_id") or (why.accounting_classification_id if why else None)
        beneficiary = b.get("beneficiary_id") or r.get("payer_id")
        out[r["txn_id"]] = dict(
            who=b["who"], why_id=b["why_id"], why=why.name if why else None,
            category_id=category, category=catalog.class_label(category),
            beneficiary_id=beneficiary, beneficiary=catalog.entity_name(beneficiary),
            beneficiary_basis="Bank allocation" if b.get("beneficiary_id") else "account owner",
            origin=origin, status=b.get("status"), complete=bool(why and category and beneficiary))
    return out


def groups(priors: dict[int, dict]) -> list[dict]:
    """Proposals grouped by WHO + beneficiary + WHY + category (incompatible ones apart)."""
    by_key = defaultdict(list)
    for tid, p in priors.items():
        by_key[(p["who"], p["beneficiary_id"], p["why_id"], p["category_id"])].append((tid, p))
    out = []
    for (who, ben, why, cat), items in by_key.items():
        p = items[0][1]
        out.append(dict(key=f"{who}|{ben}|{why}|{cat}", who=who, beneficiary_id=ben, beneficiary=p["beneficiary"],
                        why_id=why, why=p["why"], category_id=cat, category=p["category"],
                        complete=p["complete"], txn_ids=sorted(t for t, _ in items),
                        origins=dict(Counter(x["origin"] for _, x in items))))
    return sorted(out, key=lambda g: (g["who"], -len(g["txn_ids"])))


def approve(con, run_id: int, txn_ids: list[int], *, priors: dict[int, dict], results: dict[int, dict],
            corrections: dict | None = None, catalog: Catalog | None = None) -> dict:
    """Store a C-Bank human decision for each chosen movement from its OWN previous
    classification (plus the person's corrections). Skips anything protected or
    without a previous classification. Returns what was saved and skipped."""
    corrections = {k: v for k, v in (corrections or {}).items() if v}
    if catalog is not None:
        if corrections.get("why_id") and corrections["why_id"] not in catalog.whys:
            raise ValueError("Unknown WHY.")
        if corrections.get("category_id") and corrections["category_id"] not in catalog.classes:
            raise ValueError("Unknown category.")
        if corrections.get("beneficiary_id") and corrections["beneficiary_id"] not in catalog.entities:
            raise ValueError("Unknown beneficiary.")
    human = store.human_decisions(con)
    saved, skipped = [], []
    for tid in dict.fromkeys(txn_ids):
        r = results.get(tid)
        p = priors.get(tid)
        if r is None:
            skipped.append(dict(id=tid, reason="not in this run"))
        elif r.get("protected") or tid in human:
            skipped.append(dict(id=tid, reason="human decision already present (protected)"))
        elif r["status"] == engine_mod.RECONCILED:
            skipped.append(dict(id=tid, reason="already reconciled"))
        elif p is None:
            skipped.append(dict(id=tid, reason="no previous Bank classification"))
        else:
            why_id = corrections.get("why_id") or p["why_id"]
            category_id = corrections.get("category_id") or (p["category_id"] if not corrections.get("why_id") else None)
            beneficiary_id = corrections.get("beneficiary_id") or p["beneficiary_id"]
            if not category_id:
                why = catalog.whys.get(why_id) if catalog else None
                category_id = why.accounting_classification_id if why else None
            changed = sorted(k for k in ("why_id", "category_id", "beneficiary_id") if corrections.get(k)
                             and corrections[k] != p[k])
            note = (f"Decision 59: approved previous Bank classification ({p['origin']}, Bank status {p['status']})"
                    + (f"; corrected: {', '.join(changed)}" if changed else ""))
            # The account owner is the default: store a beneficiary only when it differs,
            # so this decision never propagates one entity's beneficiary to another account.
            stored_ben = beneficiary_id if beneficiary_id != r.get("payer_id") else None
            store.save_human_decision(con, tid, who_name=p["who"], beneficiary_id=stored_ben, why_id=why_id,
                                      category_id=category_id, note=note)
            saved.append(dict(id=tid, corrected=changed))
    return dict(saved=saved, skipped=skipped)
