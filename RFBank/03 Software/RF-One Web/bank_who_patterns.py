"""WHO pattern search (BANK_WHO_PATTERN_SEARCH_001, Product Owner, 2026-11-06).

Finds the recurring structures in the ORIGINAL descriptions of every loaded movement, so the person does not have to
find the formats. Method ported from the independent research `RF1 Sviluppo/output/WHO-Formati/analyse.py`
(2026-11-06): labelled bank formats, processor prefixes followed by "*", numeric skeletons discovered by comparing
descriptions (numbers that never vary stay literal), identical repeated descriptions. Patterns and counts are
recomputed on the data present in Bank every time; the WHO rules are never read.

Read-only: nothing here creates or activates a rule, or changes a movement. Each movement belongs to one top-level
pattern only; sub-families (e.g. PAYPAL inside ACH) partition their family, so their counts are already included in
the family total. Descriptions not corroborated by at least two different texts are not a pattern and are left out.
"""
import collections
import hashlib
import os
import re

from sqlalchemy import select

from rfone_data_store import models as m

# (title, template, family regex, sub-family function or None) — labels as (English, Italian).
_FAMILIES = [
    (("ACH · labelled fields", "ACH · campi etichettati"), r"^ORIG CO NAME:.*ORIG ID:.*DESC DATE:.*CO ENTRY DESCR:.*SEC:.*TRACE#:.*EED:.*IND ID:.*IND NAME:.*TRN:",
     ("ORIG CO NAME:{company} ORIG ID:{code} DESC DATE:{date, may be empty} CO ENTRY DESCR:{purpose} SEC:{type} TRACE#:{trace} EED:{date} IND ID:{value} IND NAME:{name} … TRN:{reference}",
      "ORIG CO NAME:{società} ORIG ID:{codice} DESC DATE:{data, anche vuota} CO ENTRY DESCR:{causale} SEC:{tipo} TRACE#:{traccia} EED:{data} IND ID:{valore} IND NAME:{nome} … TRN:{riferimento}"),
     lambda s: (lambda v: (v, v))(re.search(r"^ORIG CO NAME:(.*?) ORIG ID:", s).group(1).strip())),
    (("Zelle · payment to / from", "Zelle · pagamento a / da"), r"^ZELLE PAYMENT (TO|FROM) .+ \S+$",
     ("ZELLE PAYMENT {TO | FROM} {name} {final reference}", "ZELLE PAYMENT {TO | FROM} {nome} {riferimento finale}"),
     lambda s: ("Outgoing · TO", "In uscita · TO") if s.startswith("ZELLE PAYMENT TO ") else ("Incoming · FROM", "In entrata · FROM")),
    (("Online transfer · account and reference", "Trasferimento online · conto e riferimento"), r"^ONLINE TRANSFER (TO|FROM) ",
     ("ONLINE TRANSFER {TO | FROM} {account type} …{account number} TRANSACTION#: {reference} [{date}]",
      "ONLINE TRANSFER {TO | FROM} {tipo conto} …{numero conto} TRANSACTION#: {riferimento} [{data}]"),
     lambda s: (lambda d, f: (d + (" · with final date" if f else " · without final date"), d + (" · con data finale" if f else " · senza data finale")))(
         "TO" if s.startswith("ONLINE TRANSFER TO ") else "FROM", bool(re.search(r"\d{2}/\d{2}$", s)))),
    (("POS SIG · card purchase", "POS SIG · acquisto con carta"), r"^POS SIG \d{2}/\d{2} ",
     ("POS SIG {date} {network} #{card} {merchant and location}", "POS SIG {data} {circuito} #{carta} {descrizione esercente e località}"), None),
    (("PURCHASE · purchase and merchant", "PURCHASE · acquisto e descrizione esercente"), r"^PURCHASE \d{2}/\d{2} ",
     ("PURCHASE {date} {merchant / location / reference}", "PURCHASE {data} {descrizione esercente / località / riferimento}"), None),
    (("Chase card payment", "Pagamento carta Chase"), r"^PAYMENT TO CHASE CARD ENDING IN ",
     ("PAYMENT TO CHASE CARD ENDING IN {last digits} {date}", "PAYMENT TO CHASE CARD ENDING IN {ultime cifre} {data}"), None),
    (("Debits · WEB / TEL / CCD / PPD code", "Addebiti · codice WEB / TEL / CCD / PPD"), r"\b(WEB|TEL|CCD|PPD) ID: \S+$",
     ("{description and references} {WEB | TEL | CCD | PPD} ID: {code}", "{descrizione e riferimenti} {WEB | TEL | CCD | PPD} ID: {codice}"),
     lambda s: (lambda v: (v, v))(re.search(r"\b(WEB|TEL|CCD|PPD) ID:", s).group(1))),
    (("Check · number and optional date", "Assegno · numero e data facoltativa"), r"^CHECK \d+(?: \d{2}/\d{2})?$",
     ("CHECK {check number} [{date}]", "CHECK {numero assegno} [{data}]"),
     lambda s: ("With date", "Con data") if "/" in s else ("Number only", "Solo numero")),
    (("Memorandum · purpose and reference", "Memorandum · causale e riferimento"), r"^(CREDIT|DEBIT) MEMORANDUM REF:",
     ("{CREDIT | DEBIT} MEMORANDUM REF: {purpose} TRN: {reference} [{date}]", "{CREDIT | DEBIT} MEMORANDUM REF: {causale} TRN: {riferimento} [{data}]"),
     lambda s: (lambda v: (v, v))(s.split(" MEMORANDUM")[0])),
    (("Deposit · identifier", "Deposito · identificativo"), r"^DEPOSIT ID NUMBER \d+$",
     ("DEPOSIT ID NUMBER {number}", "DEPOSIT ID NUMBER {numero}"), None),
    (("Withdrawal · date", "Prelievo · data"), r"^WITHDRAWAL \d{2}/\d{2}$", ("WITHDRAWAL {date}", "WITHDRAWAL {data}"), None),
    (("FCB · transfer to account", "FCB · trasferimento a conto"), r"^FCB FUNDS TRANSFER TO ",
     ("FCB FUNDS TRANSFER TO {account}", "FCB FUNDS TRANSFER TO {conto}"), None),
    (("Online wire · labelled fields", "Bonifico online · campi etichettati"), r"^ONLINE (INTERNATIONAL|DOMESTIC) WIRE TRANSFER ",
     ("ONLINE {INTERNATIONAL | DOMESTIC} WIRE TRANSFER [VIA: {bank}] A/C: {beneficiary} REF: {purpose} … TRN: {reference} {date}",
      "ONLINE {INTERNATIONAL | DOMESTIC} WIRE TRANSFER [VIA: {banca}] A/C: {destinatario} REF: {causale} … TRN: {riferimento} {data}"),
     lambda s: ("International", "Internazionale") if "INTERNATIONAL" in s else ("Domestic", "Nazionale")),
    (("Check reversal", "Storno di assegno"), r"^REVERSAL OF CHECK \d+$", ("REVERSAL OF CHECK {number}", "REVERSAL OF CHECK {numero}"), None),
]
_CARD_DATE = (("Card description · final date", "Descrizione carta · data finale"), r"\b[A-Z]{2} \d{2}/\d{2}$",
              ("{merchant / location} {two-letter code} {date}", "{descrizione esercente / località} {sigla di due lettere} {data}"), None)


def language():
    return "it" if os.environ.get("RFONE_UI_LANGUAGE", "en").strip().lower() == "it" else "en"


def _key(*parts):
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def discover(rows, lang="en"):
    """`rows`: dict(id, date, text, source). Returns the patterns (count descending), each with its sub-families."""
    li = 1 if lang == "it" else 0
    rows = [dict(r, norm=" ".join((r["text"] or "").upper().split())) for r in rows]
    remaining = {r["id"]: r for r in rows}
    groups = []

    def add(kind, labels, template, selected, variants=None):
        selected = sorted(selected, key=lambda r: (r["date"] or "", r["id"]), reverse=True)
        for r in selected:
            del remaining[r["id"]]
        groups.append(dict(kind=kind, key=_key(kind, labels[0], template[0]), title=labels[li], template=template[li],
                           records=selected, variants=variants or []))

    def take(labels, pattern, template, variant):
        selected = [r for r in remaining.values() if re.search(pattern, r["norm"])]
        if len(selected) < 2 or len({r["norm"] for r in selected}) < 2:
            return
        variants = []
        if variant:
            bins = collections.defaultdict(list)
            for r in selected:
                bins[variant(r["norm"])].append(r)
            for names, recs in bins.items():
                recs.sort(key=lambda r: (r["date"] or "", r["id"]), reverse=True)
                variants.append(dict(key=_key(names[0]), name=names[li], records=recs))
        add("format", labels, template, selected, variants)

    for labels, pattern, template, variant in _FAMILIES:
        take(labels, pattern, template, variant)

    # Processor-like prefixes followed by "*", discovered from the data (not from WHO rules).
    bins = collections.defaultdict(list)
    for r in remaining.values():
        hit = re.match(r"^([A-Z][A-Z ._\-]{1,28})\s*\*(.+)$", r["norm"])
        if hit:
            bins[hit.group(1).strip()].append(r)
    for prefix, selected in sorted(bins.items(), key=lambda kv: -len(kv[1])):
        if len({r["norm"] for r in selected}) < 2:
            continue
        suffixes = [re.split(r"\*", r["norm"], maxsplit=1)[1].strip() for r in selected]
        code = all(re.fullmatch("[A-Z0-9]{6,}", s) and re.search("[0-9]", s) for s in suffixes)
        add("format", (prefix + " · asterisk prefix", prefix + " · prefisso con asterisco"),
            (prefix + " * " + ("{variable code}" if code else "{variable text}"),
             prefix + " * " + ("{codice variabile}" if code else "{testo variabile}")), selected)

    take(*_CARD_DATE)

    # Numeric skeletons: same text, at least two different values in the numeric fields; stable numbers stay literal.
    bins = collections.defaultdict(list)
    for r in remaining.values():
        parts = re.split(r"(\d+)", r["norm"])
        if len(parts) > 1 and any(re.search("[A-Z]", p) for p in parts):
            bins[tuple("#" if i % 2 else p for i, p in enumerate(parts))].append(r)
    for _skeleton, selected in sorted(bins.items(), key=lambda kv: -len(kv[1])):
        if len({r["norm"] for r in selected}) < 2:
            continue
        columns = [set(col) for col in zip(*(re.split(r"(\d+)", r["norm"]) for r in selected))]
        both = []
        for word in ("{number}", "{numero}"):
            template = "".join(next(iter(vals)) if len(vals) == 1 else word for vals in columns)
            both.append((template, re.split(r"[\d#*{]", template)[0].strip(" .-") or template))
        add("format", (both[0][1] + " · numeric variant", both[1][1] + " · variante numerica"), (both[0][0], both[1][0]), selected)

    # Identical descriptions repeated: a recurrence, though not evidence of variable fields.
    bins = collections.defaultdict(list)
    for r in remaining.values():
        bins[r["norm"]].append(r)
    for text, selected in sorted(bins.items(), key=lambda kv: -len(kv[1])):
        if len(selected) >= 2:
            add("repeat", (text, text), (text, text), selected)

    groups.sort(key=lambda g: (-len(g["records"]), g["title"]))
    return groups


def summary(group, variant=None):
    """What the page and the rule window show of a pattern (or of one of its sub-families)."""
    recs = variant["records"] if variant else group["records"]
    distinct = []
    for r in recs:
        if r["text"] not in distinct:
            distinct.append(r["text"])
    return dict(key=group["key"], variant=variant["key"] if variant else None, kind=group["kind"],
                title=group["title"] + (" › " + variant["name"] if variant else ""), family=group["title"],
                template=group["template"], count=len(recs), example=recs[0]["text"], example_id=recs[0]["id"],
                examples=distinct[:20], distinct=len(distinct))


def movements(db):
    sources = {i.id: i.display_name for i in db.scalars(select(m.PaymentInstrument))}
    return [dict(id=t.id, date=str(t.posting_date or t.transaction_date or ""), text=t.description_original or "",
                 source=sources.get(t.payment_instrument_id)) for t in db.scalars(select(m.FinancialTransaction))]


def search(db, lang=None):
    """Every pattern in the loaded movements, for the page: count descending, sub-families inside."""
    rows = movements(db)
    out = []
    for g in discover(rows, lang or language()):
        item = summary(g)
        item["variants"] = [dict(summary(g, v), name=v["name"]) for v in sorted(g["variants"], key=lambda v: (-len(v["records"]), v["name"]))]
        out.append(item)
    return dict(total=len(rows), covered=sum(p["count"] for p in out), patterns=out)


def find(db, key, variant=None, lang=None):
    """One pattern recomputed now, with all its movement ids; None when the data no longer produce it."""
    for g in discover(movements(db), lang or language()):
        if g["key"] != key:
            continue
        v = next((x for x in g["variants"] if x["key"] == variant), None) if variant else None
        if variant and v is None:
            return None
        item = summary(g, v)
        item["transaction_ids"] = [r["id"] for r in (v or g)["records"]]
        return item
    return None
