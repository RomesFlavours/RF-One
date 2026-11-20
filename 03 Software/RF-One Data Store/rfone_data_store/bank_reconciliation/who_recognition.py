"""WHO recognition from the bank's own text (BANK_HISTORICAL_WHO_RECOGNITION_001).

Answers one question — who is the counterparty of this financial event —
from the ORIGINAL transaction text and nothing else. It never answers why
the money moved, never reads a person's identity as a role, and never
looks at the memo: on American Express exports the memo carries the CARD
MEMBER, who is the payer's own cardholder, not the counterparty.

Every transaction lands in exactly one tier:

    DETERMINISTIC  the text names the counterparty through a proven
                   structure (a Zelle recipient before the bank's
                   reference, an ACH originator field, a fixed-width
                   merchant field, a card merchant descriptor)
    PROPOSED       a name is present but its boundary or identity is not
                   proven; an operator decides
    UNRESOLVED     the text does not name the counterparty (a bare
                   "Check", a deposit), or names an account RF-One has not
                   registered
    STRUCTURAL     the counterparty is RF-One itself: a registered
                   instrument, one of its own legal entities, or a card
                   settlement paid from its own funds

Normalization removes only provider noise that is demonstrably not
identity — bank reference tokens, masked account digits, Stripe transfer
ids, bill-pay transaction numbers, HTML entities, spacing. Store and
location numbers are KEPT: whether two stores of one chain are one
counterparty is a question for a person, and splitting too finely is the
safe error. Nothing is merged on similarity; two spellings are one WHO
only when their normalized keys are identical, or when a documented
provider grammar (below) proves the variable part is a reference.

Pure functions first (`recognize`, `normalize_who_name`), so every rule is
testable without a database; `recognize_transactions` persists.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import accounting_dedup, invoice_evidence

RECOGNIZER_VERSION = "who-v1"
OCCURRENCE_TYPE_CODE = "COUNTERPARTY"  # the existing generic Who type
OCCURRENCE_TYPE_NAME = "Counterparty"

DETERMINISTIC = m.WHO_TIER_DETERMINISTIC
PROPOSED = m.WHO_TIER_PROPOSED
UNRESOLVED = m.WHO_TIER_UNRESOLVED
STRUCTURAL = m.WHO_TIER_STRUCTURAL

# Families (how the text is structured).
F_ZELLE = "ZELLE"
F_ACH_ORIGINATOR = "ACH_ORIGINATOR"
F_ACH_FIXED_WIDTH = "ACH_FIXED_WIDTH"
F_ACH_MASKED = "ACH_MASKED_REFERENCE"
F_BILL_PAY = "BILL_PAY"
F_CARD_MERCHANT = "CARD_MERCHANT"
F_POS_FIXED_WIDTH = "POS_FIXED_WIDTH"
F_CARD_NETWORK = "CARD_NETWORK_DESCRIPTOR"
F_INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
F_OWN_LEGAL_ENTITY = "OWN_LEGAL_ENTITY"
F_CARD_SETTLEMENT = "CARD_SETTLEMENT_RECEIVED"
F_BANK_GENERATED = "BANK_GENERATED"
F_NOT_NAMED = "COUNTERPARTY_NOT_NAMED"
F_WIRE = "WIRE"
F_OTHER = "OTHER_DESCRIPTOR"

CARD_FORMATS = frozenset({
    "CHASE_CREDIT_CARD_NO_CARD", "CHASE_CREDIT_CARD_WITH_CARD",
    "AMEX_QBO", "AMEX_XLSX", "AMEX_CSV",
})
AMEX_FIXED_LAYOUT_FORMATS = frozenset({"AMEX_XLSX", "AMEX_CSV"})

# The WHO a bank-generated event names: the institution holding the
# account. Keyed by `PaymentInstrument.institution` (upper-cased).
INSTITUTION_WHO = {
    "CHASE": "JPMORGAN CHASE BANK",
    "FIRST CITIZENS": "FIRST CITIZENS BANK",
    "AMEX": "AMERICAN EXPRESS",
}

_WS = re.compile(r"\s+")


def _clean(text: str | None) -> str:
    return _WS.sub(" ", html.unescape(text or "")).strip()


# --- normalization -----------------------------------------------------------

# Provider noise that is demonstrably not identity. Each is anchored at the
# END of the name, because that is where banks append references.
_NOISE_SUFFIXES = (
    re.compile(r"\s+[X*]{2,}[\d-]*\d$"),               # ****5383, XXXX1234, ***-***5-000
    re.compile(r"\s+\*\d{2,}$"),                       # *9459
    re.compile(r"\s+ST-[A-Z0-9*]{6,}$", re.I),         # Stripe transfer id
    re.compile(r"\s+(?:ONLINE\s+)?PMT\s+TRAN#\d+$", re.I),  # bill-pay transaction number
    re.compile(r"\s+TRAN#\d+$", re.I),
    re.compile(r"\s+\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}$"),  # merchant phone in the city slot
)


def normalize_who_name(text: str | None) -> str:
    """The display form of a WHO: entities decoded, provider reference noise
    removed from the end, whitespace collapsed, upper-cased. Words, store
    numbers and location terms are never removed."""
    name = _clean(text).upper()
    changed = True
    while changed and name:
        changed = False
        for pattern in _NOISE_SUFFIXES:
            stripped = pattern.sub("", name)
            if stripped != name:
                name, changed = stripped.strip(), True
    return name


def who_key(name: str | None) -> str:
    """Exact identity key for a WHO name — the same normalization the
    accounting key and the Supplier resolver compare on (punctuation to
    spaces, upper case). Two names are one WHO only when these are equal."""
    return accounting_dedup.normalize_payee(name)


# Provider grammars: descriptor shapes whose variable part is PROVEN to be
# a reference, or whose prefix is a payment facilitator in front of the
# real merchant. Deliberately short; each has a test.
_BRAND_GRAMMARS = (
    ("AMAZON", re.compile(
        r"^(?:AMZN\s*MKTP\b|AMAZON\s*MKTPL\b|AMAZON\s+MARKE?T?PLACE\b|AMAZON\s+MKTPLACE\b|"
        r"AMAZON\.COM\b|AMZN\.COM\b|AMAZONCOM\b|AMZNCOM\b)")),
    ("INSTACART", re.compile(r"^(?:IC\s*\*|INSTACART\b)")),
    ("UBER", re.compile(r"^UBER\s*\*?\s*(?:TRIP|EATS)\b")),
    ("EXPEDIA", re.compile(r"^EXPEDIA\s+\d{6,}")),
    # ADP originates each service line under its own name ("ADP Tax",
    # "ADP WAGE PAY"); the suffix names the service, never the company.
    ("ADP", re.compile(r"^ADP\b(?![-'&])")),
)
_FACILITATORS = (
    ("TOAST", re.compile(r"^TST\s*\*\s*(?P<merchant>.+)$")),
    ("SQUARE", re.compile(r"^SQ\s*\*\s*(?P<merchant>.+)$")),
    ("PAYPAL", re.compile(r"^PAYPAL\s*\*\s*(?P<merchant>.+)$")),
)


def apply_provider_grammar(name: str) -> tuple[str, str | None]:
    """(WHO name, grammar note). Brands collapse only their proven
    reference variants; a facilitator prefix is removed so the merchant
    behind it is the WHO."""
    for brand, pattern in _BRAND_GRAMMARS:
        if pattern.search(name):
            return brand, f"provider grammar {brand}: variable part is an order/trip/booking reference"
    for facilitator, pattern in _FACILITATORS:
        match = pattern.match(name)
        if match and _letters(match.group("merchant")) >= 3:
            return match.group("merchant").strip(), f"payment facilitator {facilitator} in front of the merchant"
    return name, None


def _letters(text: str | None) -> int:
    return sum(1 for ch in (text or "") if ch.isalpha())


# --- result ------------------------------------------------------------------


@dataclass(frozen=True)
class WhoContext:
    """What recognition may know besides the text: the source layout, the
    instrument, and RF-One's own registry — never history."""

    detected_format: str | None
    instrument_type: str | None
    institution: str | None
    amount_minor: int
    registered_last_four: dict = field(default_factory=dict)   # last four -> instrument id
    legal_entities: dict = field(default_factory=dict)         # suffix-less key -> legal entity id


@dataclass(frozen=True)
class WhoResult:
    tier: str
    family: str
    parser_code: str
    name: str | None = None               # DETERMINISTIC WHO display name
    extracted: str | None = None          # the text span the parser read
    proposed_name: str | None = None
    internal_payment_instrument_id: int | None = None
    internal_legal_entity_id: int | None = None
    referenced_last_four: str | None = None
    evidence: str = ""
    needs_corroboration: bool = False     # resolved in the second pass
    reference_token: str | None = None    # masked originator reference, for grouping


_LEGAL_SUFFIX = re.compile(r"\s+(?:LLC|L L C|INC|CORP|CO|LTD|PLLC|LLP)$")


def legal_entity_key(name: str) -> str:
    return _LEGAL_SUFFIX.sub("", who_key(name)).strip()


def _own_entity(name: str, ctx: WhoContext) -> int | None:
    return ctx.legal_entities.get(legal_entity_key(name))


def _named(tier_family: str, parser: str, extracted: str, ctx: WhoContext, *, grammar: bool,
           evidence: str) -> WhoResult:
    """A name the text supplied through a proven structure."""
    name = normalize_who_name(extracted)
    note = None
    if grammar:
        name, note = apply_provider_grammar(name)
    entity = _own_entity(name, ctx)
    if entity is not None:
        return WhoResult(STRUCTURAL, F_OWN_LEGAL_ENTITY, parser, extracted=extracted,
                         internal_legal_entity_id=entity,
                         evidence=f"{evidence}; the named party is one of RF-One's own legal entities")
    if _letters(name) < 3:
        return WhoResult(UNRESOLVED, tier_family, parser, extracted=extracted,
                         evidence=f"{evidence}; the supplied name {name!r} is too short to identify anyone")
    return WhoResult(DETERMINISTIC, tier_family, parser, name=name, extracted=extracted,
                     evidence=evidence + (f"; {note}" if note else ""))


def _internal(parser: str, last_four: str, ctx: WhoContext, evidence: str) -> WhoResult:
    instrument = ctx.registered_last_four.get(last_four)
    if instrument is not None:
        return WhoResult(STRUCTURAL, F_INTERNAL_TRANSFER, parser, internal_payment_instrument_id=instrument,
                         referenced_last_four=last_four,
                         evidence=f"{evidence}; ··{last_four} is a registered RF-One instrument")
    return WhoResult(UNRESOLVED, F_INTERNAL_TRANSFER, parser, referenced_last_four=last_four,
                     evidence=f"{evidence}; ··{last_four} is not a registered instrument — the "
                              "counterparty account is unknown and is not guessed")


# --- the parsers, in order ---------------------------------------------------

_INTERNAL_PATTERNS = (
    ("ONLINE_TRANSFER", re.compile(r"^ONLINE TRANSFER (?:TO|FROM) [A-Z]{2,5} \.{2,}(\d{4})\b", re.I)),
    ("CHASE_CARD_PAYMENT", re.compile(r"^PAYMENT TO CHASE CARD ENDING IN (\d{4})\b", re.I)),
    ("FCB_TRANSFER", re.compile(r"^FCB (?:FUNDS )?TRANSFER (?:AT BRANCH )?(?:TO|FROM)\s+X(\d{4})\b", re.I)),
    ("EXTERNAL_TRANSFER", re.compile(r"\bEXT TRNSFR \*+(\d{4})\s*$", re.I)),
)

_BANK_GENERATED = re.compile(
    r"^(?:MONTHLY SERVICE FEE|SERVICE CHARGE|CALCULATED SERVICE CHARGE|OVERDRAFT\b|"
    r"INSUFFICIENT FUNDS FEE|STOP PAY CHARGE|COUNTER CHECK USAGE FEE|CHARGEBACK FEE|"
    r"COIN AND CURRENCY DEPOSITED FEE|ZELLE CREDIT TRANSACTION FEE|OFFICIAL CHECKS? CHARGE|"
    r"FEE REVERSAL|INTEREST (?:PAYMENT|CHARGE|EARNED|CHARGED)|LATE FEE|ANNUAL (?:MEMBERSHIP )?FEE|"
    r"FOREIGN TRANSACTION FEE|WIRE (?:TRANSFER )?FEE)\b"
    r"|\bFOREIGN TRAN(?:SACTION)? FEE\b",
    re.I,
)

_CARD_SETTLEMENT = re.compile(
    r"^(?:AUTOPAY PAYMENT|AUTOMATIC PAYMENT|PAYMENT THANK YOU|ONLINE PAYMENT|MOBILE PAYMENT|"
    r"PAYMENT RECEIVED)\b",
    re.I,
)

# The bank's reference: JPM…, a long number, or a 10+ character token
# mixing letters and digits. A person's name contains no digits, so the
# boundary between name and reference is proven.
_ZELLE_CHASE = re.compile(
    r"^ZELLE (?:PAYMENT|TRANSFER|INSTANT PMT) (?:TO|FROM) (?P<name>.+?)\s+"
    r"(?P<ref>JPM\w+|\d{8,}|(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{10,})$", re.I)
_ZELLE_CHASE_NO_REF = re.compile(r"^ZELLE (?:PAYMENT|TRANSFER|INSTANT PMT) (?:TO|FROM) (?P<name>.+)$", re.I)
_ZELLE_PHONE = re.compile(r"^ZELLE (?P<name>.+?)\s+\d{3}-\d{3}-\d{4}$", re.I)

_ORIG_CO = re.compile(r"^ORIG CO NAME:(?P<name>.+?)\s+ORIG ID:", re.I)
_SEC_ID = re.compile(r"\b(?:PPD|WEB|CCD|CTX|TEL|IAT) ID:", re.I)
_BILL_PAY = re.compile(r"^(?P<name>.+?)\s+ONLINE PMT TRAN#\d+$", re.I)

_WIRE = re.compile(r"^(?:FEDWIRE|CONSUMER ONLINE INTERNATIONAL WIRE|DOMESTIC WIRE|WIRE)\b", re.I)
_NOT_NAMED = re.compile(
    r"^(?:CHECK(?:\s+#?\d+)?(?:\s+\d\d/\d\d)?$|CHECK PAID|TELLER CASHED|CUSTOMER DEPOSIT$|ATM DEPOSIT|ATM WITHDRAWAL|"
    r"NON-CHASE ATM|DEPOSIT(?:\s+ID NUMBER\s+\d+)?$|REMOTE ONLINE DEPOSIT|WITHDRAWAL(?:\s+\d\d/\d\d)?$|"
    r"CASH REDEMPTION|PAPER BILL PAYMENT|SUPPLIED COIN|FOREIGN CURRENCY BANK NOTES|REVERSAL OF CHECK|"
    r"\d+ STATEMENTS|MANUAL DB|CREDIT MEMORANDUM|REIMBURSEMENT FOR CUSTOMER CLAIM|"
    r"FIRST CITIZENS\s+TRANSFER|CHARGE BACK|COUNTER CREDIT|MISC(?:ELLANEOUS)? (?:CREDIT|DEBIT)$)",
    re.I,
)

_POS_PREFIX = re.compile(r"^PURCHASE \d\d/\d\d ", re.I)
_POS_TERMINAL = re.compile(r"\s[0-9A-Z-]{3,8}$", re.I)
_VISA_LINE = re.compile(r"^(?:POS SIG \d\d/\d\d |FDR DEBIT CARD )?VISA #\d{4} (?P<desc>.+)$", re.I)
_TRAILING_STATE = re.compile(r"\s+[A-Z]{2}$")
_CHASE_DEBIT_POS = re.compile(r"^(?P<desc>\S.*?\S)\s{2,}(?:\d{6}\s+)?\d\d/\d\d(?:\s.*)?$")
_MASKED_REFERENCE = re.compile(
    r"^(?P<body>.+?)\s+(?P<ref>[A-Z]*\*{2,}[\d-]*\d{2,}|X\d{4}|FLEX\*+\d+)\s*$", re.I)
_DIGIT_TOKEN = re.compile(r"^(?=\S*\d)(?=\S*[A-Z])\S+$", re.I)


def recognize(description: str | None, ctx: WhoContext) -> WhoResult:
    """First-pass recognition of one transaction text. Pure: no database."""
    raw = description or ""
    text = _clean(raw)
    upper = text.upper()
    if not text:
        return WhoResult(UNRESOLVED, F_NOT_NAMED, "EMPTY", evidence="no description")

    for code, pattern in _INTERNAL_PATTERNS:
        match = pattern.search(text)
        if match:
            return _internal(code, match.group(1), ctx, f"{code}: the text names account ··{match.group(1)}")

    if _BANK_GENERATED.search(text):
        who = INSTITUTION_WHO.get((ctx.institution or "").upper())
        if who is None:
            return WhoResult(UNRESOLVED, F_BANK_GENERATED, "BANK_EVENT",
                             evidence="bank-generated wording, institution of the account not known")
        return WhoResult(DETERMINISTIC, F_BANK_GENERATED, "BANK_EVENT", name=who, extracted=text,
                         evidence="bank-generated fee/interest wording on an account held at "
                                  f"{ctx.institution}; the counterparty is that institution")

    if ctx.detected_format in CARD_FORMATS and ctx.amount_minor > 0 and _CARD_SETTLEMENT.search(text):
        return WhoResult(STRUCTURAL, F_CARD_SETTLEMENT, "CARD_SETTLEMENT",
                         evidence="payment received by the card from its holder's own funds; no "
                                  "external counterparty")

    match = _ZELLE_CHASE.match(text)
    if match:
        return _named(F_ZELLE, "ZELLE_RECIPIENT_REF", match.group("name"), ctx, grammar=False,
                      evidence=f"Zelle recipient before the bank reference ({match.group('ref')[:3]}…)")
    match = _ZELLE_PHONE.match(text)
    if match:
        # First Citizens' Zelle line is not the structured Chase recipient
        # field: the name slot is fixed-width and visibly truncated ("…
        # ALEXIA MI"), so its end is not proven. Only an exact match on one
        # of RF-One's own legal entities is acted on; any other name waits
        # for an operator.
        name = normalize_who_name(match.group("name"))
        entity = _own_entity(name, ctx)
        if entity is not None:
            return WhoResult(STRUCTURAL, F_OWN_LEGAL_ENTITY, "ZELLE_NAME_PHONE",
                             extracted=match.group("name"), internal_legal_entity_id=entity,
                             evidence="Zelle counterparty name before the provider phone number; "
                                      "the named party is one of RF-One's own legal entities")
        return WhoResult(PROPOSED, F_ZELLE, "ZELLE_NAME_PHONE", extracted=match.group("name"),
                         proposed_name=name,
                         evidence="First Citizens Zelle line: a fixed-width, possibly truncated name "
                                  "before the provider phone number. Deterministic Zelle recipient "
                                  "extraction is limited to the structured Chase description.")
    match = _ZELLE_CHASE_NO_REF.match(text)
    if match:
        return WhoResult(PROPOSED, F_ZELLE, "ZELLE_NO_REFERENCE", extracted=match.group("name"),
                         proposed_name=normalize_who_name(match.group("name")),
                         evidence="Zelle line without the bank reference: the end of the name is not proven")

    match = _ORIG_CO.match(text)
    if match:
        return _named(F_ACH_ORIGINATOR, "ACH_ORIG_CO_NAME", match.group("name"), ctx, grammar=True,
                      evidence="ACH originator field ORIG CO NAME")

    if _SEC_ID.search(raw) and len(raw) > 17 and raw[16] == " ":
        company = raw[:16].strip()
        first = company.split(" ")[0] if company else ""
        if _DIGIT_TOKEN.match(first):
            return WhoResult(PROPOSED, F_ACH_FIXED_WIDTH, "ACH_COMPANY_FIELD", extracted=company,
                             proposed_name=normalize_who_name(company),
                             evidence="ACH company-name field starts with a coded token; it may not be "
                                      "the originator's name")
        return _named(F_ACH_FIXED_WIDTH, "ACH_COMPANY_FIELD", company, ctx, grammar=True,
                      evidence="ACH 16-character company-name field of a SEC-coded entry")

    match = _BILL_PAY.match(text)
    if match:
        return _named(F_BILL_PAY, "BILL_PAY_PAYEE", match.group("name"), ctx, grammar=False,
                      evidence="online bill-pay payee before the bill-pay transaction number")

    if _WIRE.match(text):
        return WhoResult(UNRESOLVED, F_WIRE, "WIRE",
                         evidence="wire text: party fields are not parsed by this recognizer version")
    if _NOT_NAMED.match(text):
        return WhoResult(UNRESOLVED, F_NOT_NAMED, "NOT_NAMED",
                         evidence="the source does not name the counterparty")

    if ctx.detected_format in CARD_FORMATS:
        return _card_descriptor(raw, text, ctx)

    match = _VISA_LINE.match(text)
    if match:
        desc = _TRAILING_STATE.sub("", match.group("desc"))
        return _named(F_CARD_NETWORK, "VISA_DESCRIPTOR", desc, ctx, grammar=True,
                      evidence="card-network merchant descriptor after the masked card; trailing state "
                               "removed, city kept")

    pos = _pos_fixed_width(raw)
    if pos is not None:
        return _named(F_POS_FIXED_WIDTH, "POS_DBA_FIELD", pos, ctx, grammar=True,
                      evidence="15-character merchant (DBA) field of a fixed-width POS line")

    match = _CHASE_DEBIT_POS.match(raw)
    if match and ctx.detected_format == "CHASE_BANK_ACCOUNT":
        desc = _TRAILING_STATE.sub("", _clean(match.group("desc")))
        return _named(F_CARD_NETWORK, "DEBIT_CARD_DESCRIPTOR", desc, ctx, grammar=True,
                      evidence="debit-card merchant descriptor before the padded transaction date; "
                               "trailing state removed")

    match = _MASKED_REFERENCE.match(text)
    if match:
        body = normalize_who_name(match.group("body"))
        return WhoResult(PROPOSED, F_ACH_MASKED, "ACH_MASKED_BODY", extracted=match.group("body"),
                         proposed_name=body, needs_corroboration=True,
                         reference_token=match.group("ref").upper(),
                         evidence="company and entry description run together before a masked "
                                  "reference; the company boundary is not proven")

    name = normalize_who_name(text)
    if _letters(name) >= 3:
        return WhoResult(PROPOSED, F_OTHER, "UNSTRUCTURED", extracted=text, proposed_name=name,
                         evidence="a name-like descriptor with no recognised structure")
    return WhoResult(UNRESOLVED, F_OTHER, "UNSTRUCTURED", extracted=text,
                     evidence="no counterparty name in the text")


def _pos_fixed_width(raw: str) -> str | None:
    """The 15-character DBA field of a First Citizens POS line, when the
    layout is proven: the field is followed by a single separator, a long
    remainder, and a terminal code at the end."""
    body = html.unescape(raw)
    body = _POS_PREFIX.sub("", body)
    if len(body) < 40 or body[15] != " ":
        return None
    if not _POS_TERMINAL.search(body):
        return None
    dba = body[:15].strip()
    return dba or None


def _card_descriptor(raw: str, text: str, ctx: WhoContext) -> WhoResult:
    """A card statement's merchant descriptor."""
    if ctx.detected_format in AMEX_FIXED_LAYOUT_FORMATS and len(raw.rstrip()) >= 42 \
            and re.fullmatch(r"[A-Z]{2}", raw.rstrip()[-2:] or "") and raw[20:22] != "  ":
        merchant = raw[:20]
        return _named(F_CARD_MERCHANT, "AMEX_MERCHANT_FIELD", merchant, ctx, grammar=True,
                      evidence="American Express 20-character merchant field (fixed layout: merchant, "
                               "city, state)")
    if ctx.detected_format == "AMEX_QBO":
        brand, _note = apply_provider_grammar(normalize_who_name(text))
        if brand in {b for b, _ in _BRAND_GRAMMARS}:
            return _named(F_CARD_MERCHANT, "AMEX_QBO_BRAND", text, ctx, grammar=True,
                          evidence="QBO NAME matches a documented provider grammar")
        return WhoResult(PROPOSED, F_CARD_MERCHANT, "AMEX_QBO_NAME", extracted=text,
                         proposed_name=normalize_who_name(text), needs_corroboration=True,
                         evidence="QBO NAME is merchant and city truncated together; the merchant "
                                  "boundary is proven only by a matching fixed-layout export")
    return _named(F_CARD_MERCHANT, "CARD_DESCRIPTOR", text, ctx, grammar=True,
                  evidence="card statement merchant descriptor")


def masked_reference_companies(results) -> dict[str, str]:
    """Originator names proven by INVARIANCE: when one masked originator
    reference carries several different entry texts ("FRST BK MRCH SVC
    DEPOSIT", "… FEE", "… INTERCHNG"), the leading words common to all of
    them are the company and the varying tail is the entry description.

    At least two distinct bodies and at least two common words are
    required, so a lone generic word shared by two entries ("PAYROLL") is
    never promoted to an identity."""
    bodies: dict[str, set[str]] = {}
    for result in results:
        if result.parser_code == "ACH_MASKED_BODY" and result.reference_token:
            bodies.setdefault(result.reference_token, set()).add(who_key(result.proposed_name))
    companies: dict[str, str] = {}
    for reference, keys in bodies.items():
        if len(keys) < 2:
            continue
        token_lists = [key.split(" ") for key in keys]
        common: list[str] = []
        for tokens in zip(*token_lists):
            if len(set(tokens)) != 1:
                break
            common.append(tokens[0])
        # A coded first token ("MPS1") names a channel, not a company.
        if len(common) >= 2 and _letters(" ".join(common)) >= 4 and not _DIGIT_TOKEN.match(common[0]):
            companies[reference] = " ".join(common)
    return companies


def corroborate(result: WhoResult, known_keys: dict[str, str], amex_merchants: dict[str, str],
                ctx: WhoContext, masked_companies: dict[str, str] | None = None) -> WhoResult:
    """Second pass: a run-together body becomes DETERMINISTIC only when it
    begins with a name some structured source has already proven, followed
    by a word boundary (the longest proven name wins), or when its masked
    originator reference proves the company by invariance."""
    if not result.needs_corroboration:
        return result
    body = result.proposed_name or ""
    if result.parser_code == "AMEX_QBO_NAME":
        prefix = body[:20]
        proven = amex_merchants.get(who_key(prefix))
        if proven:
            return _named(F_CARD_MERCHANT, "AMEX_QBO_CORROBORATED", prefix, ctx, grammar=True,
                          evidence="QBO NAME begins with a merchant field proven by a fixed-layout "
                                   "American Express export")
        return result
    body_key = who_key(body)
    best = None
    for key, display in known_keys.items():
        if len(key) >= 4 and (body_key == key or body_key.startswith(key + " ")):
            if best is None or len(key) > len(best[0]):
                best = (key, display)
    if best is None:
        company = (masked_companies or {}).get(result.reference_token or "")
        if company and (body_key == company or body_key.startswith(company + " ")):
            return _named(F_ACH_MASKED, "ACH_MASKED_INVARIANT", company, ctx, grammar=True,
                          evidence=f"the words {company!r} are constant across every entry text "
                                   "carried by the same masked originator reference; the varying "
                                   "remainder is entry description")
        return result
    return _named(F_ACH_MASKED, "ACH_MASKED_CORROBORATED", best[1], ctx, grammar=True,
                  evidence=f"begins with {best[1]!r}, a counterparty name proven by a structured "
                           "originator field elsewhere in the corpus; the remainder is entry text")


# --- persistence ---------------------------------------------------------------


@dataclass
class RecognitionSummary:
    transactions: int = 0
    by_tier: Counter = field(default_factory=Counter)
    by_family_tier: Counter = field(default_factory=Counter)
    by_parser: Counter = field(default_factory=Counter)
    occurrences_created: int = 0
    aliases_created: int = 0
    recognitions_created: int = 0
    recognitions_updated: int = 0
    recognitions_unchanged: int = 0
    supplier_outcomes: Counter = field(default_factory=Counter)
    occurrences_used: int = 0
    # Merge safety (BANK_WHO_WHY_CANONICAL_CATALOG_001): how an existing WHO
    # was found instead of creating one, and how many were held for a person.
    resolved_by_name: int = 0
    resolved_by_alias: int = 0
    resolved_by_rule: int = 0
    held_for_review: int = 0


def _ensure_occurrence_type(session: Session) -> "m.BankOccurrenceType":
    existing = session.scalars(
        select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == OCCURRENCE_TYPE_CODE)
    ).first()
    if existing is not None:
        return existing
    created = m.BankOccurrenceType(
        code=OCCURRENCE_TYPE_CODE, name=OCCURRENCE_TYPE_NAME,
        description=(
            "The party a bank movement concerns, where the movement's own description "
            "identifies it. Deliberately generic: Supplier is only one possible kind, and "
            "a bank line rarely says which."
        ),
    )
    session.add(created)
    session.flush()
    return created


def build_contexts(session: Session) -> tuple[dict, dict, dict]:
    """(registered last four -> instrument id, legal entity key -> id,
    instrument id -> institution)."""
    from .historical_source import instrument_last_four
    instruments = list(session.scalars(select(m.PaymentInstrument)))
    registered = {}
    for instrument in instruments:
        last_four = instrument_last_four(instrument)
        if last_four:
            registered.setdefault(last_four, instrument.id)
    entities = {legal_entity_key(e.legal_name): e.id for e in session.scalars(select(m.LegalEntity))}
    institutions = {i.id: i.institution for i in instruments}
    types = {i.id: i.instrument_type for i in instruments}
    return registered, entities, {"institution": institutions, "type": types}


RESOLVED_BY_NAME = "NAME"
RESOLVED_BY_ALIAS = "ALIAS"
RESOLVED_BY_RULE = "RULE"


class CanonicalWhoResolver:
    """Finds the ACTIVE canonical WHO a recognised name already belongs to,
    before anything is created (BANK_WHO_WHY_CANONICAL_CATALOG_001).

    A canonical WHO may have absorbed many bank spellings: the WHO/WHY
    import renames a WHO to its clean name, moves every fragment's aliases
    onto it, records each fragment's old name as an alias, and marks the
    fragment INACTIVE. Looking a name up by `canonical_name` alone would
    then miss "Publix" for "PUBLIX", and would hand transactions back to an
    INACTIVE fragment or recreate one. This resolver reads only what
    already exists — canonical names, `BankOccurrenceAlias` and WHO-only
    `BankRecognitionRule` rows — and never invents a link:

    1. an ACTIVE DESCRIPTION rule (auto-apply on) whose WHO is ACTIVE and
       which matches this transaction within its own direction and
       instrument scope — the knowledge a person configured;
    2. exactly one ACTIVE WHO whose name has this identity key;
    3. exactly one ACTIVE WHO holding an alias with this identity key.

    When none applies but an INACTIVE WHO carries the name, nothing is
    created and nothing is reactivated: the recognition is held for a
    person (PROPOSED). Two active candidates are held the same way.
    Nothing here ever reads or sets a WHY."""

    def __init__(self, session: Session):
        from . import recognition  # local: recognition imports far more than this module needs

        self._recognition = recognition
        self.by_id: dict[int, m.BankOccurrence] = {}
        self.active_by_name: dict[str, m.BankOccurrence] = {}
        self.active_by_key: dict[str, set[int]] = {}
        self.inactive_by_key: dict[str, list[m.BankOccurrence]] = {}
        for occurrence in session.scalars(select(m.BankOccurrence)):
            self.by_id[occurrence.id] = occurrence
            key = who_key(occurrence.canonical_name)
            if occurrence.status == "ACTIVE":
                self.active_by_name[occurrence.canonical_name] = occurrence
                self.active_by_key.setdefault(key, set()).add(occurrence.id)
            else:
                self.inactive_by_key.setdefault(key, []).append(occurrence)
        self.alias_owners: dict[str, set[int]] = {}
        for occurrence_id, alias_key in session.execute(
            select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_key)
        ):
            if alias_key and self._active(occurrence_id):
                self.alias_owners.setdefault(alias_key, set()).add(occurrence_id)
        self.rules = sorted(
            (rule for rule in session.scalars(select(m.BankRecognitionRule).where(
                m.BankRecognitionRule.status == "ACTIVE",
                m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
                m.BankRecognitionRule.auto_apply_enabled.is_(True),
            )) if self._active(rule.occurrence_id)),
            key=recognition._specificity_sort_key,
        )

    def _active(self, occurrence_id: int | None) -> bool:
        occurrence = self.by_id.get(occurrence_id)
        return occurrence is not None and occurrence.status == "ACTIVE"

    def add_created(self, occurrence: "m.BankOccurrence") -> None:
        self.by_id[occurrence.id] = occurrence
        self.active_by_name[occurrence.canonical_name] = occurrence
        self.active_by_key.setdefault(who_key(occurrence.canonical_name), set()).add(occurrence.id)

    def add_alias(self, occurrence_id: int, alias_key: str) -> None:
        if alias_key and self._active(occurrence_id):
            self.alias_owners.setdefault(alias_key, set()).add(occurrence_id)

    def by_rule(self, description: str | None, amount_minor: int | None,
                instrument_id: int | None) -> "tuple[m.BankOccurrence, m.BankRecognitionRule] | None":
        """The WHO an approved description rule names for this transaction."""
        if not self.rules or amount_minor is None:
            return None
        text = self._recognition.normalize_description_for_recognition(description or "")
        direction = self._recognition.direction_for_amount(amount_minor)
        for rule in self.rules:
            if rule.payment_instrument_id is not None and rule.payment_instrument_id != instrument_id:
                continue
            if rule.direction is not None and rule.direction != direction:
                continue
            if self._recognition._rule_matches(rule, text):
                return self.by_id[rule.occurrence_id], rule
        return None

    def by_identity(self, *names: str | None) -> "tuple[m.BankOccurrence | None, str | None, str | None]":
        """(active WHO, how it was found, why it was held for a person).

        All three None means the identity is genuinely new and the ordinary
        creation path may follow."""
        for name in names:
            if name and name in self.active_by_name:
                return self.active_by_name[name], RESOLVED_BY_NAME, None
        keys = [k for k in dict.fromkeys(who_key(n) for n in names if n) if k]
        for key in keys:
            owners = self.active_by_key.get(key, set())
            if len(owners) == 1:
                return self.by_id[next(iter(owners))], RESOLVED_BY_NAME, None
            if len(owners) > 1:
                return None, None, f"several active WHO share the identity {key!r}"
        for key in keys:
            owners = self.alias_owners.get(key, set())
            if len(owners) == 1:
                return self.by_id[next(iter(owners))], RESOLVED_BY_ALIAS, None
            if len(owners) > 1:
                return None, None, f"the alias {key!r} belongs to several active WHO"
        for key in keys:
            inactive = self.inactive_by_key.get(key)
            if inactive:
                held = ", ".join(f"#{o.id} {o.canonical_name!r}" for o in inactive)
                return None, None, (
                    f"the name matches INACTIVE WHO {held} and no active canonical WHO holds it "
                    "as an alias; it is neither recreated nor reactivated"
                )
        return None, None, None

    def resolve(self, name: str | None, *, description: str | None = None,
                amount_minor: int | None = None, instrument_id: int | None = None) -> "WhoResolution":
        """THE canonical WHO resolution, in its one precedence order: an
        approved description rule, then the active canonical name, then an
        active alias; otherwise held (inactive or ambiguous) or new.

        Every path that names a WHO from bank text uses this, so WHO
        recognition and any other classifier can never disagree about which
        WHO a text belongs to."""
        ruled = self.by_rule(description, amount_minor, instrument_id) if description is not None else None
        if ruled is not None:
            return WhoResolution(occurrence=ruled[0], how=RESOLVED_BY_RULE, rule=ruled[1])
        if not name:
            return WhoResolution()
        occurrence, how, held = self.by_identity(name)
        return WhoResolution(occurrence=occurrence, how=how, held=held)


@dataclass(frozen=True)
class WhoResolution:
    """The outcome of `CanonicalWhoResolver.resolve`. Exactly one of three
    states: an ACTIVE canonical WHO (`occurrence`), held for a person
    (`held`), or genuinely new (neither) — the only state in which a caller
    may follow its creation path."""
    occurrence: "m.BankOccurrence | None" = None
    how: str | None = None
    held: str | None = None
    rule: "m.BankRecognitionRule | None" = None

    @property
    def is_new(self) -> bool:
        return self.occurrence is None and self.held is None


def recognize_transactions(
    session: Session, *, link_suppliers: bool = True,
) -> tuple[RecognitionSummary, list[tuple[int, WhoResult]]]:
    """Recognise every canonical transaction and persist the outcome.

    Writes only `bank_occurrence_types` (the existing COUNTERPARTY type, if
    missing), `bank_occurrences`, `bank_occurrence_aliases`,
    `bank_who_recognitions` and, through the existing resolver,
    `bank_occurrence_suppliers`. Never writes a FinancialTransaction, a raw
    row, a WHY, an allocation or an invoice match. Idempotent: a second run
    finds every row already in place and changes nothing."""
    summary = RecognitionSummary()
    registered, entities, lookups = build_contexts(session)
    rows = session.execute(
        select(
            m.FinancialTransaction.id, m.FinancialTransaction.payment_instrument_id,
            m.FinancialTransaction.description_original, m.FinancialTransaction.amount_minor,
            m.BankImportBatch.detected_format,
        ).outerjoin(m.BankImportBatch, m.BankImportBatch.id == m.FinancialTransaction.import_batch_id)
        .order_by(m.FinancialTransaction.id)
    ).all()

    first: list[tuple[int, WhoResult, WhoContext]] = []
    for tx_id, instrument_id, description, amount, fmt in rows:
        ctx = WhoContext(
            detected_format=fmt, instrument_type=lookups["type"].get(instrument_id),
            institution=lookups["institution"].get(instrument_id), amount_minor=amount,
            registered_last_four=registered, legal_entities=entities,
        )
        first.append((tx_id, recognize(description, ctx), ctx))

    known_keys: dict[str, str] = {}
    amex_merchants: dict[str, str] = {}
    for _, result, _ctx in first:
        if result.tier != DETERMINISTIC:
            continue
        if result.family in (F_ACH_ORIGINATOR, F_ACH_FIXED_WIDTH):
            known_keys.setdefault(who_key(result.name), result.name)
        if result.parser_code == "AMEX_MERCHANT_FIELD":
            amex_merchants.setdefault(who_key(result.extracted[:20]), result.extracted[:20])

    masked_companies = masked_reference_companies(result for _, result, _ctx in first)
    results = [(tx_id, corroborate(result, known_keys, amex_merchants, ctx, masked_companies))
               for tx_id, result, ctx in first]

    occurrence_type = _ensure_occurrence_type(session)
    resolver = CanonicalWhoResolver(session)
    aliases = {(a.occurrence_id, a.alias_text, a.source_family)
               for a in session.scalars(select(m.BankOccurrenceAlias))}
    existing = {r.financial_transaction_id: r for r in session.scalars(
        select(m.BankWhoRecognition).where(m.BankWhoRecognition.recognizer_version == RECOGNIZER_VERSION)
    )}
    sources = {tx_id: (instrument_id, description, amount)
               for tx_id, instrument_id, description, amount, _fmt in rows}
    used: set[int] = set()
    final: list[tuple[int, WhoResult]] = []

    for tx_id, result in results:
        occurrence_id = None
        occurrence = None
        parser_named = False
        instrument_id, description, amount = sources[tx_id]

        # STRUCTURAL stays STRUCTURAL: RF-One's own accounts have no external
        # WHO. Otherwise the one canonical resolution decides — an approved
        # rule first, then canonical name, then alias.
        resolution = (
            resolver.resolve(result.name if result.tier == DETERMINISTIC else None,
                             description=description, amount_minor=amount, instrument_id=instrument_id)
            if result.tier != STRUCTURAL else WhoResolution()
        )
        if resolution.how == RESOLVED_BY_RULE:
            occurrence, rule = resolution.occurrence, resolution.rule
            result = replace(
                result, tier=DETERMINISTIC, name=occurrence.canonical_name, proposed_name=None,
                evidence=(f"{result.evidence} WHO from approved recognition rule #{rule.id} "
                          f"({rule.match_type} {rule.normalized_pattern!r}"
                          f"{', ' + rule.direction if rule.direction else ''}).").strip(),
            )
            summary.resolved_by_rule += 1
        elif result.tier == DETERMINISTIC:
            occurrence = resolution.occurrence
            if occurrence is not None:
                parser_named = True
                if resolution.how == RESOLVED_BY_ALIAS:
                    summary.resolved_by_alias += 1
                else:
                    summary.resolved_by_name += 1
            elif resolution.held is not None:
                # Never recreate or reactivate a merged/inactive WHO, and
                # never pick between two active ones: a person decides.
                result = replace(
                    result, tier=PROPOSED, proposed_name=result.name,
                    evidence=f"{result.evidence} Held for review: {resolution.held}.".strip(),
                )
                summary.held_for_review += 1
            else:
                # 4. A genuinely new identity: the existing creation path,
                #    always the COUNTERPARTY type — never GENERIC_OPERATIONAL,
                #    which is configured business knowledge.
                canonical = who_key(result.name)
                occurrence = m.BankOccurrence(
                    canonical_name=canonical, occurrence_type_id=occurrence_type.id,
                    optional_notes=(
                        f"Recognised by {RECOGNIZER_VERSION} from the bank's own text "
                        f"({result.family}). Identity only: no WHY, no role, no beneficiary."
                    ),
                )
                session.add(occurrence)
                session.flush()
                resolver.add_created(occurrence)
                summary.occurrences_created += 1
                parser_named = True

        final.append((tx_id, result))
        summary.transactions += 1
        summary.by_tier[result.tier] += 1
        summary.by_family_tier[(result.family, result.tier)] += 1
        summary.by_parser[result.parser_code] += 1

        if occurrence is not None:
            occurrence_id = occurrence.id
            used.add(occurrence_id)
        if parser_named:
            alias_text = normalize_who_name(result.extracted)[:255]
            alias = (occurrence_id, alias_text, result.family)
            if alias not in aliases:
                session.add(m.BankOccurrenceAlias(
                    occurrence_id=occurrence_id, alias_text=alias_text,
                    alias_key=who_key(alias_text)[:255], source_family=result.family,
                    source="PARSER", first_financial_transaction_id=tx_id,
                ))
                aliases.add(alias)
                resolver.add_alias(occurrence_id, who_key(alias_text)[:255])
                summary.aliases_created += 1

        values = {
            "tier": result.tier, "family": result.family, "parser_code": result.parser_code,
            "extracted_name": (normalize_who_name(result.extracted)[:255] if result.extracted else None),
            "proposed_name": (result.proposed_name[:255] if result.proposed_name else None),
            "occurrence_id": occurrence_id,
            "internal_payment_instrument_id": result.internal_payment_instrument_id,
            "internal_legal_entity_id": result.internal_legal_entity_id,
            "referenced_last_four": result.referenced_last_four,
            "evidence": result.evidence,
        }
        row = existing.get(tx_id)
        if row is None:
            session.add(m.BankWhoRecognition(
                financial_transaction_id=tx_id, recognizer_version=RECOGNIZER_VERSION, **values,
            ))
            summary.recognitions_created += 1
        else:
            changed = False
            for name, value in values.items():
                if getattr(row, name) != value:
                    setattr(row, name, value)
                    changed = True
            if changed:
                summary.recognitions_updated += 1
            else:
                summary.recognitions_unchanged += 1
    session.flush()

    summary.occurrences_used = len(used)
    if link_suppliers:
        for occurrence_id in sorted(used):
            proposal = invoice_evidence.propose_supplier_link_for_occurrence(
                session, occurrence_id=occurrence_id, auto_link=True,
            )
            outcome = {
                invoice_evidence.LINK_PROPOSED: "LINKED",
                invoice_evidence.LINK_ALREADY_LINKED: "LINKED",
            }.get(proposal.outcome, proposal.outcome)
            summary.supplier_outcomes[outcome] += 1
        session.flush()
    return summary, final
