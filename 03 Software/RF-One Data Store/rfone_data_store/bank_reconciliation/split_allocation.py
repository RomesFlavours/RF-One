"""Split of one bank movement into several classification lines (BANK_SPLIT_ALLOCATION_001, 2026-11-01).

The QuickBooks Online "Split" model: a bank movement stays ONE movement and carries 1..N lines, each with an
amount, a WHY, the WHAT derived from that WHY, a description and the documents/items behind it. The lines ARE
`BankTransactionAllocation` rows (BANK_ECONOMIC_ALLOCATION_FOUNDATION_001) — no second model — so their sum
equals the movement exactly, in integer cents and in the movement's sign (money out negative), and nothing is
counted twice: reporting reads the lines, never the parent movement.

    bank movement → Charge Identifier → order(s) → purchased rows → item WHY → lines grouped by WHY → split

Rules (Product Owner, 2026-11-01):
  * items with the same classification are grouped into one line, keeping every original row in the line's
    evidence; different classifications are different lines;
  * the prevailing category is never chosen, and an amount is never divided in equal parts;
  * when several WHYs are needed and amounts per item are missing the proposal stays incomplete with
    "Importi di dettaglio mancanti"; when items have no WHY, "WHY articolo mancante"; nothing is invented;
  * a difference between detail amounts and the movement is either an explicitly stated ancillary amount
    (tax / shipping / discount), apportioned with the existing proportional rule of Purchasing
    (`invoice_allocation_bridge.proportional_split`: last share takes the odd cent), or it stays visible as
    "Differenza non spiegata" — never absorbed silently;
  * WHAT always derives from the WHY; WHOM keeps the existing logic (`row_reconciliation.for_whom_values`:
    the WHOM chosen for the movement, else the Source owner at the movement date).

Amazon order report (`bank_amazon`, kept as AMAZON_REPORT artifacts). Meaning of its columns, verified on the
real export `orders_from_20260101_to_20261026` (118 rows, 103 orders, 96 Charge Identifiers):
  * one row per purchased product line; identical rows are separate real purchases (three ceiling fans in
    order 111-7130700-7696250, Product Owner) and are never de-duplicated;
  * `Order Net Total` is the total of the ORDER, repeated on every row of the order (constant within each of
    the 12 multi-row orders, e.g. 286.23 on each of the three fan rows) — never an item price; it is read
    once per order;
  * there is no price per item in the report: a mixed order cannot be divided from the report alone;
  * `Charge Identifier` is the card charge; a charge may cover several orders (its amount is the sum of their
    totals); an order spread over several charges is a partial charge (the amount of each charge is unknown);
  * `Payment Date` is the charge date (bank date − payment date was 0–1 days on the matched movements);
  * rows with Charge Identifier `N/A` (quantity 0, net total 0.00: cancelled or never charged) are kept but
    never matched.
Link certainty: the exact Charge Identifier as a whole token of the bank description AND equal amount AND
compatible currency AND compatible date = certain. The code with a different amount/date is not certain; an
equal amount and date without the code is only a candidate.

Read-only except `save_draft` and `confirm_split`, which are a person's actions.
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from .. import models as m

# ---------------------------------------------------------------- vocabulary

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"

DETAIL_AMOUNTS_MISSING = "DETAIL_AMOUNTS_MISSING"
ITEM_WHY_MISSING = "ITEM_WHY_MISSING"
DIFFERENCE_UNEXPLAINED = "DIFFERENCE_UNEXPLAINED"
NO_ITEMS = "NO_ITEMS"
ZERO_LINE = "ZERO_LINE"
NO_DOCUMENT = "NO_DOCUMENT"
LINK_AMBIGUOUS = "LINK_AMBIGUOUS"
LINK_CANDIDATE = "LINK_CANDIDATE"
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
PARTIAL_CHARGE = "PARTIAL_CHARGE"
REFUND_PARTIAL = "REFUND_PARTIAL"
CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
DATE_MISMATCH = "DATE_MISMATCH"
ORDER_TOTAL_INCONSISTENT = "ORDER_TOTAL_INCONSISTENT"
WHY_NOT_USABLE = "WHY_NOT_USABLE"
OPPOSITE_SIGN = "OPPOSITE_SIGN"
LABELS = {
    DETAIL_AMOUNTS_MISSING: "Importi di dettaglio mancanti",
    ITEM_WHY_MISSING: "WHY articolo mancante",
    DIFFERENCE_UNEXPLAINED: "Differenza non spiegata",
    NO_ITEMS: "Nessun articolo collegato",
    ZERO_LINE: "Ripartizione di importo zero",
    NO_DOCUMENT: "Documento non trovato",
    LINK_AMBIGUOUS: "Codice addebito su più movimenti",
    LINK_CANDIDATE: "Abbinamento solo candidato (codice addebito assente o discordante)",
    AMOUNT_MISMATCH: "Importo diverso dall'addebito",
    PARTIAL_CHARGE: "Addebito parziale: l'ordine è diviso su più addebiti",
    REFUND_PARTIAL: "Rimborso parziale di un ordine misto",
    CURRENCY_MISMATCH: "Valuta diversa",
    DATE_MISMATCH: "Date non compatibili",
    ORDER_TOTAL_INCONSISTENT: "Totale ordine non coerente tra le righe",
    WHY_NOT_USABLE: "WHY non utilizzabile (inattivo, provvisorio o senza WHAT)",
    OPPOSITE_SIGN: "Riga di segno opposto al movimento",
}

# Ancillary amounts a document may state explicitly; only these are apportioned across lines.
ANCILLARY_KINDS = ("TAX", "SHIPPING", "FEE", "DISCOUNT")

CERTAIN, CODE_ONLY, CANDIDATE, AMBIGUOUS = "CERTAIN", "CODE_ONLY", "CANDIDATE", "AMBIGUOUS"
# Days from the Amazon Payment Date to the bank date accepted for a certain link (observed 0–1).
DATE_WINDOW = (-1, 5)
AMAZON_TEXT = re.compile(r"AMAZON|AMZN", re.I)
SPLIT_DRAFT = "SPLIT_DRAFT"
EVIDENCE_AMAZON = "AMAZON_ORDER"
EVIDENCE_SPLIT = "SPLIT"


def reason(code: str, detail: str = "") -> dict:
    return dict(code=code, label=LABELS[code], detail=detail)


# ---------------------------------------------------------------- split building (pure)

@dataclass
class Item:
    """One purchased row: `ref` locates it in its document; `amount_minor` is its detail amount, positive as
    the document states it, when a document gives one (the Amazon report does not)."""
    ref: dict
    why_id: int | None = None
    why_basis: str | None = None
    amount_minor: int | None = None


@dataclass
class Line:
    amount_minor: int | None
    why_id: int | None
    description: str
    items: list = field(default_factory=list)
    ancillary_minor: int = 0


@dataclass
class Proposal:
    total_minor: int
    lines: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    link: dict | None = None
    documents: list = field(default_factory=list)

    @property
    def allocated_minor(self) -> int:
        return sum(ln.amount_minor or 0 for ln in self.lines)

    @property
    def difference_minor(self) -> int:
        return self.total_minor - self.allocated_minor

    @property
    def complete(self) -> bool:
        return (not self.reasons and bool(self.lines) and self.difference_minor == 0
                and all(ln.amount_minor and ln.why_id for ln in self.lines))

    @property
    def status(self) -> str:
        return COMPLETE if self.complete else INCOMPLETE

    def to_dict(self, whys: dict | None = None) -> dict:
        whys = whys or {}
        out = dict(total_minor=self.total_minor, allocated_minor=self.allocated_minor,
                   difference_minor=self.difference_minor, status=self.status, complete=self.complete,
                   reasons=self.reasons, link=self.link, documents=self.documents, lines=[])
        for ln in self.lines:
            row = asdict(ln)
            row.update(whys.get(ln.why_id, {}) if ln.why_id else {})
            out["lines"].append(row)
        return out


def _title(item: Item) -> str:
    return str(item.ref.get("title") or item.ref.get("description") or "").strip()


def describe(items: list) -> str:
    """The QBO line description: how many rows and which ones, without dropping identical rows."""
    names = [_title(i)[:60] for i in items]
    orders = sorted({str(i.ref.get("order_id")) for i in items if i.ref.get("order_id")})
    head = f"{len(items)} articol{'o' if len(items) == 1 else 'i'}"
    text = head + (" — ordine " + ", ".join(orders) if orders else "") + ": " + "; ".join(names)
    return text[:1000]


def build(total_minor: int, items: list, *, ancillary: dict | None = None) -> Proposal:
    """The split of `total_minor` (the bank movement, signed) over `items`.

    One WHY for every item → one line for the whole movement. Several WHYs → one line per WHY, only when every
    item has a detail amount; the detail total plus an explicitly stated ancillary amount must equal the
    movement exactly. `ancillary` = dict(kind, amount_minor) in the document's positive sign (a discount is
    negative). Nothing is rounded silently: an apportioned ancillary amount follows the proportional rule
    of Purchasing, the last line taking the odd cent."""
    from .invoice_allocation_bridge import proportional_split

    p = Proposal(total_minor=total_minor)
    if not items:
        p.reasons.append(reason(NO_ITEMS))
        return p
    sign = -1 if total_minor < 0 else 1
    groups: "OrderedDict[int | None, list]" = OrderedDict()
    for item in items:
        groups.setdefault(item.why_id, []).append(item)
    unknown = groups.get(None, [])
    if unknown:
        p.reasons.append(reason(ITEM_WHY_MISSING, f"{len(unknown)} of {len(items)} row(s): "
                                + "; ".join(_title(i)[:50] for i in unknown[:5])))
    if len(groups) == 1:
        # One classification for every item (or none yet): one line for the whole movement.
        (why_id, rows), = groups.items()
        p.lines.append(Line(total_minor, why_id, describe(rows), [i.ref for i in rows]))
        return p
    if all(i.amount_minor is not None for i in items):
        sums = [sum(i.amount_minor for i in rows) for rows in groups.values()]
        difference = abs(total_minor) - sum(sums)
        shares = [0] * len(sums)
        if difference:
            stated = (ancillary or {}).get("amount_minor")
            if stated is not None and stated == difference and (ancillary or {}).get("kind") in ANCILLARY_KINDS:
                shares = proportional_split(difference, sums)
            else:
                p.reasons.append(reason(DIFFERENCE_UNEXPLAINED, (
                    f"detail amounts {sum(sums) / 100:.2f} vs movement {abs(total_minor) / 100:.2f}: "
                    f"difference {difference / 100:.2f}" + (f"; stated {ancillary['kind']} "
                    f"{stated / 100:.2f}" if stated is not None else ""))))
        for (why_id, rows), amount, share in zip(groups.items(), sums, shares):
            line = Line(sign * (amount + share), why_id, describe(rows), [i.ref for i in rows], sign * share)
            if not line.amount_minor:
                p.reasons.append(reason(ZERO_LINE, line.description[:80]))
            p.lines.append(line)
        return p
    if len(groups) - bool(unknown) >= 2:
        # Detail amounts are the missing data only once two different WHYs are known; with products still
        # without a WHY, that is what is missing first.
        p.reasons.append(reason(DETAIL_AMOUNTS_MISSING, (
            f"{len(groups) - bool(unknown)} different classifications and no amount per item: the movement is not "
            "divided in equal parts and the prevailing category is not used")))
    for why_id, rows in groups.items():
        p.lines.append(Line(None, why_id, describe(rows), [i.ref for i in rows]))
    return p


# ---------------------------------------------------------------- Amazon evidence

def money_minor(text: str) -> int:
    """'286.23' → 28623. Exact: more than two decimals or anything unreadable is refused, never rounded."""
    try:
        value = Decimal(str(text).replace(",", "").replace("$", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"unreadable amount {text!r}") from exc
    cents = value * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"amount {text!r} has more than two decimals")
    return int(cents)


def _day(text: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except ValueError:
            pass
    return None


@dataclass
class Charge:
    code: str
    rows: list                      # every original row of the charge, in report order
    orders: dict                    # order id → total_minor (read once per order)
    payment_dates: list
    currencies: list
    problems: list = field(default_factory=list)
    partial_orders: list = field(default_factory=list)

    @property
    def expected_minor(self) -> int:
        return sum(self.orders.values())


def charges_from_groups(groups: dict) -> dict:
    """`who_why_rules.charge_groups` output → Charge per code. Order totals are checked to be identical on
    every row of the order; an order appearing under several codes makes each of them a partial charge."""
    order_codes: dict = {}
    for code, rows in groups.items():
        for row in rows:
            order_codes.setdefault(row["fields"].get("Order ID"), set()).add(code)
    out = {}
    for code, rows in groups.items():
        totals: dict = {}
        problems = []
        for row in rows:
            f = row["fields"]
            try:
                totals.setdefault(f.get("Order ID"), set()).add(money_minor(f.get("Order Net Total", "")))
            except ValueError as exc:
                problems.append(reason(ORDER_TOTAL_INCONSISTENT, f"order {f.get('Order ID')}: {exc}"))
        orders = {}
        for order_id, values in totals.items():
            if not values:
                continue                       # unreadable total: reported above, never guessed
            if len(values) != 1:
                problems.append(reason(ORDER_TOTAL_INCONSISTENT, f"order {order_id}: "
                                       + ", ".join(f"{v / 100:.2f}" for v in sorted(values))))
            orders[order_id] = max(values)
        partial = sorted(o for o in orders if len(order_codes.get(o, ())) > 1)
        out[code] = Charge(code=code, rows=rows, orders=orders,
                           payment_dates=sorted({d for d in (_day(r["fields"].get("Payment Date", "")) for r in rows) if d}),
                           currencies=sorted({(r["fields"].get("Currency") or "").upper() for r in rows} - {""}),
                           problems=problems, partial_orders=partial)
    return out


def groups_from_report(report: dict, *, report_id=None, file_name=None) -> dict:
    """A parsed report (`bank_amazon.parse_report`) as charge groups, the shape `charge_groups` returns —
    used by the read-only simulation, which reads the CSV without storing it."""
    groups: dict = {}
    for row in report["rows"]:
        if row["charge"]:
            groups.setdefault(row["charge"], []).append(dict(report_id=report_id, file_name=file_name, **row))
    return groups


def item_ref(row: dict) -> dict:
    f = row["fields"]
    return dict(report_id=row.get("report_id"), file_name=row.get("file_name"), line=row.get("line"),
                charge=row.get("charge"), order_id=f.get("Order ID"), order_date=f.get("Order Date"),
                asin=f.get("ASIN"), title=f.get("Title"), category=f.get("Amazon-Internal Product Category"),
                family=f.get("Family"), klass=f.get("Class"), commodity=f.get("Commodity"),
                quantity=f.get("Item Quantity"), order_net_total=f.get("Order Net Total"))


def _bank_day(txn) -> date | None:
    return txn.transaction_date or txn.posting_date


def _date_ok(txn, charge: Charge) -> bool:
    day = _bank_day(txn)
    return bool(day and any(DATE_WINDOW[0] <= (day - p).days <= DATE_WINDOW[1] for p in charge.payment_dates))


def verify(txn, charge: Charge, currency: str | None) -> dict:
    """Checks of a coded link: amount, currency, date. Refund = money in on the charge code."""
    refund = txn.amount_minor > 0
    checks = dict(code=True, refund=refund, expected_minor=charge.expected_minor)
    reasons = list(charge.problems)
    if charge.partial_orders:
        reasons.append(reason(PARTIAL_CHARGE, "order(s) " + ", ".join(charge.partial_orders)
                              + " also appear under another Charge Identifier"))
    amount = abs(txn.amount_minor)
    checks["amount"] = amount == charge.expected_minor
    if not checks["amount"]:
        if refund and amount < charge.expected_minor:
            checks["refund_partial"] = True
        else:
            reasons.append(reason(AMOUNT_MISMATCH, f"bank {amount / 100:.2f} vs charge {charge.expected_minor / 100:.2f}"
                                  + (" (aggregated or partial charge)" if amount != charge.expected_minor else "")))
    if currency:
        checks["currency"] = "OK" if charge.currencies in ([], [currency.upper()]) else "MISMATCH"
        if checks["currency"] == "MISMATCH":
            reasons.append(reason(CURRENCY_MISMATCH, f"Source {currency} vs report {', '.join(charge.currencies)}"))
    else:
        # The Source has no currency configured: the report currency is shown, not verified against it.
        checks["currency"] = "SOURCE_NOT_CONFIGURED"
    checks["date"] = _date_ok(txn, charge)
    if not checks["date"]:
        reasons.append(reason(DATE_MISMATCH, f"bank {_bank_day(txn)} vs payment "
                              + ", ".join(str(d) for d in charge.payment_dates)))
    return dict(checks=checks, reasons=reasons)


@dataclass
class Link:
    txn_id: int
    state: str              # CERTAIN, CODE_ONLY, CANDIDATE, AMBIGUOUS
    codes: list
    checks: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)


class AmazonEvidence:
    """Charges of the Amazon reports linked to bank movements (`txns`: canonical, not duplicates)."""

    def __init__(self, charges: dict, txns, currency_of=None, item_whys: dict | None = None):
        from . import who_why_rules
        self.charges = charges
        self.txns = {t.id: t for t in txns}
        self.currency_of = currency_of or (lambda t: None)
        self.item_whys = item_whys or {}
        # code → [detail amount per row] when another document (invoice, receipt) gives the item prices; the
        # Amazon order report never does.
        self.item_amounts: dict = {}
        self.by_code = who_why_rules.charge_matches({c: None for c in charges}, list(self.txns.values()))
        self.links: dict = {}
        coded = set()
        for code, ts in self.by_code.items():
            for t in ts:
                coded.add(t.id)
                if len(ts) > 1:
                    self.links.setdefault(t.id, Link(t.id, AMBIGUOUS, [], reasons=[reason(
                        LINK_AMBIGUOUS, f"{code} is on movements " + ", ".join(f"#{x.id}" for x in ts))]))
                    self.links[t.id].codes.append(code)
                    continue
                if t.id in self.links:          # a second code on the same movement: aggregated
                    link = self.links[t.id]
                    link.codes.append(code)
                    continue
                v = verify(t, charges[code], self.currency_of(t))
                state = CERTAIN if not v["reasons"] else CODE_ONLY
                self.links[t.id] = Link(t.id, state, [code], v["checks"], v["reasons"])
        for t_id, link in self.links.items():
            if len(link.codes) > 1 and link.state != AMBIGUOUS:
                # Several charges in one movement: the amount is checked against their sum.
                t = self.txns[t_id]
                merged = Charge("+".join(link.codes), [r for c in link.codes for r in charges[c].rows],
                                {o: v for c in link.codes for o, v in charges[c].orders.items()},
                                sorted({d for c in link.codes for d in charges[c].payment_dates}),
                                sorted({x for c in link.codes for x in charges[c].currencies}),
                                [p for c in link.codes for p in charges[c].problems],
                                sorted({o for c in link.codes for o in charges[c].partial_orders}))
                v = verify(t, merged, self.currency_of(t))
                link.state, link.checks, link.reasons = (CERTAIN if not v["reasons"] else CODE_ONLY), v["checks"], v["reasons"]
        # Candidates: Amazon-looking movements without any code, equal amount and compatible date with a
        # charge that has no coded movement. Never certain.
        free = [c for c, ts in self.by_code.items() if not ts]
        self.candidates: dict = {}
        for t in self.txns.values():
            if t.id in coded or not AMAZON_TEXT.search(t.description_original or ""):
                continue
            hits = [c for c in free if abs(t.amount_minor) == charges[c].expected_minor and _date_ok(t, charges[c])]
            if hits:
                self.candidates[t.id] = hits
                self.links[t.id] = Link(t.id, CANDIDATE, hits, reasons=[reason(
                    LINK_CANDIDATE, "same amount and compatible date as " + ", ".join(hits)
                    + "; the bank description does not carry the code")])

    def charge_items(self, code: str) -> list:
        """Items of one charge with their WHY (from `item_whys`: code → [(why_id, basis)] in row order)."""
        whys = self.item_whys.get(code) or []
        amounts = self.item_amounts.get(code) or []
        out = []
        for index, row in enumerate(self.charges[code].rows):
            why, basis = whys[index] if index < len(whys) else (None, None)
            out.append(Item(ref=item_ref(row), why_id=why, why_basis=basis,
                            amount_minor=amounts[index] if index < len(amounts) else None))
        return out

    def proposal(self, txn) -> Proposal:
        link = self.links.get(txn.id)
        if link is None:
            p = Proposal(total_minor=txn.amount_minor)
            p.reasons.append(reason(NO_DOCUMENT, "no Amazon order report has the Charge Identifier of this movement"))
            return p
        items = [i for code in link.codes for i in self.charge_items(code)]
        p = build(txn.amount_minor, items)
        if link.state == CERTAIN and link.checks.get("refund_partial"):
            if len(p.lines) > 1:
                p.reasons.append(reason(REFUND_PARTIAL, "which products were refunded is not in the report"))
        p.reasons = link.reasons + p.reasons
        p.link = dict(state=link.state, codes=link.codes, checks=link.checks)
        p.documents = sorted({(r.get("file_name") or "", r.get("report_id")) for code in link.codes
                              for r in self.charges[code].rows}, key=str)
        p.documents = [dict(file_name=f, report_id=rid) for f, rid in p.documents]
        return p


def item_whys_from_runs(db) -> dict:
    """code → [(why_id, basis)] from the latest COMPLETED Amazon analysis of each charge (HIGH confidence only;
    anything less is no WHY). The analysis is valid only while the charge has exactly the same products."""
    from . import who_why_rules
    groups = who_why_rules.charge_groups(db)
    out = {}
    runs = db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == who_why_rules.AMAZON_RUN)
                      .order_by(m.BankFlowArtifact.id.desc()))
    for run in runs:
        data = json.loads(run.payload)
        if data.get("status") != "COMPLETED":
            continue
        for charge in data.get("results", []):
            code = charge.get("charge")
            if code in out or code not in groups:
                continue
            items = charge.get("items", [])
            if [i.get("product") for i in items] != [p["fields"] for p in groups[code]]:
                continue
            out[code] = [((i.get("why_id") if i.get("confidence") == "HIGH" else None),
                          f"Amazon analysis #{run.id} ({i.get('confidence')})") for i in items]
    return out


def amazon_evidence(db, txns=None, *, groups=None, item_whys=None) -> AmazonEvidence:
    """The evidence on the stored reports (or on `groups` given by the simulation)."""
    from . import who_why_rules
    if txns is None:
        txns = db.scalars(select(m.FinancialTransaction).where(m.FinancialTransaction.accounting_status == "CANONICAL"))
    txns = [t for t in txns if t.accounting_status == "CANONICAL" and t.duplicate_status != "CONFIRMED_DUPLICATE"]
    groups = who_why_rules.charge_groups(db) if groups is None else groups
    currencies = {i.id: i.currency for i in db.scalars(select(m.PaymentInstrument))}
    return AmazonEvidence(charges_from_groups(groups), txns, lambda t: currencies.get(t.payment_instrument_id),
                          item_whys_from_runs(db) if item_whys is None else item_whys)


# ---------------------------------------------------------------- WHY catalog, drafts, confirmation

def why_catalog(db) -> dict:
    """Usable WHYs: active, not provisional, with a WHAT. id → dict(why, what, what_code)."""
    from . import why_what
    out = {}
    for r in db.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")):
        cls = r.accounting_classification
        if cls is None or why_what.is_provisional(db, r):
            continue
        out[r.id] = dict(why=r.name, what=f"{cls.code} {cls.name}", what_code=cls.code)
    return out


def existing_split(db, txn_id: int) -> list:
    return list(db.scalars(select(m.BankTransactionAllocation)
                           .where(m.BankTransactionAllocation.financial_transaction_id == txn_id)
                           .order_by(m.BankTransactionAllocation.allocation_index)))


def draft_for(db, txn_id: int) -> dict | None:
    for a in db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == SPLIT_DRAFT)
                        .order_by(m.BankFlowArtifact.id.desc())):
        data = json.loads(a.payload)
        if data.get("txn_id") == txn_id:
            return dict(id=a.id, **data)
    return None


def _clean_lines(lines) -> list:
    out = []
    for ln in lines or []:
        amount = ln.get("amount_minor")
        out.append(dict(amount_minor=int(amount) if amount not in (None, "") else None,
                        why_id=int(ln["why_id"]) if ln.get("why_id") not in (None, "") else None,
                        description=str(ln.get("description") or "")[:1000],
                        items=list(ln.get("items") or [])))
    return out


def evaluate_lines(db, txn, lines) -> Proposal:
    """A person's lines checked against the movement: every line amount and usable WHY, exact total."""
    catalog = why_catalog(db)
    p = Proposal(total_minor=txn.amount_minor)
    for ln in _clean_lines(lines):
        p.lines.append(Line(ln["amount_minor"], ln["why_id"], ln["description"], ln["items"]))
    if not p.lines:
        p.reasons.append(reason(NO_ITEMS, "no line"))
    if any(ln.amount_minor is None for ln in p.lines):
        p.reasons.append(reason(DETAIL_AMOUNTS_MISSING, "a line has no amount"))
    if any(ln.amount_minor == 0 for ln in p.lines):
        p.reasons.append(reason(ZERO_LINE, "a line has amount 0"))
    if any(ln.why_id is None for ln in p.lines):
        p.reasons.append(reason(ITEM_WHY_MISSING, "a line has no WHY"))
    bad = [ln.why_id for ln in p.lines if ln.why_id is not None and ln.why_id not in catalog]
    if bad:
        p.reasons.append(reason(WHY_NOT_USABLE, ", ".join(f"#{w}" for w in bad)))
    if p.lines and all(ln.amount_minor is not None for ln in p.lines) and p.difference_minor:
        p.reasons.append(reason(DIFFERENCE_UNEXPLAINED, f"lines {p.allocated_minor / 100:.2f} vs movement "
                                f"{txn.amount_minor / 100:.2f}: difference {p.difference_minor / 100:.2f}"))
    if any(ln.amount_minor and (ln.amount_minor < 0) != (txn.amount_minor < 0) for ln in p.lines):
        p.reasons.append(reason(OPPOSITE_SIGN, "every line has the sign of the movement (money out negative)"))
    return p


def save_draft(db, txn_id: int, lines, *, account_id: int | None, note: str = "") -> dict:
    """Keep an incomplete split as it is (a person's draft): nothing is allocated."""
    txn = db.get(m.FinancialTransaction, txn_id)
    if txn is None:
        raise ValueError(f"Movement {txn_id} does not exist.")
    data = dict(txn_id=txn_id, lines=_clean_lines(lines), note=str(note or "")[:1000],
                saved_by_account_id=account_id, saved_at=datetime.now(timezone.utc).isoformat())
    a = m.BankFlowArtifact(kind=SPLIT_DRAFT, account_id=account_id, payload=json.dumps(data, ensure_ascii=False))
    db.add(a)
    db.flush()
    return dict(id=a.id, **data)


def whom_for(db, txn) -> int | None:
    """WHOM of the split lines, by the existing logic: the WHOM chosen for the movement, else the Source
    owner at the movement date (a movement already split keeps the Source-owner default)."""
    from . import row_reconciliation
    value = row_reconciliation.for_whom_values(db, [txn])[txn.id]
    return value["default_for_whom"] if value["split"] else value["for_whom"]


def confirm_split(db, txn_id: int, lines, *, account_id: int | None, evidence_kind: str = EVIDENCE_SPLIT,
                  evidence_reference: str | None = None) -> list:
    """A person confirms the split: written as the movement's allocations only when complete and exact."""
    from . import economic_allocation
    txn = db.get(m.FinancialTransaction, txn_id)
    if txn is None:
        raise ValueError(f"Movement {txn_id} does not exist.")
    p = evaluate_lines(db, txn, lines)
    if not p.complete:
        raise ValueError("The split is not complete: " + "; ".join(r["label"] + (f" ({r['detail']})" if r["detail"] else "")
                                                                for r in p.reasons))
    whom = whom_for(db, txn)
    if whom is None:
        raise ValueError("WHOM is not known: configure the owner of the Source at the movement date.")
    specs = [economic_allocation.AllocationSpec(
        amount_minor=ln.amount_minor, reporting_entity_id=whom, transaction_reason_id=ln.why_id,
        decision_source="HUMAN", decided_by_account_id=account_id, evidence_kind=evidence_kind,
        evidence_reference=(evidence_reference or "")[:255] or None, description=ln.description or None,
        evidence_detail=json.dumps(ln.items, ensure_ascii=False) if ln.items else None) for ln in p.lines]
    return economic_allocation.set_allocations(db, financial_transaction_id=txn_id, specs=specs)
