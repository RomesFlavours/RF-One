"""Pure text compatibility helpers; no legacy worker, labels, AI or database writes."""
from __future__ import annotations
import html
import re
from dataclasses import dataclass
from . import who_recognition as wr

@dataclass
class Variant:
    kind: str      # NAME | GENERIC
    text: str      # the counterparty as the bank writes it, or the generic shape
    key: str

_GENERIC = [(re.compile(p, re.IGNORECASE), label) for p, label in (
    (r"^online transfer\b", "ONLINE TRANSFER"),
    (r"\bfunds transfer\b", "FUNDS TRANSFER"),
    (r"^payment to .*card ending", "PAYMENT TO CARD"),
    (r"^(payment thank you|automatic payment)\b", "CARD PAYMENT RECEIVED"),
    (r"^check\s*#?\s*\d*$", "CHECK"),
    (r"^(remote online )?deposit\b", "DEPOSIT"),
    (r"^(atm )?withdrawal\b", "WITHDRAWAL"),
    (r"^interest (payment|charge|paid|earned)\b", "INTEREST"),
    (r"^foreign transaction fee\b", "FOREIGN TRANSACTION FEE"),
    (r"^credit memorandum\b", "CREDIT MEMORANDUM"),
    (r"^(monthly )?(service|maintenance) (fee|charge)\b", "SERVICE FEE"),
    (r"^(late|annual|overdraft|returned item|wire) fee\b", "BANK FEE"),
    (r"^(incoming|outgoing)? ?wire transfer\b", "WIRE TRANSFER"),
)]

_ACH = re.compile(r"ORIG CO NAME:\s*(.*?)\s+ORIG ID:", re.IGNORECASE)

_ACH_SELLER = re.compile(r"IND ID:\s*(.*?)\s+IND NAME:", re.IGNORECASE)

ACH_INTERMEDIARIES = {"PAYPAL", "VENMO", "SQUARE", "SQUARE INC", "STRIPE", "GOOGLE", "APPLE", "APPLE CASH"}

_ZELLE = re.compile(r"^ZELLE PAYMENT (?:TO|FROM)\s+(.*)$", re.IGNORECASE)

_CARD_PREFIX = re.compile(
    r"^(?:POS SIG|POS DEBIT|POS PURCHASE|POS|DEBIT CARD PURCHASE|CARD PURCHASE(?: WITH PIN)?|"
    r"RECURRING CARD PURCHASE|PURCHASE AUTHORIZED ON|RECURRING PAYMENT AUTHORIZED ON|PURCHASE)\s+"
    r"(?:\d\d/\d\d\s+)?(?:(?:VISA|MC|MASTERCARD|DEBIT)\s+)?(?:#\s*\d+\s+)?", re.IGNORECASE)

_AMAZON = re.compile(r"\bAMAZON|\bAMZN", re.IGNORECASE)

_ACH_TAIL = re.compile(r"\s+(?:WEB|TEL|PPD|CCD|ARC|BOC)\s+ID:.*$|\s+ID:.*$", re.IGNORECASE)

_TRAILING_CODE = re.compile(r"^(?:\d{4,}\*?|\d+/\d+|X+\d+|[A-Z]*\d[A-Z0-9]{5,}|JPM\w*)$", re.IGNORECASE)

def _strip_trailing(text: str) -> str:
    words = text.split()
    while words and _TRAILING_CODE.match(words[-1]):
        words.pop()
    return " ".join(words)

def _shape(text: str) -> str:
    return " ".join(re.sub(r"\d+", "#", text.upper()).split()[:4])

def bank_variant(description: str | None) -> Variant:
    """The counterparty as the bank writes it (NAME), or the generic shape of a
    text that names none (GENERIC). Deterministic; never an identity."""
    text = " ".join(html.unescape(description or "").split())
    for pattern, label in _GENERIC:
        if pattern.search(text):
            return Variant("GENERIC", label, "G:" + label)
    hit = _ACH.search(text)
    if hit:
        name = hit.group(1)
        seller = _ACH_SELLER.search(text)
        if wr.who_key(name) in ACH_INTERMEDIARIES and seller and _letters(seller.group(1)) >= 3:
            # PayPal & co. only carry the payment: the seller is in IND ID, and
            # each seller is its own group ("PAYPAL TEMU", "PAYPAL JETBLUEAIRW").
            name = f"{name} {_strip_trailing(seller.group(1))}"
    elif _ZELLE.match(text):
        name = _strip_trailing(_ZELLE.match(text).group(1))
    else:
        name = text
        for _ in range(2):
            name = _CARD_PREFIX.sub("", name)
        name = _ACH_TAIL.sub("", name)
        name = re.split(r"#\s*\d", name)[0]
        name = _strip_trailing(name)
    name = name.strip(" *-:/.,")[:120]
    if _AMAZON.search(name):
        # Product Owner rule: every Amazon movement is the one WHO "AMAZON"
        # (order codes, marketplace, Prime…) until Amazon's API can tell them apart.
        return Variant("NAME", "AMAZON", "N:" + wr.who_key("AMAZON"))
    if sum(ch.isalpha() for ch in name) < 3:
        shape = _shape(text) or "EMPTY"
        return Variant("GENERIC", shape, "G:" + shape)
    return Variant("NAME", name.upper(), "N:" + wr.who_key(name))

_STOP = {"THE", "AND", "INC", "LLC", "CO", "COM", "OF", "CORP", "LTD", "USA", "US", "PAY", "PAYMENT",
         "BILL", "ONLINE", "WWW", "STORE", "SHOP", "MARKET", "SERVICE", "SERVICES"}

def _compact(text: str | None) -> str:
    return re.sub(r"[^0-9A-Z]", "", (text or "").upper())

def _tokens(text: str | None) -> set[str]:
    return {t for t in wr.who_key(text or "").split() if len(t) >= 3 and t not in _STOP}

def fragment_in(fragment: str | None, descriptions: list[str]) -> bool:
    """The quoted fragment really is in one of the descriptions."""
    piece = _compact(fragment)
    return sum(ch.isalpha() for ch in piece) >= 3 and any(piece in _compact(d) for d in descriptions)

def related(name: str | None, fragment: str | None) -> bool:
    """The name is coherent with the bank text: a shared significant word, one
    contained in the other, or an abbreviation of a word ("DUKEENERGY" /
    "DUKE ENERGY", "SAMUELS AND SON" / "SAMUELS & SON SEAFOOD")."""
    a, b = _tokens(name), _tokens(fragment)
    if a & b:
        return True
    ca, cb = _compact(name), _compact(fragment)
    if min(len(ca), len(cb)) >= 4 and (ca in cb or cb in ca):
        return True
    return any(x[:4] == y[:4] for x in a for y in b if len(x) >= 4 and len(y) >= 4)

SIMILAR_NAME = 0.85

def name_similarity(a: str | None, b: str | None) -> float:
    """How alike two names are, on their identity keys ("FOSTERR KING" /
    "FOSTER KING" ≈ 0.96). 1.0 only for the same key."""
    from difflib import SequenceMatcher
    ka, kb = wr.who_key(a or ""), wr.who_key(b or "")
    if not ka or not kb:
        return 0.0
    return SequenceMatcher(None, ka, kb).ratio()

def contains_name(a: str | None, b: str | None) -> bool:
    """One name is the other plus extra words ("SPECTRUM" / "SPECTRUM MOBILE",
    "NEXT INSUR" / "NEXT INSUR GEN L"): a likely duplicate."""
    ka, kb = wr.who_key(a or "").split(), wr.who_key(b or "").split()
    if not ka or not kb or ka == kb:
        return False
    short, long_ = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    return len("".join(short)) >= 4 and long_[:len(short)] == short

def _letters(text: str | None) -> int:
    return sum(ch.isalpha() for ch in text or "")
