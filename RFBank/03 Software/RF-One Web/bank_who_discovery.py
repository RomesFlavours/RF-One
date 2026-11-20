"""New WHO discovery (Product Owner, 2026-11-17): one button runs WHO Pattern Training automatically.

Product Owner, 2026-11-18: the WHO rules apply in the same way here and in the reconciliation. First every WHO
rule is applied to every movement with the engine's recognition: a name a rule reads that is not a registered WHO
is a candidate, marked with that rule. The patterns below run only on the movements that no WHO rule reads.

For every pattern found by the pattern search (`bank_who_patterns`) whose template names the WHO field, the WHO is
highlighted in the pattern's example — the step a person does on the WHO Pattern Training page — the training code
derives the extraction rule (`bank_who_training.derive`) and applies it to the pattern's movements
(`bank_who_training.verify`). Card descriptors (POS SIG, PURCHASE) lose the trailing location. Every WHO already
present (name or alias, ignoring case and punctuation, also when the bank truncated it) is skipped; the others are
kept as candidates in one `bank_flow_artifacts` record until a person presses Singolo or Multiplo.

Nothing here writes a movement, a WHY or a rule. A WHO is created only by the person's button.
"""
import collections
import html
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select

from rfone_data_store import models as m

KIND = "WHO_DISCOVERY"

# Where the WHO is, by pattern family (the template field naming the counterparty).
SPANS = [
    ("ACH", "PAYPAL", r"IND ID:\s*(.*?)\s+IND NAME:"),
    ("ACH", None, r"ORIG CO NAME:\s*(.*?)\s+ORIG ID:"),
    ("Zelle", None, r"^Zelle payment (?:to|from)\s+(.+?)\s+\S+\s*$"),
    ("POS SIG", None, r"^POS SIG \d{2}/\d{2} \S+ \S+\s+(.+?)\s*$"),
    ("PURCHASE", None, r"^PURCHASE \d{2}/\d{2}\s+(.+?)\s*$"),
    ("Bonifico online", None, r"A/C:\s*(.*?)\s+REF:"),
    ("Online wire", None, r"A/C:\s*(.*?)\s+REF:"),
]
CARD_FAMILIES = ("POS SIG", "PURCHASE")


def _span(family, variant, text):
    for name, var, rx in SPANS:
        if family.startswith(name) and (var is None or (variant or "").upper().startswith(var)):
            hit = re.search(rx, text, re.I)
            return (hit.start(1), hit.end(1)) if hit and hit.group(1).strip() else None
    hit = re.match(r"^\s*([A-Za-z][A-Za-z ._\-]{1,28}?)\s*\*\s*[A-Za-z0-9]*\d[A-Za-z0-9]*\s*$", text)
    if ("prefix" in family or "prefisso" in family) and hit:      # PREFIX * {code}: the prefix is the WHO
        return hit.start(1), hit.end(1)
    return None


def _variables(text, span):
    """Every token with digits outside the WHO varies (dates, numbers, codes)."""
    return [[a.start(), a.end()] for a in re.finditer(r"\S*\d\S*", text) if a.end() <= span[0] or a.start() >= span[1]]


def clean_card_name(raw):
    """Card descriptor -> merchant: cut the repeated name, the first part with digits or '#', the web domain, the
    trailing state code and numbers. Returns (name, uncertain)."""
    words = raw.split()
    if len(words) > 1 and words[0].endswith("*") and len(words[0]) <= 4:      # processor prefix: "IC* COSTCO …"
        words = words[1:]
    for j in range(1, len(words)):           # "ABC FINE WINE/S ABC FINE WINE/SPWINTER…": the name is repeated
        if words[j] == words[0] and j + 1 < len(words) and words[j + 1][:3] == words[1][:3]:
            words = words[:j]
            break
    for i, w in enumerate(words):
        if i and (re.search(r"\d", w) or w.startswith("#")):
            words = words[:i]
            break
    words = [re.sub(r"\.(COM|CO|NET|ORG)$", "", w, flags=re.I) or w for w in words]     # "CLUB.COM" -> "CLUB"
    while words and (re.fullmatch(r"[A-Z]{2}", words[-1]) or re.fullmatch(r"\d+", words[-1])):
        words = words[:-1]
    name = " ".join(words).strip(" -/.,*")
    return name, (not name or len(name) > 30 or len(words) > 5)


def tidy(name):
    """Every extracted name: HTML entities decoded, '*code' and trailing numbers removed, spaces collapsed."""
    words = html.unescape(name or "").upper().split()
    words = [re.sub(r"\*\S*\d\S*$", "", w) or w for w in words]
    while len(words) > 1 and re.fullmatch(r"\d+", words[-1]):
        words = words[:-1]
    return " ".join(words).strip(" -/.,*")


def junk(name):
    """Not a name: fewer than three letters/digits, or only one- or two-letter words."""
    return len(norm(name)) < 3 or all(len(w) <= 2 for w in _tokens(name))


def norm(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _tokens(text):
    return tuple(re.findall(r"[A-Z0-9]+", html.unescape(text or "").upper()))


def known_names(db):
    names = [o.canonical_name for o in db.scalars(select(m.BankOccurrence))]
    names += [a.alias_text for a in db.scalars(select(m.BankOccurrenceAlias))]
    return {_tokens(n) for n in names if _tokens(n)}


def is_known(name, known):
    """Already a WHO: same name or alias ignoring case and punctuation; a name the bank truncated (ACH, 16
    characters); a registered name followed by extra words ("GEICO *AUTO", "UBER BV"); or the first words of a
    registered name ("SEASONS" for "SEASONS 52")."""
    n = _tokens(name)
    if not n:
        return True
    flat = "".join(n)
    for k in known:
        kflat = "".join(k)
        if kflat == flat or (len(flat) >= 10 and kflat.startswith(flat)):
            return True
        if len(kflat) >= 4 and n[:len(k)] == k:
            return True
        if len(flat) >= 3 and k[:len(n)] == n:
            return True
    return False


def read_by_rule(reader, txn):
    """The name a WHO rule of the reconciliation reads on this movement when it is not a registered WHO yet, with
    the rule's reference; else None. The same recognition as the engine (`who_search_text.WhoRecogniser`)."""
    from rfone_data_store.bank_reconciliation import who_search_text as wst
    rec = reader.recognise(txn)
    if rec.outcome == wst.FOUND and rec.method == wst.RULE and not rec.known and rec.who:
        return rec.who.strip().upper(), rec.evidence
    return None


def ruled(rec) -> bool:
    """A WHO rule decided what this movement's WHO is (found, in conflict, or only the intermediary)."""
    from rfone_data_store.bank_reconciliation import who_search_text as wst
    return rec.method == wst.RULE or rec.outcome == wst.RULES_DISAGREE or bool(rec.via_rules)


def discover(db):
    """Product Owner, 2026-11-18 — one reading for the same goal: first the WHO rules of the reconciliation on every
    movement (a name a rule reads that is not a registered WHO is a candidate, with that rule); then the patterns
    and the training code, only on the movements no WHO rule reads. Returns the candidates (not yet registered)."""
    import bank_who_patterns as patterns
    import bank_who_training as training
    from rfone_data_store.bank_reconciliation import who_search_text as wst
    out = collections.OrderedDict()
    reader = wst.WhoRecogniser(db)
    covered = set()
    read = 0
    for txn in db.scalars(select(m.FinancialTransaction)):
        rec = reader.recognise(txn)
        if not ruled(rec):
            continue
        covered.add(txn.id)
        read += 1
        hit = read_by_rule(reader, txn)
        if hit is None:
            continue
        name, ref = hit
        c = out.setdefault(name, dict(name=name, count=0, uncertain=False, patterns=[], example=txn.description_original or "",
                                      raw=name, rule=ref))
        c["count"] += 1
    by_rule = set(out)
    found = patterns.search(db, "it")
    moves = {mv["id"]: mv for mv in training._movements(db)}
    approved, _ = training._approved(db)
    known = known_names(db)
    for p in found["patterns"]:
        for v in (p["variants"] or [None]):
            item = patterns.find(db, p["key"], v["variant"] if v else None, "it")
            if item is None:
                continue
            sp = _span(p["family"], v["name"] if v else None, item["example"])
            if sp is None:
                continue
            try:
                spec, _who = training.derive(item["example"], list(sp), _variables(item["example"], sp))
            except ValueError:
                continue
            check = training.verify(spec, [moves[i] for i in item["transaction_ids"] if i in moves and i not in covered],
                                    {}, approved)
            read += check["selected"]
            card = p["family"].startswith(CARD_FAMILIES)
            for r in check["rows"]:
                name, uncertain = clean_card_name(html.unescape(r["who"])) if card else (r["who"], False)
                name = tidy(name)
                uncertain = uncertain or len(name) > 30 or len(name.split()) > 5 or bool(re.search(r"[#\d]", name))
                if not name or junk(name) or is_known(name, known) or name.upper() in by_rule:
                    continue
                c = out.setdefault(name.upper(), dict(name=name.upper(), count=0, uncertain=uncertain, patterns=[],
                                                      example=r["description"], raw=r["who"]))
                c["count"] += 1
                if item["title"] not in c["patterns"]:
                    c["patterns"].append(item["title"])
    candidates = sorted(out.values(), key=lambda c: (-c["count"], c["name"]))
    return dict(candidates=candidates, movements=found["total"], read=read,
                searched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def record(db, create=False):
    rec = db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == KIND)
                     .order_by(m.BankFlowArtifact.id).limit(1)).first()
    if rec is None and create:
        rec = m.BankFlowArtifact(kind=KIND, payload=json.dumps(dict(candidates=[])))
        db.add(rec)
        db.flush()
    return rec


def load(db):
    rec = record(db)
    data = json.loads(rec.payload) if rec is not None else dict(candidates=[])
    known = known_names(db)
    data["candidates"] = [c for c in data.get("candidates", []) if not is_known(c["name"], known)]
    return data


def save(db, data):
    rec = record(db, create=True)
    rec.payload = json.dumps(data, ensure_ascii=False)
