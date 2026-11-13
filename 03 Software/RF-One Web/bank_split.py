"""Split of a bank movement (BANK_SPLIT_ALLOCATION_001): one movement, several classification lines.

`/bank/split` lists the Amazon order evidence linked to bank movements — certain links, links by code that do
not verify, candidates without the code, charges without a movement — and the movements already split.
`/bank/split/<id>` shows one movement: bank total, linked documents and products, the proposed lines (editable),
the allocated total and the difference, and the state or the reason it is incomplete. A person may keep an
incomplete split as a draft, or confirm a complete one: only then the lines are written as the movement's
allocations (`split_allocation.confirm_split`). The QuickBooks Online preview of the confirmed split is local
and read-only. No engine run is started and nothing is sent anywhere.
"""
import json

from flask import abort, jsonify, render_template, request
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import (qbo_export, rule_application_safety as safety,
                                                  split_allocation as S)


def _movement(db, txn, sources, owners) -> dict:
    source = sources.get(txn.payment_instrument_id)
    owner = owners.get(txn.id)
    return dict(id=txn.id, date=str(txn.transaction_date or txn.posting_date or ""), description=txn.description_original or "",
                amount_minor=txn.amount_minor, source=source.display_name if source else None,
                source_type=source.instrument_type if source else None, currency=source.currency if source else None,
                owner=owner)


def _owners(db, txns, sources) -> dict:
    from rfone_data_store.bank_reconciliation import card_configuration
    out = {}
    for t in txns:
        source = sources.get(t.payment_instrument_id)
        day = t.posting_date or t.transaction_date
        e = card_configuration.owner_entity_for(db, instrument=source, on_date=day) if source and day else None
        out[t.id] = dict(id=e.id, name=e.name, type=e.entity_type) if e else None
    return out


def overview(db, who_id=None) -> dict:
    ev = S.amazon_evidence(db)
    whys = S.why_catalog(db)
    sources = {s.id: s for s in db.scalars(select(m.PaymentInstrument))}
    txns = [ev.txns[i] for i in ev.links]
    if who_id:
        current = {t.id: t.explanation_id for t in txns}
        keep = {e.id for e in db.scalars(select(m.BankTransactionExplanation).where(
            m.BankTransactionExplanation.id.in_([x for x in current.values() if x]),
            m.BankTransactionExplanation.occurrence_id == who_id))}
        txns = [t for t in txns if current[t.id] in keep] or txns
    owners = _owners(db, txns, sources)
    rows = []
    for t in sorted(txns, key=lambda t: (str(t.transaction_date or t.posting_date or ""), t.id), reverse=True):
        link = ev.links[t.id]
        p = ev.proposal(t)
        rows.append(dict(_movement(db, t, sources, owners), link=link.state, codes=link.codes,
                         status=p.status, reasons=p.reasons, lines=len(p.lines),
                         items=sum(len(ln.items) for ln in p.lines)))
    coded = {c for link in ev.links.values() if link.state != S.CANDIDATE for c in link.codes}
    unmatched = [dict(code=c, orders=list(ch.orders), expected_minor=ch.expected_minor,
                      payment_dates=[str(d) for d in ch.payment_dates], rows=len(ch.rows))
                 for c, ch in sorted(ev.charges.items()) if c not in coded]
    split = {}
    for a in db.scalars(select(m.BankTransactionAllocation)):
        split.setdefault(a.financial_transaction_id, []).append(a)
    split_ids = [t for t, rows_ in split.items() if len(rows_) > 1]
    split_txns = [db.get(m.FinancialTransaction, i) for i in split_ids]
    split_owners = _owners(db, split_txns, sources)
    counts = {k: sum(r["link"] == k for r in rows) for k in (S.CERTAIN, S.CODE_ONLY, S.CANDIDATE, S.AMBIGUOUS)}
    return dict(movements=rows, unmatched=unmatched, counts=counts, whys=len(whys),
                complete=sum(r["status"] == S.COMPLETE and r["link"] == S.CERTAIN for r in rows),
                split=[dict(_movement(db, t, sources, split_owners), lines=len(split[t.id])) for t in split_txns])


def detail(db, txn_id) -> dict:
    txn = db.get(m.FinancialTransaction, txn_id)
    if txn is None:
        abort(404)
    sources = {s.id: s for s in db.scalars(select(m.PaymentInstrument))}
    whys = S.why_catalog(db)
    ev = S.amazon_evidence(db)
    p = ev.proposal(txn)
    allocations = S.existing_split(db, txn_id)
    state = None
    if allocations:
        from rfone_data_store.bank_reconciliation import economic_allocation
        st = economic_allocation.allocation_state(db, financial_transaction_id=txn_id)
        state = dict(status=st.status, allocated_minor=st.allocated_amount_minor, difference_minor=st.difference_minor,
                     balanced=st.is_balanced)
    whom = S.whom_for(db, txn)
    entity = db.get(m.ReportingEntity, whom) if whom else None
    return dict(movement=_movement(db, txn, sources, _owners(db, [txn], sources)),
                whom=dict(id=entity.id, name=entity.name) if entity else None,
                proposal=p.to_dict(whys), draft=S.draft_for(db, txn_id),
                allocations=[dict(amount_minor=a.amount_minor, why_id=a.transaction_reason_id,
                                  why=a.transaction_reason_name_snapshot,
                                  what=" ".join(x for x in (a.accounting_classification_code_snapshot,
                                                            a.accounting_classification_name_snapshot) if x),
                                  description=a.description, status=a.status, decision_source=a.decision_source,
                                  items=json.loads(a.evidence_detail) if a.evidence_detail else [],
                                  evidence=a.evidence_reference) for a in allocations],
                allocation_state=state,
                whys=sorted(([dict(id=k, **v) for k, v in whys.items()]), key=lambda w: w["why"].casefold()),
                qbo=qbo_export.preview(db, [txn_id])["purchases"][0] if allocations else None,
                labels=S.LABELS)


def _lines(body):
    raw = body.get("lines")
    lines = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(lines, list):
        raise ValueError("Send the split lines.")
    return lines


def register(app, *, gate, SessionFactory, require_csrf, owner, endpoint):
    @app.route("/bank/split")
    @gate
    def bank_split_page():
        return render_template("bank_split.html", txn_id=None)

    @app.route("/bank/split/data")
    @gate
    @endpoint
    def bank_split_data():
        with SessionFactory() as db:
            return jsonify(ok=True, **overview(db, request.args.get("who", type=int)), labels=S.LABELS)

    @app.route("/bank/split/<int:txn_id>")
    @gate
    def bank_split_movement_page(txn_id):
        return render_template("bank_split.html", txn_id=txn_id)

    @app.route("/bank/split/<int:txn_id>/data")
    @gate
    @endpoint
    def bank_split_movement_data(txn_id):
        with SessionFactory() as db:
            return jsonify(ok=True, **detail(db, txn_id))

    @app.route("/bank/split/<int:txn_id>/check", methods=["POST"])
    @gate
    @endpoint
    def bank_split_check(txn_id):
        require_csrf()
        with SessionFactory() as db:
            txn = db.get(m.FinancialTransaction, txn_id)
            if txn is None:
                abort(404)
            return jsonify(ok=True, **S.evaluate_lines(db, txn, _lines(request.form)).to_dict(S.why_catalog(db)))

    @app.route("/bank/split/<int:txn_id>/draft", methods=["POST"])
    @gate
    @endpoint
    def bank_split_draft(txn_id):
        require_csrf()
        with SessionFactory() as db:
            safety.lock_writes(db)
            draft = S.save_draft(db, txn_id, _lines(request.form), account_id=owner(db), note=request.form.get("note", ""))
            db.commit()
            return jsonify(ok=True, draft_id=draft["id"])

    @app.route("/bank/split/<int:txn_id>/confirm", methods=["POST"])
    @gate
    @endpoint
    def bank_split_confirm(txn_id):
        require_csrf()
        if request.form.get("confirm") != "yes":
            raise ValueError("Confirm the split explicitly.")
        with SessionFactory() as db:
            safety.lock_writes(db)
            rows = S.confirm_split(db, txn_id, _lines(request.form), account_id=owner(db),
                                   evidence_kind=request.form.get("evidence_kind") or S.EVIDENCE_SPLIT,
                                   evidence_reference=request.form.get("evidence_reference"))
            db.commit()
            return jsonify(ok=True, lines=len(rows))

    @app.route("/bank/split/qbo-preview")
    @gate
    @endpoint
    def bank_split_qbo_preview():
        ids = [int(x) for x in (request.args.get("ids") or "").split(",") if x.strip().isdigit()]
        with SessionFactory() as db:
            return jsonify(ok=True, **qbo_export.preview(db, ids))
