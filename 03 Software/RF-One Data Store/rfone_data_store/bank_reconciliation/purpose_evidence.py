"""WHO is not WHAT
(BANK_MEMO_PURPOSE_CLASSIFICATION_001).

The identity of the person who received money is evidence of WHO. It is
never, by itself, evidence of WHY the money moved or of WHAT account the
movement belongs to.

    ZELLE PAYMENT TO MARIO ROSSI

may be a tips distribution (2300, no P&L effect), 1099 contract labour
(6800, Labor Cost), a reimbursement, settlement of an already-recorded
payable (2100), an owner draw (3400) or a loan movement. The bank line
says which PERSON, and nothing about which of those it is. That Mario was
paid 1099 labour last month does not make this month's payment 1099
labour either.

So this module separates two questions that the description used to
answer together:

    WHO EVIDENCE      who the counterparty is
    PURPOSE EVIDENCE  why the money moved

and it refuses to let the first answer the second. For a person-payment
channel the counterparty's name is REMOVED from the text before purpose
is looked for at all, which is what stops "Giovanna Wine Rep" from
proving wine COGS and "Isaac Ortiz - Electrician" from proving repairs.
Those are names, and a name is a Who.

Purpose evidence comes from:

* the source MEMO / NOTE — user-entered or bank-provided purpose text
  (`FinancialTransaction.source_memo`, with `source_memo_field` recording
  which source column it came from);
* purpose text in the description itself, for channels where the bank
  writes the reason there (ACH `CO ENTRY DESCR`, a cheque memo line) —
  but never the counterparty-name part of it.

Three outcomes, and only one of them may act automatically:

    PROVEN      the text names an accounting purpose unambiguously.
                Automatic classification is allowed.
    AMBIGUOUS   the text is about money but does not settle the
                accounting question ("PAYROLL" does not say whether the
                movement is labour expense, a payroll-liability
                settlement, a tax payment or processor funding).
                REVIEW_REQUIRED.
    ABSENT      there is no purpose text. REVIEW_REQUIRED.

A future Mercury connector feeds `source_memo` / `source_memo_field` from
its note, memo or external-memo field and needs nothing else here: the
semantics live in this module, not in any connector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Channels --------------------------------------------------------------
#
# The channel matters because it decides whether the counterparty is a
# PERSON the bank happens to name. On a person channel a name in the
# description is a Who and must never leak into purpose.

ZELLE = "ZELLE"
ACH = "ACH"
CHECK = "CHECK"
CARD = "CARD"
WIRE = "WIRE"
OTHER = "OTHER"

# Channels where the bank writes a counterparty's own name into the
# description, so the description is WHO evidence and (by itself) nothing
# else. PayPal is deliberately NOT here: `PAYPAL *TEMU` names a merchant
# the money reached through PayPal, not a person paid by the business.
PERSON_CHANNELS = (ZELLE, CHECK)

_CHANNEL_PATTERNS = (
    (ZELLE, re.compile(r"\bZELLE\b|\bQUICKPAY\b", re.I)),
    (WIRE, re.compile(r"\b(WIRE|FEDWIRE|SWIFT)\b", re.I)),
    (CHECK, re.compile(r"\b(CHECK|CHK)\s*#?\s*\d+", re.I)),
    (ACH, re.compile(r"ORIG\s+CO\s+NAME|CO\s+ENTRY\s+DESCR|\bACH\b|\bPPD\b|\bCCD\b", re.I)),
    (CARD, re.compile(r"\bCARD\s+PURCHASE\b|\bPOS\s+DEBIT\b|\bDEBIT\s+CARD\b", re.I)),
)

# "Zelle payment to Mario Rossi JPM99cu6r5b3" — the name is everything
# between the preposition and the bank's own reference token. The
# reference is captured separately so it is never mistaken for purpose.
_ZELLE_COUNTERPARTY = re.compile(
    r"\bZELLE\s+(?:PAYMENT|TRANSFER|INSTANT\s+PMT)\s+(?:TO|FROM)\s+"
    r"(?P<name>.+?)\s+(?P<reference>JPM\w+|\d{8,})\s*$",
    re.I,
)
# The same without a trailing reference, which some exports omit.
_ZELLE_COUNTERPARTY_NO_REF = re.compile(
    r"\bZELLE\s+(?:PAYMENT|TRANSFER|INSTANT\s+PMT)\s+(?:TO|FROM)\s+(?P<name>.+?)\s*$",
    re.I,
)

_WHITESPACE = re.compile(r"\s+")

# The channel's own wording. It says HOW the money moved, never why, so it
# is removed before purpose is looked for — otherwise the "payment" in
# "Zelle payment to" would read as purpose text that was considered and
# rejected, when in truth there was no purpose text at all.
_CHANNEL_WORDING = re.compile(
    r"\bZELLE\b|\bQUICKPAY\b|\bPAYMENT\b|\bPMT\b|\bTRANSFER\b|\bINSTANT\b|"
    r"\bTO\b|\bFROM\b|\bCHECK\b|\bCHK\b|#",
    re.I,
)


@dataclass(frozen=True)
class WhoEvidence:
    """What the description says about the counterparty, and nothing more."""

    channel: str
    counterparty_name: str | None
    reference: str | None

    @property
    def is_person_channel(self) -> bool:
        """Whether the counterparty is a person or small payee the bank
        named directly. On such a channel a learned rule may recognise the
        WHO and must not, on its own, decide the WHAT."""
        return self.channel in PERSON_CHANNELS

    @property
    def names_counterparty(self) -> bool:
        return bool(self.counterparty_name)


def channel_of(description: str | None) -> str:
    text = (description or "").strip()
    if not text:
        return OTHER
    for channel, pattern in _CHANNEL_PATTERNS:
        if pattern.search(text):
            return channel
    return OTHER


def who_evidence(description: str | None) -> WhoEvidence:
    """The counterparty a bank line names, kept strictly separate from why
    the money moved."""
    text = _WHITESPACE.sub(" ", (description or "").strip())
    channel = channel_of(text)
    if channel != ZELLE:
        return WhoEvidence(channel=channel, counterparty_name=None, reference=None)

    match = _ZELLE_COUNTERPARTY.search(text)
    if match is not None:
        return WhoEvidence(
            channel=ZELLE,
            counterparty_name=match.group("name").strip(),
            reference=match.group("reference").strip(),
        )
    match = _ZELLE_COUNTERPARTY_NO_REF.search(text)
    if match is not None:
        return WhoEvidence(
            channel=ZELLE, counterparty_name=match.group("name").strip(), reference=None,
        )
    return WhoEvidence(channel=ZELLE, counterparty_name=None, reference=None)


# --- Purpose ---------------------------------------------------------------

PROVEN = "PROVEN"
AMBIGUOUS = "AMBIGUOUS"
ABSENT = "ABSENT"

DESCRIPTION = "DESCRIPTION"
MEMO = "MEMO"


@dataclass(frozen=True)
class PurposeRule:
    """One purpose pattern that carries its own accounting meaning.

    Mirrors `deterministic_rules.DeterministicRule` on purpose: a purpose
    rule is the same kind of object — an explicit, auditable statement
    that a particular wording settles a particular accounting question —
    applied to memo/purpose text instead of to a merchant description."""

    pattern: str                 # regex, matched against purpose text
    account_code: str
    why_code: str
    why_name: str
    rationale: str
    no_pl_effect: bool = False   # True when the destination is a Balance Sheet account


# The wording a human writes on a payment when they mean a specific
# accounting treatment. Deliberately narrow: each entry is a phrase whose
# accounting meaning does not depend on anything the bank line omits.
PURPOSE_RULES: tuple[PurposeRule, ...] = (
    # ---- Tips: a liability being settled, never a P&L cost -------------
    PurposeRule(
        pattern=r"\bTIPS?\b(?!\s*(REPORT|SUMMARY)\b)",
        account_code="2300", why_code="TIPS_SETTLEMENT",
        why_name="Guest tips paid out to staff",
        rationale=(
            "The memo says the payment IS the tips distribution. Tips collected from guests "
            "were recorded as a liability, so paying them out settles 2300 and has no "
            "profit-and-loss effect."
        ),
        no_pl_effect=True,
    ),
    PurposeRule(
        pattern=r"\bGRATUIT(Y|IES)\b",
        account_code="2300", why_code="TIPS_SETTLEMENT",
        why_name="Guest tips paid out to staff",
        rationale="A gratuity payout is the same liability settlement as a tip payout.",
        no_pl_effect=True,
    ),
    # ---- 1099 / contract labour: a real Labor Cost ----------------------
    PurposeRule(
        pattern=r"\b1099\b|\bCONTRACT(OR|ED)?\s+LABOU?R\b|\bCONTRACT\s+LABOU?R\b",
        account_code="6800", why_code="CONTRACT_LABOR",
        why_name="Temporary / contract restaurant labour invoiced by the worker",
        rationale=(
            "The memo names 1099 / contract labour, which is work bought from someone who "
            "is not on payroll — Labor Cost, not a payroll liability."
        ),
    ),
    PurposeRule(
        pattern=r"\b(KITCHEN|BOH|FOH|LINE|PREP)\s+CONTRACTOR\b",
        account_code="6800", why_code="CONTRACT_LABOR",
        why_name="Temporary / contract restaurant labour invoiced by the worker",
        rationale="The memo names contracted restaurant work explicitly.",
    ),
    # ---- Liability settlements: reduce the Balance Sheet, add no cost ---
    PurposeRule(
        pattern=r"\bSALES\s+TAX\b",
        account_code="2200", why_code="SALES_TAX_REMITTANCE",
        why_name="Remittance of sales tax collected from guests",
        rationale=(
            "Sales tax collected from guests is a liability. Remitting it settles 2200 and "
            "is never an expense."
        ),
        no_pl_effect=True,
    ),
    PurposeRule(
        pattern=r"\b(CARD|CREDIT\s*CARD|CC)\s+PAYMENT\b|\bPAY(MENT)?\s+CREDIT\s+CARD\b",
        account_code="2500", why_code="CREDIT_CARD_SETTLEMENT",
        why_name="Payment of a credit card statement",
        rationale=(
            "Paying the card statement settles the card liability. The purchases it covers "
            "were already recorded when they were made."
        ),
        no_pl_effect=True,
    ),
    PurposeRule(
        pattern=r"\b(INVOICE|INV)\s+PAYMENT\b|\bPAY(ING|MENT)?\s+INVOICE\b|\bAP\s+PAYMENT\b|"
                r"\bACCOUNTS?\s+PAYABLE\b",
        account_code="2100", why_code="PAYABLE_SETTLEMENT",
        why_name="Settlement of an already-recorded supplier payable",
        rationale=(
            "The memo says this pays an invoice that is already on the books. The cost was "
            "recognised when the invoice was recorded, so paying it settles 2100 rather "
            "than creating a second expense."
        ),
        no_pl_effect=True,
    ),
    PurposeRule(
        pattern=r"\b(OWNER|MEMBER)\s+(DRAW|DISTRIBUTION)S?\b|\bDISTRIBUTION\s+TO\s+(OWNER|MEMBER)\b",
        account_code="3400", why_code="MEMBER_DRAW",
        why_name="Distribution / draw taken by a member of the company",
        rationale=(
            "A draw reduces equity. It is neither an expense nor a wage, and it never "
            "reaches the profit and loss account."
        ),
        no_pl_effect=True,
    ),
    # ---- Occupancy -------------------------------------------------------
    PurposeRule(
        pattern=r"\bBASE\s+RENT\b|\bRENT\s+(FOR\s+)?(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
                r"\w*\b|\bMONTHLY\s+RENT\b|\bRENT\s+PAYMENT\b",
        account_code="7110", why_code="BASE_RENT",
        why_name="Base rent for the restaurant premises",
        rationale=(
            "The memo names rent for a period, which is the premises lease itself rather "
            "than a common-area charge or an equipment lease."
        ),
    ),
)

# Wording that is ABOUT money but does not settle the accounting question.
# Matching one of these is a positive statement that the evidence is
# insufficient — which is different from, and more useful than, no match
# at all, because it tells the reviewer the memo was read and rejected.
AMBIGUOUS_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\bPAYROLL\b",
        "\"Payroll\" does not say whether this is direct labour cost, settlement of a "
        "payroll liability, a payroll tax payment, or funding sent to a payroll processor. "
        "Those are four different accounts.",
    ),
    (
        r"\bREIMBURSE(MENT|D)?\b|\bEXPENSE\s+REPORT\b",
        "A reimbursement takes the accounting treatment of whatever was originally bought, "
        "which this line does not state.",
    ),
    (
        r"\bLOAN\b|\bADVANCE\b",
        "A loan movement may be principal, interest or a related-party advance, and the "
        "line does not say which.",
    ),
    (
        r"\bTRANSFER\b|\bTRF\b",
        "A transfer may be between the company's own accounts or to a third party.",
    ),
    (
        r"\bPAYMENT\b|\bPMT\b|\bINVOICE\b|\bINV\b",
        "\"Payment\" or \"invoice\" alone names no cost family and does not say whether a "
        "payable was already recorded.",
    ),
    (
        r"\bSERVICES?\b|\bWORK\b|\bJOB\b|\bLABOU?R\b",
        "The line names work done but not whether it was contracted labour, a repair, a "
        "professional service or a capital improvement.",
    ),
)

_COMPILED_PURPOSE = tuple((rule, re.compile(rule.pattern, re.I)) for rule in PURPOSE_RULES)
_COMPILED_AMBIGUOUS = tuple((re.compile(pattern, re.I), why) for pattern, why in AMBIGUOUS_PATTERNS)


@dataclass(frozen=True)
class PurposeEvidence:
    """Why the money moved, as far as the source text actually proves it."""

    status: str                        # PROVEN | AMBIGUOUS | ABSENT
    account_code: str | None = None
    why_code: str | None = None
    why_name: str | None = None
    rule: PurposeRule | None = None
    source_field: str | None = None    # MEMO | DESCRIPTION
    matched_text: str | None = None    # the exact text that proved it
    rationale: str | None = None

    @property
    def is_proven(self) -> bool:
        """Whether automatic classification is allowed on this evidence
        alone. Only PROVEN qualifies — "I don't know" is REVIEW_REQUIRED,
        never a residual account."""
        return self.status == PROVEN and bool(self.account_code)


def purpose_text(description: str | None, memo: str | None) -> tuple[str, str | None]:
    """The text that may legitimately be searched for purpose, and where it
    came from.

    The memo wins when it has content: it is the field a human fills in to
    say what a payment is for. Otherwise the description is used — but on
    a person channel the counterparty's NAME and the bank's reference
    token are removed first, because a name is a Who and must never
    contribute to a Who-independent question."""
    clean_memo = _WHITESPACE.sub(" ", (memo or "").strip())
    if clean_memo:
        return clean_memo, MEMO

    text = _WHITESPACE.sub(" ", (description or "").strip())
    if not text:
        return "", None

    who = who_evidence(text)
    if who.is_person_channel and who.counterparty_name:
        # Remove the name and the reference, leaving only the channel
        # wording and anything the bank added beyond the name.
        remainder = text
        for fragment in (who.counterparty_name, who.reference or ""):
            if fragment:
                remainder = re.sub(re.escape(fragment), " ", remainder, flags=re.I)
        remainder = _CHANNEL_WORDING.sub(" ", remainder)
        remainder = _WHITESPACE.sub(" ", remainder).strip()
        return remainder, DESCRIPTION
    return text, DESCRIPTION


def purpose_evidence(description: str | None, memo: str | None) -> PurposeEvidence:
    """What the source text proves about why the money moved.

    Never consults the counterparty's identity, and never consults what
    this counterparty was classified as before. History is evidence for a
    human; it is not proof about the next payment."""
    text, field = purpose_text(description, memo)
    if not text:
        return PurposeEvidence(status=ABSENT, source_field=field)

    for rule, compiled in _COMPILED_PURPOSE:
        match = compiled.search(text)
        if match is not None:
            return PurposeEvidence(
                status=PROVEN,
                account_code=rule.account_code,
                why_code=rule.why_code,
                why_name=rule.why_name,
                rule=rule,
                source_field=field,
                matched_text=match.group(0).strip(),
                rationale=rule.rationale,
            )

    for compiled, why in _COMPILED_AMBIGUOUS:
        match = compiled.search(text)
        if match is not None:
            return PurposeEvidence(
                status=AMBIGUOUS, source_field=field,
                matched_text=match.group(0).strip(), rationale=why,
            )

    # Text exists but says nothing about money at all. On a person channel
    # that is the ordinary case: the description held a name, the name was
    # removed, and what is left is "Zelle payment to".
    return PurposeEvidence(status=ABSENT, source_field=field)


def describe(description: str | None, memo: str | None) -> dict:
    """WHO and PURPOSE side by side, for the review UI and the analysis
    scripts. Two answers, never collapsed into one."""
    who = who_evidence(description)
    purpose = purpose_evidence(description, memo)
    return {
        "channel": who.channel,
        "is_person_channel": who.is_person_channel,
        "counterparty_name": who.counterparty_name,
        "reference": who.reference,
        "purpose_status": purpose.status,
        "purpose_account_code": purpose.account_code,
        "purpose_why_code": purpose.why_code,
        "purpose_source_field": purpose.source_field,
        "purpose_matched_text": purpose.matched_text,
        "purpose_rationale": purpose.rationale,
    }
