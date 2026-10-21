"""Transfer and card-payment leg matching (decisions 22, 37).

Pairs the two legs of a movement between own instruments: opposite amounts,
different instruments, close dates. The two legs stay separate movements; the
match only says they are one economic event, so no cost is counted twice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_DAYS = 5
_REF = re.compile(r"(?:\.\.\.|ending in |x{2,}|#)\s?(\d{4})\b", re.I)
_HINTS = ("transfer", "payment to chase card", "automatic payment", "autopay",
          "credit crd", "payment thank", "online payment", "zelle payment from", "deposit from")


@dataclass(frozen=True)
class Match:
    counterpart_id: int
    counterpart_instrument_id: int
    kind: str               # CARD_SETTLEMENT | TRANSFER
    basis: str              # human-readable evidence


def referenced_last_four(description: str | None) -> set[str]:
    return set(_REF.findall(description or ""))


def is_hinted(description: str | None) -> bool:
    text = (description or "").lower()
    return any(h in text for h in _HINTS)


def match_all(txns, instruments, settlement) -> dict[int, Match]:
    """{transaction id: Match} for every leg that has exactly one partner.

    `settlement` maps a card instrument id to the bank account that pays it.
    Evidence order: explicit last-four reference in the description, then a
    configured card→account settlement, then a hinted description; ties are
    left unmatched (never an arbitrary pairing)."""
    by_amount: dict[int, list] = {}
    for t in txns:
        by_amount.setdefault(t.amount_minor, []).append(t)
    last_four = {i.id: (i.last_four or "") for i in instruments.values()}

    def score(a, b) -> tuple[int, str] | None:
        if a.payment_instrument_id == b.payment_instrument_id or not (a.posting_date and b.posting_date):
            return None
        days = abs((a.posting_date - b.posting_date).days)
        if days > MAX_DAYS:
            return None
        refs_a, refs_b = referenced_last_four(a.description_original), referenced_last_four(b.description_original)
        if last_four.get(b.payment_instrument_id) in refs_a or last_four.get(a.payment_instrument_id) in refs_b:
            return 3, f"description references the other account (…{last_four.get(b.payment_instrument_id)}), {days} day(s) apart"
        pair = {a.payment_instrument_id, b.payment_instrument_id}
        for card, account in settlement.items():
            if pair == {card, account} and (is_hinted(a.description_original) or is_hinted(b.description_original)):
                return 2, f"configured card settlement account, {days} day(s) apart"
        if is_hinted(a.description_original) and is_hinted(b.description_original):
            return 1, f"both descriptions are transfers/payments, {days} day(s) apart"
        return None

    candidates: dict[int, list] = {}
    for t in txns:
        if not t.amount_minor:
            continue
        for other in by_amount.get(-t.amount_minor, []):
            s = score(t, other)
            if s:
                candidates.setdefault(t.id, []).append((s[0], other, s[1]))
    def unique_best(options):
        best = max(o[0] for o in options)
        top = [o for o in options if o[0] == best]
        return top[0] if len(top) == 1 else None

    choice = {tid: unique_best(options) for tid, options in candidates.items()}
    result: dict[int, tuple] = {}
    for tid, pick in choice.items():
        if pick is None:
            continue
        _, other, basis = pick
        # Mutual uniqueness: the partner's own unique best must be this leg.
        back = choice.get(other.id)
        if back is None or back[1].id != tid:
            continue
        result[tid] = (other, basis)
    # Kind: a movement between a card and a bank account is a card settlement.
    by_id = {t.id: t for t in txns}
    matches: dict[int, Match] = {}
    for tid, (other, basis) in result.items():
        own = instruments[by_id[tid].payment_instrument_id].instrument_type
        theirs = instruments[other.payment_instrument_id].instrument_type
        kind = "CARD_SETTLEMENT" if "CREDIT_CARD" in (own, theirs) else "TRANSFER"
        matches[tid] = Match(other.id, other.payment_instrument_id, kind, basis)
    return matches
