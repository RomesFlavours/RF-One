"""Amazon split simulation, read-only (BANK_SPLIT_ALLOCATION_001, 2026-11-01).

Reads an Amazon order report CSV (never stored), links its charges to the bank movements of the Bank database
(read-only session) and builds the split of each linked movement:

    bank movement → Charge Identifier → order(s) → purchased rows → item WHY → lines by WHY → split

Item WHYs: none by default (every linked movement then waits for its products' WHY). With `--ai` the products of
the linked charges are classified with the Amazon prompt of Bank (`bank_amazon.PROMPT`, the one ChatGPT adapter);
only HIGH-confidence answers count. Sent to the AI: product fields (title, Family, Class, Commodity, category,
brand, model, quantity), the Source type and whether the Source owner is a person or a company, the WHY catalog.
Never sent: amounts, bank descriptions, order or charge codes. `--resume` reuses the answers already in --out.

Output (JSON, --out): every CSV row preserved, the links separated (certain / code not verified / candidate /
ambiguous / charge without movement), each proposal with its lines, totals and reasons, a QuickBooks Online
Purchase preview of the complete proposals (one Purchase, several lines), and the summary. Nothing is written
to any database; nothing is sent to QuickBooks.

    python -m cbank.amazon_split --csv <orders.csv> --out <file.json> [--ai] [--resume]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from . import legacy
from .legacy import m

FIELDS = ("Title", "Family", "Class", "Commodity", "Amazon-Internal Product Category", "Brand Code",
          "Item model number", "Item Quantity")


def _split():
    from rfone_data_store.bank_reconciliation import split_allocation, qbo_export
    return split_allocation, qbo_export


def load_report(path: Path) -> dict:
    import bank_amazon
    return bank_amazon.parse_report(path.read_bytes())


def classify(db, ev, links, owner_kind, generate=None, previous=None) -> dict:
    """code → [(why_id, basis)] for the charges of `links`, with the Bank Amazon prompt (HIGH only)."""
    import bank_amazon
    S, _q = _split()
    generate = generate or legacy.generate_json
    reasons = list(db.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")))
    catalog = [dict(id=r.id, name=r.name, description=r.description, what=r.resolution_label) for r in reasons]
    by_id = {c["id"]: c for c in catalog}
    answers = dict(previous or {})
    items = []
    for txn_id, link in links.items():
        txn = ev.txns[txn_id]
        source = db.get(m.PaymentInstrument, txn.payment_instrument_id)
        context = dict(source_type="card" if source and source.instrument_type == "CREDIT_CARD" else "bank account",
                       source_owner=owner_kind.get(txn_id) or "unknown")
        for code in link.codes:
            for index, row in enumerate(ev.charges[code].rows):
                item_id = f"{code}:{index}"
                if item_id not in answers:
                    items.append(dict(item_id=item_id, product={k: row["fields"].get(k, "") for k in FIELDS},
                                      movement=context))
    for offset in range(0, len(items), 20):
        batch = items[offset:offset + 20]
        out = bank_amazon.validate_answer(generate(bank_amazon.PROMPT + "\n" + json.dumps(
            dict(items=batch, why_catalog=catalog), ensure_ascii=False)), batch, by_id)
        answers.update(out)
    whys = {}
    for item_id, a in answers.items():
        code, index = item_id.rsplit(":", 1)
        whys.setdefault(code, {})[int(index)] = (a["why_id"] if a.get("confidence") == "HIGH" else None,
                                                 f"ChatGPT {a.get('confidence')}: {a.get('reason', '')[:300]}")
    item_whys = {code: [v.get(i, (None, None)) for i in range(len(ev.charges[code].rows))] for code, v in whys.items()
                 if code in ev.charges}
    return dict(item_whys=item_whys, answers=answers)


def qbo_preview(db, txn, proposal, whys_catalog):
    """The QBO Purchase the proposal would export once confirmed (allocations are not written)."""
    _S, Q = _split()
    lines = []
    for ln in proposal.lines:
        r = db.get(m.BankTransactionReason, ln.why_id)
        cls = r.accounting_classification if r else None
        lines.append(SimpleNamespace(amount_minor=ln.amount_minor, status=m.ALLOCATION_COMPLETE,
                                     accounting_classification_id=cls.id if cls else None,
                                     accounting_classification_code_snapshot=cls.code if cls else None,
                                     accounting_classification_name_snapshot=cls.name if cls else None,
                                     transaction_reason_name_snapshot=r.name if r else None,
                                     description=ln.description, evidence_reference=", ".join(proposal.link["codes"])))
    return Q.purchase(db, txn, lines)


def run(db, csv_path: Path, *, ai=False, previous=None, generate=None) -> dict:
    S, _Q = _split()
    report = load_report(csv_path)
    groups = S.groups_from_report(report, file_name=csv_path.name)
    txns = list(db.scalars(select(m.FinancialTransaction)))
    ev = S.amazon_evidence(db, txns, groups=groups, item_whys={})
    links = dict(ev.links)
    from rfone_data_store.bank_reconciliation import card_configuration
    owner_kind = {}
    for tid in links:
        t = ev.txns[tid]
        source = db.get(m.PaymentInstrument, t.payment_instrument_id)
        e = card_configuration.owner_entity_for(db, instrument=source, on_date=t.posting_date or t.transaction_date) if source else None
        owner_kind[tid] = {"PERSONAL": "Personal", "LEGAL": "Company"}.get(e.entity_type if e else None, "unknown")
    answers = dict((previous or {}).get("ai_answers") or {})
    if ai:
        got = classify(db, ev, links, owner_kind, generate=generate, previous=answers)
        ev.item_whys, answers = got["item_whys"], got["answers"]
    elif answers:
        got = classify(db, ev, {}, owner_kind, previous=answers)
        ev.item_whys = got["item_whys"]
    whys = S.why_catalog(db)
    movements = []
    for tid, link in sorted(links.items()):
        t = ev.txns[tid]
        p = ev.proposal(t)
        row = dict(txn_id=tid, date=str(t.transaction_date or t.posting_date or ""), description=t.description_original,
                   amount_minor=t.amount_minor, source_owner=owner_kind.get(tid), link=link.state, codes=link.codes,
                   checks=link.checks, proposal=p.to_dict(whys))
        if p.complete and link.state == S.CERTAIN:
            row["qbo_preview"] = qbo_preview(db, t, p, whys)
        movements.append(row)
    coded = {c for link in links.values() if link.state != S.CANDIDATE for c in link.codes}
    rows_total = len(report["rows"])
    na_rows = report["without_code"]
    summary = Counter()
    for r in movements:
        summary["links: " + r["link"]] += 1
        if r["link"] == S.CERTAIN:
            summary["certain: complete" if r["proposal"]["complete"] else "certain: open"] += 1
            if r["proposal"]["complete"]:
                summary[f"certain complete: {len(r['proposal']['lines'])} line(s)"] += 1
            for reason in r["proposal"]["reasons"]:
                summary["open reason: " + reason["label"]] += 1
    rows_in_proposals = sum(len(ln["items"]) for r in movements if r["link"] == S.CERTAIN for ln in r["proposal"]["lines"])
    out = dict(
        generated_at=datetime.now(timezone.utc).isoformat(), csv=str(csv_path), read_only=True,
        columns_meaning={
            "Order Net Total": "total of the ORDER, identical on every row of the order (verified); never an item price",
            "Charge Identifier": "card charge; equals the Amazon code in the bank description (exact whole token)",
            "Payment Date": "charge date (bank date − payment date 0–1 days on the certain links)",
            "Item Quantity": "units of the row; identical rows are separate purchases and are kept",
            "Currency": "currency of the order",
            "item price": "not present in the report: a mixed order needs detail amounts from another document"},
        report=dict(rows=rows_total, rows_without_charge=na_rows, charges=len(ev.charges),
                    orders=len({r["fields"]["Order ID"] for r in report["rows"]}),
                    identical_rows=[dict(order=k[0], asin=k[1], rows=n) for k, n in Counter(
                        (r["fields"]["Order ID"], r["fields"]["ASIN"], json.dumps(r["fields"], sort_keys=True))
                        for r in report["rows"]).items() if n > 1]),
        movements=movements,
        charges_without_movement=[dict(code=c, orders=list(ch.orders), expected_minor=ch.expected_minor,
                                       payment_dates=[str(d) for d in ch.payment_dates], rows=len(ch.rows))
                                  for c, ch in sorted(ev.charges.items()) if c not in coded],
        summary=dict(summary, movements_linked=len(movements), rows_in_certain_proposals=rows_in_proposals,
                     charges_without_movement=len(ev.charges) - len(coded)),
        ai_answers=answers)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Amazon split simulation (read-only).")
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--ai", action="store_true", help="classify the products of the linked charges with ChatGPT")
    p.add_argument("--resume", action="store_true", help="reuse the AI answers already in --out")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    previous = json.loads(a.out.read_text(encoding="utf-8")) if a.resume and a.out.exists() else None
    db = legacy.session()
    try:
        out = run(db, a.csv, ai=a.ai, previous=previous)
    finally:
        db.close()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1))
    print("written", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
