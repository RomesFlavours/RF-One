"""Bank AI Rules — natural-language AI rules, tried before anything is applied
(BANK_AI_RULES_001, flow redesigned by BANK_AI_RULES_002).

The flow: the AI Rules page lists every in-scope movement of a period; from a
movement the operator writes a rule in natural language, with that movement
as its example, and asks for a PREVIEW. The preview evaluates the rule on
EVERY in-scope movement of the period — in as many AI calls as needed, never
a sample, never silently truncated — and returns the movements the rule
applies to (MATCH), the doubtful ones (DOUBT) and, when the rule says so, the
WHO/WHY it would propose. A rule can be saved as a DRAFT with its origin
movement.

PROPOSALS ONLY. Drafts, previews and their items live in their own tables
(`BankAiRuleDraft`, `BankAiRulePreview`, `BankAiRulePreviewItem`); no
decision, allocation, WHO, WHY, traditional rule or Standard is created or
changed, and no rule engine is called. A proposed WHO/WHY is matched to the
catalog by RF-One (exact name or code); anything else stays a suggested name.

What the AI receives per movement: date, description (runs of 8+ digits
masked to their last four), amount, Source (display name, type, owner) and
the current WHO/WHY — plus the WHO/WHY catalog, the optional general AI
instructions and the rule. Never credentials, never a full account or card
number. The AI is reached through the one RF-One provider abstraction,
`selection.parsing.ai_client.generate_json`; a provider that is missing or
failing makes the preview FAILED with its message — an answer is never
simulated.

DETERMINISTIC RULES (BANK_AI_RULES_003). A per-movement AI judgement proved
unreliable on long batches (the model declared "no JPM" on descriptions
containing JPM, and the reverse). So the AI first only INTERPRETS the rule;
when the rule is "the description starts with <prefix> and later contains
<marker>: the WHO is the text between them", RF-One code — not the AI —
checks and extracts on every movement (`method` CODE): prefix matched without
regard to case, marker matched as written, WHO = the text between, spaces
normalized, upper case; WHY unchanged. A movement without the marker is NOT
matching (not doubtful). Both markers must appear literally in the rule text,
otherwise the interpretation is not trusted and the AI evaluates as before.

GENERAL STRUCTURED RULES (BANK_AI_RULES_005). The interpretation is a
verifiable structure — conditions (description contains / does not contain /
starts with a text, any case; Source name or owner name contains a text;
Source owner is a Person / a Company; Source is a card / a bank account;
money in / out) and assignments (a fixed WHO, a WHO between two texts, a
fixed WHY). RF-One validates it (only supported elements; every text copied
from the rule itself), resolves WHO and WHY in the catalogs, and executes it
on the whole period. One AI call per rule text and set of general
instructions: the interpretation is saved and reused while both are
unchanged. A rule with no such form is judged by the AI movement by movement:
throttling is retried with progressive waits and a shrinking concurrency, and
every batch that succeeded is kept, so a stopped preview resumes without
asking those batches again; an incomplete preview is FAILED, never shown as
complete.

STRUCTURED-V3 (BANK_AI_RULES_008). New general elements: extraction with
the start text anywhere and the end text in any case; the WHY as the WHO's
DEFAULT WHY (emptied or unchanged when it has none); "Da confermare"
(decision status NEEDS_HUMAN_REVIEW) on the movements a rule changes; "only
if the WHO differs"; replacing a value decided by another rule. Every
interpretation must list how each instruction of the rule is represented
(coverage): an unsupported instruction, a missing coverage or an OTHER
answer BLOCKS the rule — no simplified version, and the movement-by-movement
AI evaluation runs only when asked explicitly, never as a fallback. Manual,
Standard, own-account and For Whom protections are unchanged.

STRUCTURED-V4 (BANK_AI_RULES_010). FOR WHOM is an assignment of its own
(`for_whom`): a fixed entity, or the entity named right after a text of the
description (e.g. "IND NAME:"), decided independently of the WHO. It is
written as ONE pending allocation for the whole amount (status
NEEDS_OPERATOR, decision source RULE, notes naming the AI Rule), like the
For Whom chosen on Review Transactions — the row's Confirm completes it.
The blanket protection of every movement with a For Whom is replaced by
PROVENANCE (`ForWhomState`): a For Whom chosen by a person or by a Standard
is kept; an accounting-complete (confirmed) For Whom protects the movement;
a For Whom written by a rule is automatic and may be updated like a WHO/WHY;
anything else (a split, a pending-evidence line, an unknown source) is kept
with its reason. "Da confermare" applies when WHO, WHY or For Whom changes.

"Crea WHO mancanti" (per rule): a WHO extracted but absent from the catalog
is shown as a new WHO to create; `create_missing_whos` creates the WHO of the
certain matches through the existing WHO service — the catalog only.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..selection.parsing import ai_client
from . import accounting_dedup
from . import claude_code_cli
from . import export as export_service

# One AI call evaluates at most BATCH_SIZE movements, so its answer fits the
# provider's output limit; a batch whose answer cannot be read is split in
# two and asked again, down to MIN_BATCH. PARALLEL calls run at once.
BATCH_SIZE = 40
MIN_BATCH = 10
PARALLEL = 3
# A period larger than this is refused with a message (never cut silently).
MAX_PERIOD_MOVEMENTS = 1500
MATCH, DOUBT = "MATCH", "DOUBT"

_LONG_NUMBER = re.compile(r"\d[\d -]{6,}\d")


class AiRuleError(ValueError):
    """A request the AI Rules page cannot carry out, with the reason."""


def mask_numbers(text: str | None) -> str:
    """Any run of 8 or more digits (spaces/dashes allowed inside) keeps only
    its last four: account, card and reference numbers never leave RF-One in
    full. Shorter numbers (amounts, store numbers, dates) stay readable."""
    def _mask(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return f"****{digits[-4:]}" if len(digits) >= 8 else match.group(0)
    return _LONG_NUMBER.sub(_mask, text or "")


# ---------------------------------------------------------------------------
# General AI instructions (optional context for every preview)
# ---------------------------------------------------------------------------

def current_instruction(session: Session) -> "m.BankAiInstruction | None":
    return session.scalar(select(m.BankAiInstruction).order_by(m.BankAiInstruction.id.desc()).limit(1))


def save_instructions(session: Session, *, text: str | None, account_id: int | None) -> "m.BankAiInstruction | None":
    """A new version when the text changed. An empty text is saved too: it
    means "no general instructions"."""
    text = (text or "").strip()
    current = current_instruction(session)
    if current is not None and current.instructions == text:
        return current
    if current is None and not text:
        return None
    instruction = m.BankAiInstruction(instructions=text, created_by_account_id=account_id)
    session.add(instruction)
    session.flush()
    return instruction


# ---------------------------------------------------------------------------
# Movements of a period
# ---------------------------------------------------------------------------

@dataclass
class Row:
    """One in-scope movement, with everything the page and the AI need."""
    txn: "m.FinancialTransaction"
    currency: str | None
    source_label: str
    current_who: str | None
    current_why: str | None
    # The Source facts a structured rule may test (BANK_AI_RULES_005). The
    # owner of a card is the owner of the account it settles to on that date.
    source_name: str | None = None
    source_type: str | None = None          # "card" | "bank account"
    owner_name: str | None = None
    owner_kind: str | None = None           # "Person" | "Company"
    # BANK_AI_RULES_006 — the current decision, to plan what applying does.
    explanation: "m.BankTransactionExplanation | None" = None
    # BANK_AI_RULES_007 — the Source's Personal classification as Bank records
    # it (see `RowBuilder.classify`): SOURCE_PERSONAL, SOURCE_NOT_PERSONAL or
    # None when missing; `source_class_basis` names the data it came from.
    source_class: str | None = None
    source_class_basis: str | None = None

    @property
    def id(self) -> int:
        return self.txn.id

    def as_dict(self) -> dict:
        return dict(id=self.txn.id, date=self.txn.posting_date.isoformat() if self.txn.posting_date else None,
                    description=self.txn.description_original or "", amount=f"{self.txn.amount_minor / 100:.2f}",
                    currency=self.currency or "", source=self.source_label, who=self.current_who,
                    why=self.current_why)


def _scope_query():
    """The Review/Export scope: no confirmed or suppressed duplicate."""
    return (select(m.FinancialTransaction)
            .where(export_service._not_confirmed_duplicate(), accounting_dedup.not_suppressed_filter()))


SOURCE_PERSONAL, SOURCE_NOT_PERSONAL = "PERSONAL", "NOT_PERSONAL"


class RowBuilder:
    """Builds `Row`s; Sources, owners and catalog names are loaded once, so
    the import can build one row per new movement cheaply."""

    def __init__(self, session: Session):
        self.session = session
        self.owners = export_service.OwnerIndex(session)
        self.who_names = dict(session.execute(select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)).all())
        self.why_names = dict(session.execute(select(m.BankTransactionReason.id, m.BankTransactionReason.name)).all())

    def row(self, txn: "m.FinancialTransaction", explanation: "m.BankTransactionExplanation | None") -> Row:
        owners = self.owners
        instrument = owners.instruments.get(txn.payment_instrument_id)
        owner = owners.owner(owners.key_for(txn))
        label = instrument.display_name if instrument else "Source not identified"
        if instrument is not None:
            label += f" ({'card' if instrument.instrument_type == 'CREDIT_CARD' else 'bank account'})"
        if owner is not None:
            label += f", owner {owner.name} ({owner.kind})"
        return Row(
            txn=txn, currency=instrument.currency if instrument else None, source_label=label,
            current_who=self.who_name(explanation.occurrence_id) if explanation else None,
            current_why=self.why_names.get(explanation.transaction_reason_id) if explanation else None,
            source_name=instrument.display_name if instrument else None,
            source_type=(None if instrument is None else
                         "card" if instrument.instrument_type == "CREDIT_CARD" else "bank account"),
            owner_name=owner.name if owner else None, owner_kind=owner.kind if owner else None,
            explanation=explanation, **self.classify(txn, instrument),
        )

    def classify(self, txn: "m.FinancialTransaction", instrument) -> dict:
        """The Source's Personal classification, from the SAME data the Monthly
        Export uses for a movement's owner (`export.OwnerIndex`): the owner
        recorded on the Source — for a card, the owner of the account it
        settles to on the movement's date (`card_configuration`). A PERSONAL
        reporting entity is Personal; a company (Legal Entity, or a LEGAL /
        VIRTUAL reporting entity) is not Personal; no owner recorded, or a card
        with no settlement account on that date, is MISSING — never "not
        Personal". (`economic_allocation.resolve_payer` would call an account
        with no Legal Entity "personal" even with no owner recorded; that
        inference is deliberately not reused.)"""
        owners = self.owners
        if instrument is None:
            return dict(source_class=None, source_class_basis="the Source is not identified")
        account = owners.account_for(txn.payment_instrument_id, txn.posting_date)
        if account is None:
            return dict(source_class=None, source_class_basis=(
                f"card {instrument.display_name} has no settlement account on {txn.posting_date}"))
        via = "" if account.id == instrument.id else f" via settlement account {account.display_name}"
        key = owners.account_key(account)
        if key is None:
            return dict(source_class=None, source_class_basis=f"no owner recorded for {account.display_name}{via}")
        kind, _, raw = key.partition(":")
        if kind == "re":
            entity = owners.entities.get(int(raw))
            if entity is not None and entity.entity_type == m.REPORTING_ENTITY_PERSONAL:
                return dict(source_class=SOURCE_PERSONAL,
                            source_class_basis=f"owner {entity.name} (PERSONAL){via}")
            name = entity.name if entity else "a reporting entity"
            return dict(source_class=SOURCE_NOT_PERSONAL, source_class_basis=f"owner {name} (company){via}")
        legal = owners.legals.get(int(raw))
        return dict(source_class=SOURCE_NOT_PERSONAL,
                    source_class_basis=f"owner {legal.legal_name if legal else 'a Legal Entity'} (company){via}")

    def who_name(self, occurrence_id: int | None) -> str | None:
        if occurrence_id is None:
            return None
        if occurrence_id not in self.who_names:      # a WHO created after the builder was made
            occurrence = self.session.get(m.BankOccurrence, occurrence_id)
            self.who_names[occurrence_id] = occurrence.canonical_name if occurrence else None
        return self.who_names[occurrence_id]


def _rows(session: Session, transactions: list["m.FinancialTransaction"]) -> list[Row]:
    builder = RowBuilder(session)
    explanation_ids = [t.explanation_id for t in transactions if t.explanation_id]
    explanations = {}
    for start in range(0, len(explanation_ids), 500):
        explanations.update({e.id: e for e in session.scalars(select(m.BankTransactionExplanation).where(
            m.BankTransactionExplanation.id.in_(explanation_ids[start:start + 500])))})
    return [builder.row(txn, explanations.get(txn.explanation_id)) for txn in transactions]


# BANK_AI_RULES_019 — the "Classificazione" filter of the AI Rules list: the
# WHO / WHY CURRENTLY on the movement (its current decision), never a WHO's
# default WHY. A movement with no decision has no WHO.
CLASSIFICATION_FILTERS = {"all": "All", "no_who": "Without WHO", "no_why": "With WHO but without WHY"}


def classification_filter(rows: list[Row], key: str) -> list[Row]:
    if key == "no_who":
        return [r for r in rows if r.explanation is None or r.explanation.occurrence_id is None]
    if key == "no_why":
        return [r for r in rows if r.explanation is not None and r.explanation.occurrence_id is not None
                and r.explanation.transaction_reason_id is None]
    return rows


def search_filter(session: Session, rows: list[Row], text: str | None) -> list[Row]:
    """BANK_AI_RULES_024 — the movements' search of the list, with the SAME
    condition as Bank Reconciliation's search (`review_queues._search_condition`,
    BANK_REVIEW_SEARCH_001): the text, literally and in any case, in the
    description, the current WHO, the current WHY or the Source's name. An
    empty text keeps every row. Read only; it never touches the selection,
    the Preview scope or an application."""
    text = (text or "").strip()
    if not text or not rows:
        return list(rows)
    from .review_queues import _search_condition
    matching: set[int] = set()
    ids = [r.id for r in rows]
    for start in range(0, len(ids), 500):
        matching.update(session.scalars(
            select(m.FinancialTransaction.id)
            .outerjoin(m.BankTransactionExplanation,
                       m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
            .where(m.FinancialTransaction.id.in_(ids[start:start + 500]), _search_condition(text))))
    return [r for r in rows if r.id in matching]


def selected_within_search(session: Session, selected_ids: list[int] | None, *, date_from: date | None,
                           date_to: date | None, cls: str | None, search: str | None) -> list[int]:
    """BANK_AI_RULES_025 — with a movements' search active, the selected
    movements a Preview or an application may operate on are ONLY those within
    the list's perimeter: the period, "Classificazione" and the search, as the
    page shows them. Without a search, the selection is returned unchanged.
    Raises when no selected movement is within the perimeter. Read only."""
    selected = sorted(set(selected_ids or []))
    if not (search or "").strip():
        return selected
    rows = period_rows(session, date_from=date_from, date_to=date_to)
    rows = classification_filter(rows, cls if cls in CLASSIFICATION_FILTERS else "all")
    perimeter = {r.id for r in search_filter(session, rows, search)}
    kept = [i for i in selected if i in perimeter]
    if not kept:
        raise AiRuleError("None of the selected movements is among the results of the current search, period and "
                          "Classificazione: select them in the list, then try again.")
    return kept


def ids_matching_classification(session: Session, ids: list[int], key: str) -> list[int]:
    """BANK_AI_RULES_020 — of these movement ids (any period), those that
    exist and satisfy the "Classificazione" filter, on the CURRENT WHO / WHY.
    Read only."""
    found = []
    wanted = sorted({int(i) for i in ids if int(i) > 0})
    for start in range(0, len(wanted), 500):
        chunk = wanted[start:start + 500]
        rows = session.execute(
            select(m.FinancialTransaction.id, m.BankTransactionExplanation.occurrence_id,
                   m.BankTransactionExplanation.transaction_reason_id)
            .outerjoin(m.BankTransactionExplanation,
                       m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
            .where(m.FinancialTransaction.id.in_(chunk)))
        for txn_id, who_id, why_id in rows:
            if key == "no_who" and who_id is not None:
                continue
            if key == "no_why" and (who_id is None or why_id is not None):
                continue
            found.append(txn_id)
    return sorted(found)


def period_rows(session: Session, *, date_from: date | None, date_to: date | None) -> list[Row]:
    """Every in-scope movement of the period, classified or not, by date."""
    if date_from and date_to and date_from > date_to:
        raise AiRuleError("The period start is after its end.")
    query = _scope_query()
    if date_from:
        query = query.where(m.FinancialTransaction.posting_date >= date_from)
    if date_to:
        query = query.where(m.FinancialTransaction.posting_date <= date_to)
    transactions = list(session.scalars(query.order_by(m.FinancialTransaction.posting_date,
                                                       m.FinancialTransaction.id)))
    return _rows(session, transactions)


SCOPE_PERIOD, SCOPE_ALL, SCOPE_SELECTED = "PERIOD", "ALL", "SELECTED"
SCOPES = (SCOPE_PERIOD, SCOPE_ALL, SCOPE_SELECTED)


def scope_rows(session: Session, *, scope: str, date_from: date | None, date_to: date | None,
               selected_ids: list[int] | None = None) -> list[Row]:
    """The movements of a scope (BANK_AI_RULES_006): the displayed PERIOD, ALL
    the in-scope movements of the database, or exactly the SELECTED ones —
    never more, whatever period is displayed."""
    if scope == SCOPE_PERIOD:
        return period_rows(session, date_from=date_from, date_to=date_to)
    query = _scope_query()
    if scope == SCOPE_SELECTED:
        ids = sorted(set(selected_ids or []))
        if not ids:
            raise AiRuleError("Select at least one movement for “Only the selected transactions”.")
        transactions = []
        for start in range(0, len(ids), 500):
            transactions += list(session.scalars(query.where(m.FinancialTransaction.id.in_(ids[start:start + 500]))))
        transactions.sort(key=lambda t: (t.posting_date or date.min, t.id))
        return _rows(session, transactions)
    if scope == SCOPE_ALL:
        return _rows(session, list(session.scalars(query.order_by(m.FinancialTransaction.posting_date,
                                                                  m.FinancialTransaction.id))))
    raise AiRuleError("Unknown scope.")


# BANK_AI_RULES_013 — "Solo movimenti non ancora sistemati da regole AI".
ONLY_UNSETTLED_LABEL = "Only transactions not yet classified by AI rules"
# BANK_AI_RULES_018 — "Solo WHO": a Preview / application that executes ONLY
# the WHO part of the rules (WHY, the WHO's default WHY and For Whom are left
# as they are; conflicts are about the WHO only). The rule itself is not
# changed: its other instructions stay for a later phase.
WHO_ONLY_LABEL = "Apply only WHO"


def who_only_exec(ex: "Exec") -> "Exec":
    """The rule's result reduced to its WHO part: WHY, default WHY, WHY to
    verify and For Whom dropped; the WHO, its options and status kept."""
    if ex.outcome != "MATCH":
        return ex
    return Exec(ex.outcome, who=ex.who, who_verify=ex.who_verify, branch=ex.branch, note=ex.note,
                status=ex.status, only_if_who_differs=ex.only_if_who_differs, replace_existing=ex.replace_existing)


def ai_settled(session: Session) -> dict[int, int]:
    """{movement id: AI rule id} of the movements SETTLED BY AN AI RULE: their
    CURRENT decision is one an AI rule application actually wrote — an
    application item UPDATED with that decision (`explanation_id`) — and it
    names both a WHO and a WHY (a WHY left to complete is not settled). Recorded
    provenance only, never deduced from a WHO / WHY being present: a preview,
    a movement not matched, an UNCHANGED or an ERROR item writes no decision,
    and a decision changed afterwards (by a person, a Standard, another
    rule) is no longer the AI rule's."""
    rows = session.execute(
        select(m.FinancialTransaction.id, m.BankAiRuleApplication.rule_id)
        .join(m.BankAiRuleApplicationItem,
              m.BankAiRuleApplicationItem.explanation_id == m.FinancialTransaction.explanation_id)
        .join(m.BankAiRuleApplication, m.BankAiRuleApplication.id == m.BankAiRuleApplicationItem.application_id)
        .join(m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
        .where(m.BankAiRuleApplicationItem.outcome == "UPDATED",
               # BANK_AI_RULES_015 — COMPLETELY settled: the decision names a WHO and a WHY. A WHO left with its
               # WHY to complete (no default WHY) is not settled: the rule may complete it later.
               m.BankTransactionExplanation.occurrence_id.is_not(None),
               m.BankTransactionExplanation.transaction_reason_id.is_not(None)))
    return {txn_id: rule_id for txn_id, rule_id in rows}


def without_ai_settled(session: Session, rows: list["Row"], only_unsettled: bool) -> tuple[list["Row"], dict[str, int]]:
    """(rows to consider, {AI rule id: movements excluded}) — with the option
    on, the movements already settled by an AI rule are left out."""
    if not only_unsettled:
        return rows, {}
    settled = ai_settled(session)
    kept, excluded = [], {}
    for row in rows:
        rule_id = settled.get(row.id)
        if rule_id is None:
            kept.append(row)
        else:
            excluded[str(rule_id)] = excluded.get(str(rule_id), 0) + 1
    return kept, excluded


def scope_key(*, rule_text: str, scope: str, selected_ids: list[int] | None, create_missing_who: bool,
              date_from: date | None = None, date_to: date | None = None, override_protected: bool = False,
              only_unsettled: bool = False, who_only: bool = False) -> str:
    """Identifies what a preview was made for: an application uses only a
    preview of the same text, scope, selection and options. (The override
    option is part of the key only when on, so earlier keys are unchanged.)"""
    ids = ",".join(map(str, sorted(set(selected_ids or [])))) if scope == SCOPE_SELECTED else ""
    period = f"{date_from}..{date_to}" if scope == SCOPE_PERIOD else ""
    override = "|override_protected" if override_protected else ""
    override += "|only_unsettled" if only_unsettled else ""
    override += "|who_only" if who_only else ""
    return hashlib.sha256(f"{rule_text.strip()}|{scope}|{ids}|{period}|{int(bool(create_missing_who))}{override}"
                          .encode("utf-8")).hexdigest()


_SCOPE_WORDS = {SCOPE_ALL: "“All existing transactions”", SCOPE_SELECTED: "“Only the selected transactions”",
                SCOPE_PERIOD: "the period shown"}


def preview_problem(preview, *, rule_text: str, scope: str, selected_ids: list[int] | None,
                    create_missing_who: bool, override_protected: bool = False,
                    only_unsettled: bool = False, who_only: bool = False) -> str | None:
    """Why `preview` cannot authorize applying this text, scope, selection
    and option — the precise reason — or None when it can."""
    if preview is None:
        return "there is no Preview of this rule: press Preview, check it, then apply."
    if preview.status != "COMPLETED":
        return (f"Preview #{preview.id} did not complete ({preview.status})"
                + (f": {shown_message(preview.error_message)}" if preview.error_message else "."))
    if (preview.rule_text or "").strip() != (rule_text or "").strip():
        return f"the rule text is not the one of Preview #{preview.id}: it changed after that Preview."
    if preview.scope != scope:
        return (f"Preview #{preview.id} was made for {_SCOPE_WORDS.get(preview.scope, preview.scope)}, "
                f"the rule is now applied to {_SCOPE_WORDS.get(scope, scope)}.")
    if bool(preview.create_missing_who) != bool(create_missing_who):
        return (f"“Create missing WHO” is {'on' if create_missing_who else 'off'} now, it was "
                f"{'on' if preview.create_missing_who else 'off'} in Preview #{preview.id}.")
    if bool(preview.override_protected) != bool(override_protected):
        return (f"“{OVERRIDE_LABEL}” is {'on' if override_protected else 'off'} now, it was "
                f"{'on' if preview.override_protected else 'off'} in Preview #{preview.id}.")
    if bool(preview.only_unsettled) != bool(only_unsettled):
        return (f"“{ONLY_UNSETTLED_LABEL}” is {'on' if only_unsettled else 'off'} now, it was "
                f"{'on' if preview.only_unsettled else 'off'} in Preview #{preview.id}.")
    if bool(preview.who_only) != bool(who_only):
        return (f"“{WHO_ONLY_LABEL}” is {'on' if who_only else 'off'} now, it was "
                f"{'on' if preview.who_only else 'off'} in Preview #{preview.id}.")
    if preview.scope_key != scope_key(rule_text=rule_text, scope=scope, selected_ids=selected_ids,
                                      create_missing_who=create_missing_who, override_protected=override_protected,
                                      only_unsettled=only_unsettled, who_only=who_only):
        if scope == SCOPE_SELECTED:
            return f"the selected movements are not those of Preview #{preview.id}."
        return f"Preview #{preview.id} was made for another text, scope or option."
    return None


def row_for(session: Session, transaction_id: int | None) -> Row | None:
    if not transaction_id:
        return None
    txn = session.get(m.FinancialTransaction, transaction_id)
    return _rows(session, [txn])[0] if txn is not None else None


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def save_draft(session: Session, *, draft_id: int | None, rule_text: str | None,
               origin_transaction_id: int | None, account_id: int | None,
               create_missing_who: bool = False, ai_rule_id: int | None = None,
               override_protected: bool = False, only_unsettled: bool = True,
               user_title: str | None = None) -> "m.BankAiRuleDraft":
    rule_text = (rule_text or "").strip()
    if not rule_text:
        raise AiRuleError("Write the rule before saving it as a draft.")
    draft = session.get(m.BankAiRuleDraft, draft_id) if draft_id else None
    if draft_id and draft is None:
        raise AiRuleError("This draft no longer exists; reload the page.")
    if draft is None:
        origin = session.get(m.FinancialTransaction, origin_transaction_id) if origin_transaction_id else None
        if origin is None:
            raise AiRuleError("The origin transaction could not be found; reload the page.")
        draft = m.BankAiRuleDraft(
            rule_text=rule_text, status="DRAFT", origin_transaction_id=origin.id,
            origin_posting_date=origin.posting_date, origin_description=origin.description_original,
            origin_amount_minor=origin.amount_minor, created_by_account_id=account_id,
            ai_rule_id=ai_rule_id or None)
        session.add(draft)
    else:
        draft.rule_text = rule_text
    draft.user_title = " ".join((user_title or "").split())[:200] or None    # BANK_AI_RULES_022
    draft.create_missing_who = bool(create_missing_who)
    draft.override_protected = bool(override_protected)
    draft.only_unsettled = bool(only_unsettled)
    session.flush()
    return draft


def catalog_names(session: Session) -> tuple[list[str], list[str]]:
    """(active WHO canonical names, available WHY names), alphabetical — the
    two pick lists of the AI Rule window (BANK_AI_RULES_004). Read only: a
    pick only writes text into the rule."""
    whos = sorted(session.scalars(select(m.BankOccurrence.canonical_name)
                                  .where(m.BankOccurrence.status == "ACTIVE")), key=str.casefold)
    whys = sorted(session.scalars(select(m.BankTransactionReason.name)
                                  .where(m.BankTransactionReason.status == "ACTIVE")), key=str.casefold)
    return whos, whys


def drafts(session: Session) -> list["m.BankAiRuleDraft"]:
    return list(session.scalars(select(m.BankAiRuleDraft).order_by(m.BankAiRuleDraft.updated_at.desc(),
                                                                   m.BankAiRuleDraft.id.desc())))


# ---------------------------------------------------------------------------
# Preview — catalog and the movement-by-movement AI prompt
# ---------------------------------------------------------------------------

def _catalog(session: Session):
    whys = [(r.id, r.code, r.name, r.description) for r in session.scalars(
        select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")
        .order_by(m.BankTransactionReason.name))]
    codes = {rid: code for rid, code, _, _ in whys}
    possible: dict[int, list[str]] = {}
    for occurrence_id, reason_id in session.execute(
            select(m.BankOccurrenceReasonAssociation.occurrence_id,
                   m.BankOccurrenceReasonAssociation.transaction_reason_id)
            .where(m.BankOccurrenceReasonAssociation.active.is_(True))):
        if reason_id in codes:
            possible.setdefault(occurrence_id, []).append(codes[reason_id])
    whos = [(o.id, o.canonical_name, sorted(possible.get(o.id, []))) for o in session.scalars(
        select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE").order_by(m.BankOccurrence.canonical_name))]
    return whos, whys


def _line(ref: str, row: Row) -> str:
    txn = row.txn
    return (f"{ref} | {txn.posting_date} | {txn.amount_minor / 100:.2f} {row.currency or ''}".rstrip()
            + f" ({'money out' if txn.amount_minor < 0 else 'money in'}) | Source: {row.source_label} | "
            f"Current WHO: {row.current_who or '-'} | Current WHY: {row.current_why or '-'} | "
            f"Description: {mask_numbers(txn.description_original)}")


def _context(rule_text: str, origin_line: str, instructions: str | None, whos, whys) -> str:
    who_lines = "\n".join(f"- {name}" + (f"  [possible WHY: {', '.join(codes)}]" if codes else "")
                          for _, name, codes in whos)
    why_lines = "\n".join(f"- {code} | {name}" + (f" | {description}" if description and description != name else "")
                          for _, code, name, description in whys)
    general = f"\nGENERAL AI INSTRUCTIONS OF THE OPERATOR:\n{instructions}\n" if instructions else ""
    return f"""You evaluate ONE classification rule, written in natural language by an operator of RF-One Bank
Reconciliation, against a list of bank and card movements.

THE RULE:
{rule_text}

THE EXAMPLE MOVEMENT the operator wrote the rule from (use it to understand what the rule means):
{origin_line}
{general}
For each movement of the list decide:
- MATCH: the rule clearly applies to it;
- DOUBT: it might apply but the data is not enough to be sure;
- otherwise leave it OUT of the answer.
For every MATCH or DOUBT give a short "reason" in Italian (at most 20 words). Give a WHO and/or a WHY ONLY when
the rule itself says or clearly implies them; otherwise null. A WHO is written in UPPER CASE, exactly as in the
catalog when it is there; a WHY is given by its catalog code when it is there. Never invent facts.

WHO CATALOG:
{who_lines or '- (empty)'}

WHY CATALOG (code | name | description):
{why_lines or '- (empty)'}
"""


def _prompt(context: str, lines: list[str]) -> str:
    movements = "\n".join(lines)
    return f"""{context}
MOVEMENTS (ref | date | amount | Source | current WHO | current WHY | description; long numbers are masked):
{movements}

Answer ONLY with JSON, no markdown, exactly this shape, listing only MATCH and DOUBT movements:
{{"items": [{{"ref": "T1", "verdict": "MATCH" or "DOUBT", "reason": "...",
  "who": "UPPER CASE NAME" or null, "why_code": "CATALOG_CODE" or null, "why_name": "WHY name" or null}}]}}
If no movement matches, answer {{"items": []}}."""


# ---------------------------------------------------------------------------
# AI calls: throttling handled with progressive waits, limited retries and a
# concurrency that shrinks when the provider pushes back (BANK_AI_RULES_005)
# ---------------------------------------------------------------------------

MAX_RETRIES = 5            # per call, on throttling only
BACKOFF_BASE = 2.0         # seconds: 2, 4, 8, 16, 32 (+ up to 1 s jitter)
_sleep = time.sleep        # replaced by tests


def is_throttling(error: Exception) -> bool:
    text = str(error).lower()
    return ("throttl" in text or "too many requests" in text or "rate exceeded" in text
            or "429" in text or "slow down" in text)


class _Limiter:
    """At most `allowed` AI calls at once; every throttling answer lowers
    `allowed` by one (never below one) for the rest of the preview."""

    def __init__(self, allowed: int):
        self.allowed = allowed
        self.active = 0
        self.throttled = 0
        self.condition = threading.Condition()

    def __enter__(self):
        with self.condition:
            while self.active >= self.allowed:
                self.condition.wait()
            self.active += 1
        return self

    def __exit__(self, *exc):
        with self.condition:
            self.active -= 1
            self.condition.notify_all()

    def slow_down(self):
        with self.condition:
            self.throttled += 1
            self.allowed = max(1, self.allowed - 1)


class _Calls:
    def __init__(self):
        self.count = 0
        self.lock = threading.Lock()

    def add(self):
        with self.lock:
            self.count += 1


def _call(generate, prompt: str, limiter: _Limiter, calls: _Calls) -> dict:
    """One AI call; on throttling, wait progressively and retry (at most
    MAX_RETRIES times). Any other failure — or throttling that persists — is
    raised, never swallowed."""
    for attempt in range(MAX_RETRIES + 1):
        with limiter:
            calls.add()
            try:
                return generate(prompt)
            except ai_client.AIProviderUnavailable as exc:
                if not is_throttling(exc) or attempt == MAX_RETRIES:
                    raise
                limiter.slow_down()
        _sleep(BACKOFF_BASE * (2 ** attempt) + random.random())
    raise AssertionError("unreachable")


def _ask(generate, context: str, lines: list[str], limiter: _Limiter, calls: _Calls) -> list[dict]:
    """One batch -> its items. An unreadable answer splits the batch in two
    (down to MIN_BATCH); any other failure is raised."""
    try:
        answer = _call(generate, _prompt(context, lines), limiter, calls)
        items = answer.get("items") if isinstance(answer, dict) else None
        if not isinstance(items, list):
            raise ai_client.AIProviderUnavailable("unparsable response: the AI answer has no 'items' list")
        return [item for item in items if isinstance(item, dict)]
    except ai_client.AIProviderUnavailable as exc:
        unreadable = "unparsable" in str(exc) or "Expecting" in str(exc) or "JSON" in str(exc)
        if unreadable and len(lines) > MIN_BATCH:
            half = len(lines) // 2
            return (_ask(generate, context, lines[:half], limiter, calls)
                    + _ask(generate, context, lines[half:], limiter, calls))
        raise


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# WHO of a proposal: existing, new, or not creatable — the WHO service decides
# ---------------------------------------------------------------------------

def normalize_who(name: str | None) -> str | None:
    """Spaces collapsed, upper case: the form a WHO name is stored and compared in."""
    clean = " ".join(str(name or "").split()).upper()
    return clean[:255] or None


# BANK_AI_RULES_016 — an extracted WHO that is not a WHO yet may be an
# existing WHO followed by abbreviations, suffixes or codes.
WHO_DOUBT = "Doubt about the WHO"
MIN_SUBJECT_CHARS = 5          # a name whose last word continues glued into a longer word
MIN_WHOLE_WORD_CHARS = 3       # a name matched by whole words, followed only by suffixes or codes
REUSED_EXACT, REUSED_IDENTITY, REUSED_SUBJECT = "EXACT", "IDENTITY", "SUBJECT"


def _words(name: str) -> list[str]:
    return re.findall(r"[0-9A-Z]+", (name or "").upper())


# Words that may follow a WHO's name without naming another subject: legal
# forms and payment words. Any word with a digit (a code) or of at most 3
# letters (PAY, CO, SA…) is a suffix too.
SUBJECT_SUFFIXES = {"LLC", "INC", "CORP", "CORPORATION", "LTD", "LIMITED", "COMPANY", "GMBH", "SPA", "SRL", "SARL",
                    "PLLC", "LLP", "PAYMENT", "PAYMENTS"}


def _is_suffix(word: str) -> bool:
    return any(c.isdigit() for c in word) or len(word) <= 3 or word in SUBJECT_SUFFIXES


def same_subject(existing: str, extracted: str) -> bool:
    """True when the existing WHO's name is the START of the extracted text,
    word by word — every word equal, except that its LAST word may continue
    into a longer word (an abbreviation glued to it, "KATOM" in
    "KATOMRESTAU") — and every following word is only a suffix or a code
    (`_is_suffix`). A name too short is too vague: at least
    MIN_SUBJECT_CHARS letters or digits when its last word continues glued,
    MIN_WHOLE_WORD_CHARS when it is matched by whole words. Further
    descriptive words name another subject: "KATOM" is "KATOMRESTAU PAY",
    "TEMU" is "TEMU 123456", "ACME SUPPLY" is "ACME SUPPLY 4471 XZ"; but
    "GIOVANNA" is NOT "GIOVANNA WINE REP", "TEMU" is not "TEMUCO SA" (glued,
    too short), "ACME SUPPLY" is not "ACME SERVICES"."""
    have, got = _words(existing), _words(extracted)
    if not have or len(have) > len(got) or have == got:
        return False
    last = got[len(have) - 1]
    if have[:-1] != got[:len(have) - 1] or not last.startswith(have[-1]):
        return False
    minimum = MIN_SUBJECT_CHARS if last != have[-1] else MIN_WHOLE_WORD_CHARS
    return len("".join(have)) >= minimum and all(_is_suffix(word) for word in got[len(have):])


class _WhoStatus:
    """`who_rules.check_new_who`, read-only and once per name: the existing
    ACTIVE WHO the name already is (case and spaces aside, or its registry
    identity), a new name, or why it cannot become a WHO.

    BANK_AI_RULES_016 — when the name is no WHO yet, an existing ACTIVE WHO
    that identifies the SAME SUBJECT (`same_subject`: its name followed by
    abbreviations, suffixes or codes) is reused; two or more such WHO are a
    DOUBT — none is chosen. `how[name]` says how the WHO was found."""

    def __init__(self, session: Session):
        self.session = session
        self.cache: dict[str, tuple[int | None, str | None, str | None]] = {}
        self.how: dict[str, str] = {}
        self._active: list[tuple[int, str]] | None = None

    def _subjects(self, name: str) -> list[tuple[int, str]]:
        if self._active is None:
            self._active = [(o.id, o.canonical_name) for o in self.session.scalars(
                select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))]
        return [(i, n) for i, n in self._active if same_subject(n, name)]

    def __call__(self, name: str | None) -> tuple[int | None, str | None, str | None]:
        from . import who_rules
        name = normalize_who(name)
        if name is None:
            return None, None, None
        if name not in self.cache:
            try:
                existing, clean = who_rules.check_new_who(self.session, name)
                if existing is not None:
                    self.cache[name] = (existing.id, existing.canonical_name, None)
                    self.how[name] = (REUSED_EXACT if normalize_who(existing.canonical_name) == name
                                      else REUSED_IDENTITY)
                else:
                    subjects = self._subjects(name)
                    if len(subjects) == 1:
                        self.cache[name] = (subjects[0][0], subjects[0][1], None)
                        self.how[name] = REUSED_SUBJECT
                    elif subjects:
                        names = ", ".join(sorted(n for _i, n in subjects))
                        self.cache[name] = (None, name, f"{WHO_DOUBT}: “{name}” can be one of several existing WHO "
                                                        f"({names}); none is chosen automatically")
                    else:
                        self.cache[name] = (None, normalize_who(clean), None)
            except ValueError as exc:
                self.cache[name] = (None, name, str(exc))
        return self.cache[name]


_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = dict.fromkeys(map(ord, "“”„«»"), '"')


def _norm(text: str | None) -> str:
    """For comparing texts: every dash alike, every double quote alike,
    spaces collapsed, case ignored."""
    return " ".join(str(text or "").translate(_DASHES).translate(_QUOTES).split()).casefold()


class _WhyCatalog:
    """WHY resolution by RF-One: code, or name with case, spaces and dash
    style aside."""

    def __init__(self, whys):
        self.by_code = {code.upper(): rid for rid, code, _, _ in whys}
        self.by_name = {_norm(name): rid for rid, _, name, _ in whys}
        self.name_of = {rid: name for rid, _, name, _ in whys}
        self.code_of = {rid: code for rid, code, _, _ in whys}

    def resolve(self, value: str | None) -> int | None:
        value = str(value or "").strip()
        if not value:
            return None
        return self.by_code.get(value.upper()) or self.by_name.get(_norm(value))


class EntityCatalog:
    """For Whom resolution by RF-One (BANK_AI_RULES_010): an ACTIVE reporting
    entity by code or by name, case, spaces and dash style aside. An entity is
    never created. `name_of` also names inactive entities, to show a current
    For Whom."""

    def __init__(self, session: Session):
        entities = list(session.scalars(select(m.ReportingEntity)))
        active = [e for e in entities if e.status == "ACTIVE"]
        self.by_code = {_norm(e.code): e.id for e in active}
        self.by_name = {_norm(e.name): e.id for e in active}
        self.name_of = {e.id: e.name for e in entities}
        self.code_of = {e.id: e.code for e in entities}

    def resolve(self, value: str | None) -> int | None:
        key = _norm(value)
        if not key:
            return None
        return self.by_code.get(key) or self.by_name.get(key)


def _resolve(item: dict, who_status: _WhoStatus, why_catalog: _WhyCatalog) -> dict:
    """WHO/WHY of one item matched to the catalogs by RF-One, never by the AI.
    A name that already IS another WHO by registry identity (e.g. the name
    of a WHO merged into it) proposes that WHO, and says so."""
    extracted = normalize_who(item.get("who"))
    who_id, who_name, who_error = who_status(extracted)
    note = None
    if who_id is not None and extracted and normalize_who(who_name) != extracted:
        if who_status.how.get(extracted) == REUSED_SUBJECT:
            note = (f"Extracted text “{extracted}” → existing WHO {who_name} reused (same subject: "
                    "the WHO's name followed by abbreviations, suffixes or codes).")
        else:
            note = f"“{extracted}” is already the WHO {who_name} (same identity in the WHO list: merged name or alias)."
    why_code = str(item.get("why_code") or "").strip()
    why_name = str(item.get("why_name") or "").strip()[:255] or None
    why_id = why_catalog.resolve(why_code) or why_catalog.resolve(why_name)
    if why_id is None and why_code and not why_name:
        why_name = why_code
    if why_id is not None:
        why_name = why_catalog.name_of[why_id]
    return dict(proposed_who_name=who_name, proposed_who_id=who_id, extracted_who_name=extracted,
                proposed_who_is_new=bool(who_name and who_id is None and not who_error),
                proposed_why_name=why_name, proposed_why_id=why_id, proposed_why_is_new=bool(why_name and why_id is None),
                who_error=who_error, who_note=note)


# ---------------------------------------------------------------------------
# Interpretation: the AI reads the rule once into a verifiable structure;
# RF-One validates it and executes it by code (BANK_AI_RULES_003/005/007)
# ---------------------------------------------------------------------------

# structured-v2 (BANK_AI_RULES_007): "Personal" is the Source's Personal
# classification in Bank (three-valued), never "owner is a Person"; rules may
# have branches (if / otherwise). Interpretations of v1 are never reused.
# structured-v3 (BANK_AI_RULES_008): extraction options, the WHO's default
# WHY, the "Da confermare" status, "only if the WHO differs", replacing values
# decided by other rules, and a mandatory COVERAGE of every instruction of the
# rule — an instruction that cannot be represented blocks the rule.
# structured-v4 (BANK_AI_RULES_010): the For Whom assignment ("for_whom": a
# fixed entity, or the entity named right after a text such as "IND NAME:"),
# and For Whom protection by provenance instead of a blanket protection of
# every movement with a For Whom. A VALID structured-v3 interpretation stays
# reusable (it represented its whole rule, with no For Whom); a BLOCKED one is
# not — its rule may be representable now, so it is interpreted again.
# structured-v5 (BANK_AI_RULES_011): the condition "the description ends with a
# block of digits" and the WHO extraction "after A, up to that final number".
# The per-rule option "override_protected" is a rule option (like "Crea WHO
# mancanti"), not an element of the structure.
# structured-v6 (BANK_AI_RULES_015): the WHO "to_end" — after one of several
# alternative start texts, optionally after the first following marker, up to
# the END of the description.
# structured-v7 (BANK_AI_RULES_021): WHO extraction options "strip_digits"
# (digits 0-9 removed from the extracted text) and "require_letter" (no letter
# left → the WHO is "Da verificare"); "to_end" option "after_adjacent" (only
# spaces between the start text and the marker); conditions "starts_with_word"
# / "not_starts_with_word" (the text followed by a space or the end); branches
# with no "otherwise": no branch holding = the rule does not apply.
INTERPRETATION_VERSION = "structured-v7"
REUSABLE_PREVIOUS_VERSIONS = ("structured-v6", "structured-v5", "structured-v4", "structured-v3")
SPEC_VERSION = 7
USABLE_SPEC_VERSIONS = (2, 3, 4, 5, 6, 7)
MAX_START_TEXTS = 5
# WHO assignments that name a WHO (fixed or extracted from the description).
WHO_EXTRACTIONS = ("between", "before_final_number", "to_end")
WHO_NAMING = ("fixed",) + WHO_EXTRACTIONS
# "ends_with_number": once trimmed, the description ends with a space and a
# block made ONLY of digits ("… Cleaning 30541248046"; never "JPM99cxov680").
FINAL_NUMBER_RE = re.compile(r"\s(\d+)$")
OVERRIDE_LABEL = "Allow this rule to replace manual or confirmed WHO and WHY"
# The SAME option as the AI interpretation prompt names it. Kept with its
# former wording on purpose (BANK_OLD_RULES_REMOVAL_001): the prompt text is
# changed only after the Product Owner approves the before/after comparison
# (07 Tasks/Reports/BANK_OLD_RULES_REMOVAL_001/AI_PROMPT_BEFORE_AFTER.md).
PROMPT_OVERRIDE_LABEL = "Sostituisci anche WHO/WHY manuali, Standard o confermati"
MAX_FOR_WHOM_NAMES = 10
PROTECTIONS_TEXT = (
    "PROTECTED by RF-One, never changed: manual decisions, own-account movements (no WHO), "
    "a For Whom chosen by a person, a movement whose For Whom is accounting-complete (confirmed); "
    "a For Whom whose origin is uncertain is kept, with the reason. A For Whom written by a rule is automatic: "
    "updated like a WHO / WHY")
TO_VERIFY = "To verify"
# "Da confermare" (BANK_AI_RULES_008): the decision is NOT in a resolved
# state (`recognition.RESOLVED_DECISION_STATUSES`), so it blocks the export
# and shows as unresolved; with no human allocation, the derived
# reconciliation status (`reconciliation_status`) is "Needs review".
TO_CONFIRM = "Da confermare"
# How the status is named on screen (the value above stays as it is in the rule's interpretation).
TO_CONFIRM_LABEL = "To confirm"
TO_CONFIRM_DECISION_STATUS = "NEEDS_HUMAN_REVIEW"
START_AT = ("beginning", "anywhere")
END_CASE = ("as_written", "ignore")
IF_NO_DEFAULT = ("clear", "unchanged")
MAX_COVERAGE = 30
TEXT_FIELDS = {
    "description": ("contains", "not_contains", "starts_with", "ends_with_number", "starts_with_word",
                    "not_starts_with_word"),
    "source_name": ("contains", "not_contains"),
    "source_owner_name": ("contains", "not_contains"),
}
ENUM_FIELDS = {
    "source_type": ("card", "bank account"),
    "direction": ("money out", "money in"),
    "source_class": ("Personal", "not Personal", "missing"),
}
ENUM_OPS = ("is", "is_not")
VALUELESS_OPS = ("ends_with_number",)
MAX_CONDITIONS = 8
MAX_BRANCHES = 6

# What "Personal" means, said once wherever it is used.
SOURCE_CLASS_BASIS = (
    "Personal / not Personal = the Source's owner as recorded in Bank (Source configuration; for a card, the owner "
    "of the account it settles to on the movement's date — card settlement configuration): a PERSONAL reporting "
    "entity = Personal; a company = not Personal; no owner recorded, or a card with no settlement account on that "
    "date = classification missing → Da verificare (never \"not Personal\")."
)


# ---------------------------------------------------------------------------
# AI mode (BANK_AI_RULES_008). PROVIDER: the RF-One provider abstraction
# (`ai_client`, RFONE_AI_PROVIDER). SESSION: the Claude Code session in VS
# Code interprets the rules (Infrastructure/Bank Local Environment,
# SESSION_INTERPRETATION.md) — Bank NEVER calls a provider: a saved
# interpretation runs, a missing one makes the preview wait for the session.
# ---------------------------------------------------------------------------

AI_MODE_SESSION, AI_MODE_PROVIDER = "SESSION", "PROVIDER"
SESSION_PROVIDER = "CLAUDE_CODE_SESSION"
SESSION_WAIT_MARKER = "In attesa della sessione Claude Code"


class SessionInterpretationNeeded(ai_client.AIProviderUnavailable):
    """SESSION mode: this rule text has no saved interpretation yet."""


def ai_mode() -> str:
    mode = (os.environ.get("RFONE_BANK_AI_MODE") or AI_MODE_PROVIDER).strip().upper()
    return mode if mode in (AI_MODE_SESSION, AI_MODE_PROVIDER) else AI_MODE_PROVIDER


def _session_generate(prompt: str) -> dict:
    raise SessionInterpretationNeeded("no interpretation of this rule is saved yet")


def default_generate() -> Callable[[str], dict]:
    """PROVIDER mode: the RF-One provider abstraction. SESSION mode: the local
    Claude Code CLI when the environment enables it (BANK_AI_RULES_012 — the
    preview interprets the rule in the same click), otherwise wait for the
    session."""
    if ai_mode() != AI_MODE_SESSION:
        return ai_client.generate_json
    return claude_code_cli.generate_json if claude_code_cli.available() else _session_generate


def active_ai_description() -> tuple[str, str | None]:
    """(provider, model) the page shows: in SESSION mode, never a provider."""
    if ai_mode() == AI_MODE_SESSION:
        if claude_code_cli.available():
            return claude_code_cli.PROVIDER, (f"{claude_code_cli.model()} — Claude Code CLI on this PC (same login "
                                              "as the VS Code session), automatic; no AWS provider")
        return SESSION_PROVIDER, "Claude Code session in VS Code — no call to an AI provider"
    return ai_client.active_provider_description()


def session_wait_message(preview_id: int | str) -> str:
    """The STORED wait message: it begins with SESSION_WAIT_MARKER, by which the
    session tooling finds the previews waiting for it (bank_local_env
    session_ai). Never shown as it is: see `shown_message`."""
    return (f"{SESSION_WAIT_MARKER} (Preview #{preview_id}): questa regola non ha ancora un'interpretazione. "
            "Nella sessione Claude Code di VS Code scrivi «Interpreta le AI Rules in attesa». Quando la sessione "
            "conferma, premi di nuovo Preview: la regola sarà eseguita dal codice, senza chiamate AI. "
            "Nessun provider AI (AWS) è stato chiamato.")


SESSION_WAIT_SHOWN = "Waiting for the Claude Code session"
_SESSION_WAIT_PREVIEW = re.compile(r"\s*\(Preview #([^)]*)\)")


def shown_message(message: str | None) -> str | None:
    """A stored preview message as the page shows it. The session wait keeps its
    stored marker (what the session tooling looks for) and is shown in the
    interface language; every other message is shown as it is."""
    if not message or not message.startswith(SESSION_WAIT_MARKER):
        return message
    found = _SESSION_WAIT_PREVIEW.match(message[len(SESSION_WAIT_MARKER):])
    return (f"{SESSION_WAIT_SHOWN} (Preview #{found.group(1) if found else '?'}): this rule has no interpretation "
            "yet. In the Claude Code session in VS Code, write “Interpreta le AI Rules in attesa”. When the session "
            "confirms, press Preview again: the rule will be executed by the code, with no AI call. No AI provider "
            "(AWS) was called.")


def interpreter_capabilities() -> str:
    """The conditions, assignments and structure the interpreter accepts —
    the ONE description of them, given to the AI both to interpret a rule
    (`_interpretation_prompt`) and to rewrite one (BANK_AI_RULES_026,
    `rewrite_prompt`), and kept in step with `validate_interpretation`."""
    return f"""Conditions (a list: all must hold):
- {{"field": "description", "op": "contains" | "not_contains" | "starts_with", "value": "TEXT"}}  (case ignored;
     starts_with: the description's leading spaces ignored)
- {{"field": "description", "op": "starts_with_word" | "not_starts_with_word", "value": "TEXT"}}  the description
     (leading spaces and case ignored) starts — or does not start — with TEXT followed by a space or by its end (so
     "ORIG CO NAME:PAYPAL" is not "ORIG CO NAME:PAYPALSI…")
- {{"field": "description", "op": "ends_with_number"}}  the description, trailing spaces ignored, ends with a space
     followed by a block made ONLY of digits (e.g. "… Cleaning 30541248046"); a final code mixing letters and digits
     (e.g. "JPM99cxov680") is NOT a final number
- {{"field": "source_name", "op": "contains" | "not_contains", "value": "TEXT"}}   the Source (card/account) name
- {{"field": "source_owner_name", "op": "contains" | "not_contains", "value": "TEXT"}}  the Source owner's name
- {{"field": "source_class", "op": "is" | "is_not", "value": "Personal" | "not Personal" | "missing"}}
     the Source's Personal classification in Bank. "Personal Source" / "Source Personal" = is "Personal";
     "non Personal" = is "not Personal"; "classification missing or uncertain" = is "missing".
     A "Personal card" ("carta Personal") = TWO conditions: source_type is "card" AND source_class is "Personal".
- {{"field": "source_type", "op": "is" | "is_not", "value": "card" | "bank account"}}
- {{"field": "direction", "op": "is" | "is_not", "value": "money out" | "money in"}}
Assignments (null = left unchanged):
- "who": {{"mode": "fixed", "name": "NAME"}}
     or {{"mode": "between", "start": "A", "end": "B", "start_at": "beginning" | "anywhere",
         "end_case": "as_written" | "ignore"}}
        the WHO is the description text after A and before the FIRST following B, spaces trimmed and collapsed,
        upper case; A is matched ignoring case; "start_at": where A must be ("beginning" of the description, or
        "anywhere" in it); "end_case": whether B is matched as written or ignoring case. A or B missing, B not after
        A, or nothing between them: the rule does not change the movement.
     or {{"mode": "before_final_number", "start": "A", "start_at": "beginning" | "anywhere"}}
        the WHO is the text after A and before the description's FINAL NUMBER (the last block made only of digits,
        preceded by a space — see "ends_with_number"), spaces trimmed and collapsed, upper case; other numbers inside
        the text are kept. A missing, no final number or nothing between: the rule does not change the movement.
     or {{"mode": "to_end", "starts": ["A1", "A2", ...], "start_at": "beginning" | "anywhere", "after": "M" | null}}
        the WHO is the text up to the END of the description: after the FIRST occurrence of any of the start
        texts A (alternatives — "A1 oppure A2"; any case), and, when "after" is given, after the FIRST following
        marker M (any case) — e.g. starts ["PAYPAL", "PYPAL"], after "*": "PAYPAL *AIRBNB HMSSZ842DA" →
        "AIRBNB HMSSZ842DA". Nothing is removed (codes and numbers stay); outer spaces trimmed, spaces collapsed,
        upper case. No start text, no marker after it, or nothing after: the rule does not change the movement.
        Alternatives of the start text are expressed by "starts" — do NOT add a "contains" condition for them.
        "after_adjacent": true — only spaces may stand between the start text and the marker (e.g. "PAYPAL *TEMU",
        "PAYPAL   *TEMU", never "PAYPAL INST *X").
   Every WHO extraction ("between", "before_final_number", "to_end") also takes:
        "strip_digits": true — every digit 0-9 is removed from the extracted text (letters and punctuation kept,
        spaces collapsed): "WIX 1259622963" → "WIX";
        "require_letter": true — when the extracted (and cleaned) text has no letter, NO WHO is assigned and the
        WHO is "Da verificare" (the movement is a doubt, never applied).
     or {{"mode": "to_verify"}} (the rule says the WHO is to be verified) or null
- "why": {{"mode": "fixed", "name": "WHY name or code"}}
     or {{"mode": "who_default", "if_missing": "clear" | "unchanged"}}  the default WHY registered on the WHO this
        rule assigns (never deduced); "if_missing": what happens when that WHO has no default WHY — the WHY is
        emptied ("clear": the WHY is left TO BE COMPLETED by a person, never invented; such a movement does not
        count as settled by AI rules) or left as it is ("unchanged"). Needs a "who" assignment. A WHO that is not
        in the WHO list yet is created only with the rule option "Crea WHO mancanti" (otherwise not applied).
     or {{"mode": "to_verify"}} or null
- "for_whom": FOR WHOM — the entity (company / reporting entity) the movement is for. Decided on its own, never
     from the WHO:
     {{"mode": "fixed", "entity": "ENTITY"}}
     or {{"mode": "after_text", "marker": "M", "names": [{{"name": "N1", "entity": "E1"}}, ...]}}  M is searched in
        the description ignoring case (its first occurrence); the spaces right after it are skipped; if the text
        that follows begins with one of the names N — the COMPLETE name, ignoring case, followed by the end of
        the description, spaces or other data, never by more letters or digits — For Whom is its entity E (the
        names are checked in their order). M missing or no name matching: For Whom is left unchanged.
     or null (For Whom left unchanged). ENTITY / E: the entity's code or name exactly as the rule writes it; it
        must be an existing entity (an entity is never created).
- "status": {{"mode": "to_confirm"}} — a movement whose WHO, WHY or For Whom this rule changes is set to
     "Da confermare" (to be confirmed by a person), even if it was confirmed before — or null (status left as it
     is). A movement on which nothing changes keeps its status.
- "only_if_who_differs": true — when the movement already has the WHO this rule assigns (case and spaces aside),
     the rule changes NOTHING on it (no WHO, WHY, For Whom or status change). Otherwise false.
- "replace_existing": true — a different WHO / WHY / For Whom already decided by another rule or an earlier
     automatic decision is replaced. Otherwise false (such a value is a conflict, left as it is). RF-One ALWAYS
     protects, and shows separately: decisions made manually or by a Reconciliation Standard, own-account
     movements (no WHO), a For Whom chosen by a person or by a Standard, a movement whose For Whom is already
     accounting-complete (confirmed), and a For Whom whose origin is uncertain (kept, with the reason). An
     instruction to keep manual / Standard classifications is represented by these protections — say so in the
     coverage. An instruction that EXPLICITLY authorizes replacing WHO / WHY also when manual, Standard or confirmed
     is represented by the rule option "{PROMPT_OVERRIDE_LABEL}" (set by the operator on the rule, off by default,
     recorded) together with "replace_existing" — say so in the coverage; it is not an element of this structure.

Structure:
- "conditions": the conditions for the rule to apply at all;
- "who", "why", "for_whom": what the rule assigns whenever it applies;
- "branches": OPTIONAL alternatives (if / else if / otherwise), checked in order, the first whose conditions all
  hold adds its own "who" / "why" / "for_whom"; a last branch with an empty conditions list is "otherwise".
  With NO "otherwise" and nothing assigned outside the branches, a movement where no branch holds is not matched
  (e.g. "apply only to these two formats": one branch per format, no rule-level condition needed).
  Each branch: {{"conditions": [...], "who": ..., "why": ..., "for_whom": ...}}.
"""


def _interpretation_prompt(rule_text: str, example: str, instructions: str | None) -> str:
    general = f"\nGENERAL AI INSTRUCTIONS OF THE OPERATOR (context):\n{instructions}\n" if instructions else ""
    return f"""An operator of a bank reconciliation tool wrote this classification rule for bank and card movements:

RULE:
{rule_text}

EXAMPLE movement description the rule was written from:
{example}
{general}
Translate the rule into conditions and assignments that a program will execute on every movement. Use ONLY:

{interpreter_capabilities()}- "coverage": EVERY instruction of the rule, one entry each, in the rule's order:
  {{"instruction": "the instruction, quoted or closely paraphrased from the rule",
    "represented_by": "the element(s) above that carry it out"}}
- "unsupported": the instructions no element above can carry out (an empty list when there is none).

Every TEXT, NAME, A, B, M, N and ENTITY must be copied EXACTLY from the rule. Do not add conditions the rule does
not state and NEVER drop one: if any instruction of the rule cannot be represented with these elements, answer
OTHER, name it in "unsupported" and explain in "reason" — never a simplified version.
Answer ONLY with JSON, no markdown:
{{"kind": "STRUCTURED", "conditions": [...], "who": ..., "why": ..., "for_whom": ..., "status": ...,
  "only_if_who_differs": ..., "replace_existing": ..., "branches": [...], "coverage": [...], "unsupported": []}}
or
{{"kind": "OTHER", "reason": "what cannot be represented", "coverage": [...], "unsupported": ["..."]}}"""


def _in_rule(rule_text: str, value: str) -> bool:
    return bool(_norm(value)) and _norm(value) in _norm(rule_text)


class _Invalid(ValueError):
    pass


def _conditions(raw_conditions, rule_text: str) -> list[dict]:
    if raw_conditions is None:
        return []
    if not isinstance(raw_conditions, list) or len(raw_conditions) > MAX_CONDITIONS:
        raise _Invalid("the conditions are not a short list")
    conditions = []
    for raw in raw_conditions:
        if not isinstance(raw, dict):
            raise _Invalid("a condition is not a structure")
        field, op, value = raw.get("field"), raw.get("op"), str(raw.get("value") or "").strip()
        if field in TEXT_FIELDS:
            if op not in TEXT_FIELDS[field]:
                raise _Invalid(f"“{op}” is not supported for {field}")
            if op in VALUELESS_OPS:
                value = ""
            elif not _in_rule(rule_text, value):
                raise _Invalid(f"the text “{value}” of a condition is not written in the rule")
        elif field in ENUM_FIELDS:
            if op not in ENUM_OPS:
                raise _Invalid(f"“{op}” is not supported for {field}")
            allowed = {v.casefold(): v for v in ENUM_FIELDS[field]}
            if value.casefold() not in allowed:
                raise _Invalid(f"“{value}” is not a value of {field}")
            value = allowed[value.casefold()]
        else:
            raise _Invalid(f"the condition field “{field}” is not supported")
        conditions.append({"field": field, "op": op, "value": value})
    return conditions


def _choice(raw: dict, key: str, allowed: tuple[str, ...], default: str) -> str:
    value = raw.get(key)
    if value is None:
        return default
    value = str(value).strip().lower()
    if value not in allowed:
        raise _Invalid(f"“{value}” is not a value of {key}")
    return value


def _assignment(raw, kind: str, rule_text: str):
    if raw is None:
        return None
    modes = WHO_NAMING + ("to_verify",) if kind == "who" else ("fixed", "who_default", "to_verify")
    if not isinstance(raw, dict) or raw.get("mode") not in modes:
        raise _Invalid(f"the {kind.upper()} assignment is not supported")
    if raw["mode"] == "to_verify":
        return {"mode": "to_verify"}
    if raw["mode"] == "who_default":
        if raw.get("if_missing") is None:
            raise _Invalid("the default WHY does not say what happens when the WHO has none (if_missing)")
        return {"mode": "who_default", "if_missing": _choice(raw, "if_missing", IF_NO_DEFAULT, "")}
    if raw["mode"] in WHO_EXTRACTIONS:
        if raw.get("after_adjacent") is True and raw["mode"] != "to_end":
            raise _Invalid("“after_adjacent” is an option of the “to_end” WHO only")
        cleaned = _extraction(raw, rule_text)
        cleaned.update(_extraction_options(raw))
        return cleaned
    if raw["mode"] == "fixed":
        name = " ".join(str(raw.get("name") or "").split())
        if not _in_rule(rule_text, name):
            raise _Invalid(f"the {kind.upper()} “{name}” is not written in the rule")
        return {"mode": "fixed", "name": name}
    raise _Invalid(f"the {kind.upper()} assignment is not supported")


def _extraction_options(raw: dict) -> dict:
    """BANK_AI_RULES_021 — options of every WHO extraction (absent = off)."""
    options = {}
    for key in ("strip_digits", "require_letter"):
        if raw.get(key) is True:
            options[key] = True
    return options


def _extraction(raw: dict, rule_text: str) -> dict:
    if raw["mode"] == "to_end":
        starts = raw.get("starts")
        if starts is None and raw.get("start"):
            starts = [raw.get("start")]
        if not isinstance(starts, list) or not starts or len(starts) > MAX_START_TEXTS:
            raise _Invalid("the start texts of the WHO are not a short list")
        clean = [" ".join(str(s or "").split()) for s in starts]
        if not all(_in_rule(rule_text, s) for s in clean):
            raise _Invalid("a start text of the WHO is not written in the rule")
        after = raw.get("after")
        after = str(after).strip() if after not in (None, "") else None
        if after is not None and not _in_rule(rule_text, after):
            raise _Invalid(f"the marker “{after}” is not written in the rule")
        result = {"mode": "to_end", "starts": clean, "after": after,
                  "start_at": _choice(raw, "start_at", START_AT, "anywhere")}
        if raw.get("after_adjacent") is True:
            if after is None:
                raise _Invalid("“after_adjacent” needs a marker (after)")
            result["after_adjacent"] = True
        return result
    if raw["mode"] == "before_final_number":
        start = " ".join(str(raw.get("start") or "").split())
        if not _in_rule(rule_text, start):
            raise _Invalid("the text before the WHO is not written in the rule")
        return {"mode": "before_final_number", "start": start,
                "start_at": _choice(raw, "start_at", START_AT, "beginning")}
    if raw["mode"] == "between":
        start = " ".join(str(raw.get("start") or "").split())
        end = str(raw.get("end") or "").strip()
        if not (_in_rule(rule_text, start) and _in_rule(rule_text, end)):
            raise _Invalid("the texts around the WHO are not written in the rule")
        # Absent options keep the v2 behaviour: start at the beginning, end as written.
        return {"mode": "between", "start": start, "end": end,
                "start_at": _choice(raw, "start_at", START_AT, "beginning"),
                "end_case": _choice(raw, "end_case", END_CASE, "as_written")}
    raise _Invalid(f"the WHO extraction “{raw['mode']}” is not supported")


def _entity(raw_value, rule_text: str, entities: "EntityCatalog | None") -> str:
    entity = " ".join(str(raw_value or "").split())
    if not _in_rule(rule_text, entity):
        raise _Invalid(f"the For Whom entity “{entity}” is not written in the rule")
    if entities is not None and entities.resolve(entity) is None:
        raise _Invalid(f"the For Whom entity “{entity}” is not an active entity (an entity is never created)")
    return entity


def _for_whom(raw, rule_text: str, entities: "EntityCatalog | None"):
    """The For Whom assignment (BANK_AI_RULES_010): None (unchanged), a fixed
    entity, or the entity named right after a marker text. Marker, names and
    entities are copied from the rule; with a catalog, every entity must be an
    existing active one — otherwise the whole interpretation is invalid."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("mode") not in ("fixed", "after_text"):
        raise _Invalid("the For Whom assignment is not supported")
    if raw["mode"] == "fixed":
        return {"mode": "fixed", "entity": _entity(raw.get("entity"), rule_text, entities)}
    marker = " ".join(str(raw.get("marker") or "").split())
    if not _in_rule(rule_text, marker):
        raise _Invalid(f"the For Whom text “{marker}” is not written in the rule")
    names = raw.get("names")
    if not isinstance(names, list) or not names or len(names) > MAX_FOR_WHOM_NAMES:
        raise _Invalid("the For Whom names are not a short list")
    clean = []
    for entry in names:
        if not isinstance(entry, dict):
            raise _Invalid("a For Whom name is not a structure")
        name = " ".join(str(entry.get("name") or "").split())
        if not _in_rule(rule_text, name):
            raise _Invalid(f"the For Whom name “{name}” is not written in the rule")
        clean.append({"name": name, "entity": _entity(entry.get("entity"), rule_text, entities)})
    return {"mode": "after_text", "marker": marker, "names": clean}


def _coverage(answer: dict) -> tuple[list[dict], list[str]]:
    """The interpretation's account of EVERY instruction of the rule, and the
    instructions it could not represent. Mandatory: without it nothing shows
    that no instruction was dropped."""
    raw = answer.get("coverage")
    if not isinstance(raw, list) or not raw or len(raw) > MAX_COVERAGE:
        raise _Invalid("the interpretation does not list how each instruction of the rule is represented (coverage)")
    coverage = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise _Invalid("a coverage entry is not a structure")
        instruction = " ".join(str(entry.get("instruction") or "").split())[:500]
        represented = " ".join(str(entry.get("represented_by") or "").split())[:500]
        if not instruction or not represented:
            raise _Invalid("a coverage entry does not say which instruction and how it is represented")
        coverage.append({"instruction": instruction, "represented_by": represented})
    unsupported = answer.get("unsupported") or []
    if not isinstance(unsupported, list):
        raise _Invalid("“unsupported” is not a list")
    return coverage, [" ".join(str(u).split())[:500] for u in unsupported if str(u).strip()]


def _who_default_needs_who(why, who, where: str) -> None:
    if why and why["mode"] == "who_default" and not (who and who["mode"] in WHO_NAMING):
        raise _Invalid(f"the default WHY of the WHO needs a WHO assigned {where}")


def validate_interpretation(answer, rule_text: str, *,
                            entities: "EntityCatalog | None" = None) -> tuple[dict | None, str | None]:
    """(spec, None) when the AI's structure is complete, uses only supported
    elements, copies every text from the rule itself and accounts for every
    instruction of the rule with nothing left unsupported; (None, reason)
    otherwise — the rule then has no executable form, and no simplified
    version of it is ever executed. With `entities`, every For Whom entity
    must also be an existing active entity."""
    if not isinstance(answer, dict):
        return None, "the AI answer is not a structure"
    unsupported = answer.get("unsupported") if isinstance(answer.get("unsupported"), list) else []
    if answer.get("kind") != "STRUCTURED":
        reason = str(answer.get("reason") or "the AI found no executable form").strip()
        named = "; ".join(" ".join(str(u).split()) for u in unsupported if str(u).strip())
        return None, (f"{reason} — not supported: {named}" if named and named not in reason else reason)[:1000]
    try:
        conditions = _conditions(answer.get("conditions"), rule_text)
        who = _assignment(answer.get("who"), "who", rule_text)
        why = _assignment(answer.get("why"), "why", rule_text)
        for_whom = _for_whom(answer.get("for_whom"), rule_text, entities)
        _who_default_needs_who(why, who, "by the rule")
        raw_branches = answer.get("branches") or []
        if not isinstance(raw_branches, list) or len(raw_branches) > MAX_BRANCHES:
            raise _Invalid("the branches are not a short list")
        branches = []
        for i, raw in enumerate(raw_branches, start=1):
            if not isinstance(raw, dict):
                raise _Invalid("a branch is not a structure")
            branch = {"conditions": _conditions(raw.get("conditions"), rule_text),
                      "who": _assignment(raw.get("who"), "who", rule_text),
                      "why": _assignment(raw.get("why"), "why", rule_text),
                      "for_whom": _for_whom(raw.get("for_whom"), rule_text, entities)}
            _who_default_needs_who(branch["why"], branch["who"] or who, f"in branch {i}")
            if not branch["conditions"] and i != len(raw_branches):
                raise _Invalid("only the last branch may have no condition (otherwise)")
            if branch["who"] is None and branch["why"] is None and branch["for_whom"] is None:
                raise _Invalid(f"branch {i} assigns nothing")
            branches.append(branch)
        status = answer.get("status")
        if status is not None and not (isinstance(status, dict) and status.get("mode") == "to_confirm"):
            raise _Invalid("the status assignment is not supported (only “Da confermare”)")
        only_if_who_differs = answer.get("only_if_who_differs") is True
        if only_if_who_differs and not (who and who["mode"] in WHO_NAMING):
            raise _Invalid("“only if the WHO differs” needs a WHO assigned by the rule")
        coverage, unsupported = _coverage(answer)
    except _Invalid as exc:
        return None, str(exc)
    if unsupported:
        return None, "not supported: " + "; ".join(unsupported)
    if not conditions and not (who and who["mode"] in WHO_EXTRACTIONS) and not (
            for_whom and for_whom["mode"] == "after_text") and not (
            branches and all(b["conditions"] for b in branches)):   # one condition per branch, no "otherwise"
        return None, "the rule states no condition"
    if who is None and why is None and for_whom is None and not branches:
        return None, "the rule assigns no WHO, no WHY and no For Whom"
    return {"kind": "STRUCTURED", "version": SPEC_VERSION, "conditions": conditions, "who": who, "why": why,
            "for_whom": for_whom, "branches": branches, "status": TO_CONFIRM if status else None,
            "only_if_who_differs": only_if_who_differs, "replace_existing": answer.get("replace_existing") is True,
            "coverage": coverage}, None


def spec_usable(spec: dict | None) -> bool:
    """A structure the current engine may execute. A v1 structure that read
    "Personal" as "owner is a Person" (`source_owner_kind`) is not."""
    if not spec:
        return False
    if spec.get("version") in USABLE_SPEC_VERSIONS:
        return True
    return "source_owner_kind" not in json.dumps(spec)


def interpretation_key(rule_text: str, instructions: str | None, version: str = INTERPRETATION_VERSION) -> str:
    return _hash(f"{version}\n{rule_text.strip()}\n---\n{(instructions or '').strip()}")


def saved_interpretation(session: Session, rule_text: str,
                         instructions: str | None) -> "m.BankAiRuleInterpretation | None":
    """The interpretation to reuse for this text and these instructions: the
    current engine's, or else a VALID one of a previous engine version still
    executable (`REUSABLE_PREVIOUS_VERSIONS`). A previous BLOCKED one is never
    reused: the rule is interpreted again by the current engine."""
    def by_key(key):
        return session.scalar(select(m.BankAiRuleInterpretation).where(m.BankAiRuleInterpretation.cache_key == key))

    saved = by_key(interpretation_key(rule_text, instructions))
    if saved is not None:
        return saved
    for version in REUSABLE_PREVIOUS_VERSIONS:
        older = by_key(interpretation_key(rule_text, instructions, version))
        if older is not None and older.spec and spec_usable(json.loads(older.spec)):
            return older
    return None


def _interpret(session: Session, rule_text: str, example: str | None, instructions: str | None,
               generate, limiter: _Limiter, calls: _Calls) -> tuple["m.BankAiRuleInterpretation", bool]:
    """The saved interpretation for this rule text and these instructions
    (reused: no AI call), or a new one from ONE AI call."""
    key = interpretation_key(rule_text, instructions)
    saved = saved_interpretation(session, rule_text, instructions)
    if saved is not None:
        return saved, True
    if generate is claude_code_cli.generate_json:
        return _interpret_with_cli(session, rule_text, example, instructions, limiter, calls)
    answer = _call(generate, _interpretation_prompt(rule_text, mask_numbers(example), instructions), limiter, calls)
    spec, reason = validate_interpretation(answer, rule_text, entities=EntityCatalog(session))
    provider, model = ai_client.active_provider_description()
    saved = m.BankAiRuleInterpretation(
        cache_key=key, rule_text=rule_text, instructions_snapshot=instructions,
        raw_answer=json.dumps(answer, ensure_ascii=False)[:20000], spec=json.dumps(spec, ensure_ascii=False) if spec else None,
        rejection_reason=reason, provider=provider, model=model)
    session.add(saved)
    session.flush()
    return saved, False


_CLI_LOCK = threading.Lock()


def _interpret_with_cli(session: Session, rule_text: str, example: str | None, instructions: str | None,
                        limiter: _Limiter, calls: _Calls) -> tuple["m.BankAiRuleInterpretation", bool]:
    """BANK_AI_RULES_012 — one interpretation by the local Claude Code CLI.
    One at a time in this process (two clicks on the same text never ask
    twice). The database read is released while the CLI thinks (it may take
    a minute), so other pages can keep writing meanwhile."""
    example = mask_numbers(example)
    clean = not (session.new or session.dirty or session.deleted)
    if clean:
        session.rollback()                      # ends the read transaction only: nothing is pending
    with _CLI_LOCK:
        saved = saved_interpretation(session, rule_text, instructions)
        if saved is not None:
            return saved, True
        answer = _call(claude_code_cli.generate_json, _interpretation_prompt(rule_text, example, instructions),
                       limiter, calls)
        if clean:
            session.rollback()                  # a fresh read: what others wrote meanwhile is seen
        spec, reason = validate_interpretation(answer, rule_text, entities=EntityCatalog(session))
        saved = m.BankAiRuleInterpretation(
            cache_key=interpretation_key(rule_text, instructions), rule_text=rule_text,
            instructions_snapshot=instructions, raw_answer=json.dumps(answer, ensure_ascii=False)[:20000],
            spec=json.dumps(spec, ensure_ascii=False) if spec else None, rejection_reason=reason,
            provider=claude_code_cli.PROVIDER, model=claude_code_cli.model())
        session.add(saved)
        session.flush()
        if clean:
            # Kept even if the rest of the preview fails: an interpretation is never asked twice.
            session.commit()
        return saved, False


def extract_between(description: str | None, spec: dict) -> tuple[str, str | None]:
    """(outcome, WHO): outcome MATCH, NO_PREFIX, NO_MARKER or EMPTY.
    Prefix: any case — at the start, or with `anywhere` its first occurrence
    anywhere. Marker: the first occurrence after the prefix, as written or,
    with `end_ignore_case`, in any case. WHO: the text between, spaces
    normalized, upper case."""
    text = (description or "").lstrip()
    start = spec["starts_with"]
    if spec.get("anywhere"):
        found = text.lower().find(start.lower())
        if found < 0:
            return "NO_PREFIX", None
        rest = text[found + len(start):]
    else:
        if not text.casefold().startswith(start.casefold()):
            return "NO_PREFIX", None
        rest = text[len(start):]
    marker = spec["end_marker"]
    position = rest.lower().find(marker.lower()) if spec.get("end_ignore_case") else rest.find(marker)
    if position < 0:
        return "NO_MARKER", None
    who = normalize_who(rest[:position])
    return ("MATCH", who) if who else ("EMPTY", None)


def final_number(description: str | None) -> str | None:
    """The description's FINAL NUMBER (BANK_AI_RULES_011): once trimmed, the
    last block made only of digits, preceded by a space — or None."""
    found = FINAL_NUMBER_RE.search((description or "").strip())
    return found.group(1) if found else None


def clean_extracted(name: str | None, assignment: dict) -> tuple[str, str | None, str | None]:
    """(outcome, WHO, why "Da verificare") after the extraction options
    (BANK_AI_RULES_021): "strip_digits" removes every digit 0-9 (letters and
    punctuation kept, spaces collapsed); "require_letter": no letter left →
    no WHO, "Da verificare". Without "require_letter", nothing left = EMPTY."""
    if assignment.get("strip_digits"):
        name = normalize_who(re.sub(r"[0-9]", "", name or ""))
    if assignment.get("require_letter") and not any(ch.isalpha() for ch in (name or "")):
        return "MATCH", None, "the extracted text has no letter"
    if not name:
        return "EMPTY", None, None
    return "MATCH", name, None


def extract_to_end(description: str | None, assignment: dict) -> tuple[str, str | None]:
    """(outcome, WHO) of a "to_end" WHO (BANK_AI_RULES_015): the earliest
    occurrence of any start text (any case; at the beginning — leading spaces
    ignored — or anywhere), then, with a marker, its first occurrence after
    it (any case); the WHO is everything after, to the end of the description
    — nothing removed, outer spaces trimmed, spaces collapsed, upper case.
    NO_PREFIX (no start text), NO_MARKER (no marker after it), EMPTY."""
    text = (description or "").strip()
    found = None
    for start in assignment["starts"]:
        pattern = r"\s+".join(map(re.escape, start.split()))
        match = (re.search(pattern, text, re.IGNORECASE) if assignment.get("start_at") != "beginning"
                 else re.match(pattern, text, re.IGNORECASE))
        if match and (found is None or match.start() < found.start()):
            found = match
    if found is None:
        return "NO_PREFIX", None
    rest = text[found.end():]
    marker = assignment.get("after")
    if marker:
        position = rest.lower().find(marker.lower())
        if position < 0 or (assignment.get("after_adjacent") and rest[:position].strip()):
            return "NO_MARKER", None              # no marker — or, adjacent only, something else before it
        rest = rest[position + len(marker):]
    who = normalize_who(rest)
    return ("MATCH", who) if who else ("EMPTY", None)


def extract_before_final_number(description: str | None, assignment: dict) -> tuple[str, str | None]:
    """(outcome, WHO): the text after the start text A (any case; at the
    beginning — leading spaces ignored — or anywhere) and before the final
    number; spaces trimmed and collapsed, upper case; numbers inside the text
    are kept. NO_PREFIX (A missing), NO_MARKER (no final number after A) or
    EMPTY (nothing between)."""
    text = (description or "").strip()
    start = assignment["start"]
    pattern = r"\s+".join(map(re.escape, start.split()))
    found = (re.search(pattern, text, re.IGNORECASE) if assignment.get("start_at") == "anywhere"
             else re.match(pattern, text, re.IGNORECASE))
    if found is None:
        return "NO_PREFIX", None
    rest = text[found.end():]
    number = FINAL_NUMBER_RE.search(rest)          # a space, then only digits, at the very end
    if number is None:
        return "NO_MARKER", None
    who = normalize_who(rest[:number.start()])
    return ("MATCH", who) if who else ("EMPTY", None)


def _field_value(row: Row, field: str) -> str | None:
    return {
        "description": row.txn.description_original,
        "source_name": row.source_name,
        "source_owner_name": row.owner_name,
        "source_type": row.source_type,
        "direction": "money out" if row.txn.amount_minor < 0 else "money in",
    }[field]


def _truth(condition: dict, row: Row) -> bool | None:
    """True / False, or None when the data the condition needs is missing
    (only the Source's Personal classification can be missing)."""
    op = condition["op"]
    if condition["field"] == "source_class":
        value, have = condition["value"], row.source_class
        if value == "missing":
            result = have is None
        elif have is None:
            return None
        else:
            result = have == (SOURCE_PERSONAL if value == "Personal" else SOURCE_NOT_PERSONAL)
        return result if op == "is" else not result
    if op == "ends_with_number":
        return final_number(_field_value(row, condition["field"])) is not None
    if op in ("starts_with_word", "not_starts_with_word"):
        actual, value = _norm(_field_value(row, condition["field"])), _norm(condition["value"])
        hit = actual.startswith(value) and (len(actual) == len(value) or actual[len(value)].isspace())
        return hit if op == "starts_with_word" else not hit
    actual = _norm(_field_value(row, condition["field"]))
    value = _norm(condition["value"])
    if op == "contains":
        return value in actual
    if op == "not_contains":
        return value not in actual
    if op == "starts_with":
        return actual.startswith(value)
    if op == "is":
        return actual == value
    return actual != value                 # is_not


def _all(conditions: list[dict], row: Row) -> bool | None:
    results = [_truth(c, row) for c in conditions]
    if any(r is False for r in results):
        return False
    if any(r is None for r in results):
        return None
    return True


@dataclass
class Exec:
    """What a structured rule does to one movement. `who` / `why`: the name
    to assign (None = unchanged); `who_verify` / `why_verify`: why that field
    is "Da verificare" instead (never assigned)."""
    outcome: str                      # MATCH, NO_MATCH, NO_MARKER, EMPTY, UNKNOWN
    who: str | None = None
    why: str | None = None
    who_verify: str | None = None
    why_verify: str | None = None
    branch: str | None = None
    note: str | None = None
    # BANK_AI_RULES_008 — `why_default`: the WHY is the default WHY of the WHO
    # assigned, resolved in the catalog by the Planner ("clear" / "unchanged":
    # what happens when that WHO has none). The rule-level options travel
    # with the result so every caller plans with them.
    why_default: str | None = None
    status: str | None = None
    only_if_who_differs: bool = False
    replace_existing: bool = False
    # BANK_AI_RULES_010 — `for_whom`: the entity (as the rule writes it) to
    # assign, None = unchanged; `for_whom_note`: why For Whom stays unchanged
    # (marker or name not found); `for_whom_verify`: why it is "Da verificare".
    for_whom: str | None = None
    for_whom_note: str | None = None
    for_whom_verify: str | None = None

    @property
    def assigns(self) -> bool:
        return (self.who is not None or self.why is not None or self.why_default is not None
                or self.for_whom is not None)

    @property
    def to_verify(self) -> str | None:
        fields = [f for f, v in (("WHO", self.who_verify), ("WHY", self.why_verify),
                                 ("FOR_WHOM", self.for_whom_verify)) if v]
        return ",".join(fields) or None


def match_after_text(description: str | None, assignment: dict) -> tuple[str | None, str]:
    """(entity, note) of an `after_text` For Whom: the marker's first
    occurrence (any case), the spaces after it skipped, then the first listed
    name the text begins with — complete (any case, any run of spaces between
    its words) and followed by the end, a space or other data, never by more
    letters or digits. No marker or no name: (None, why)."""
    text = description or ""
    marker = assignment["marker"]
    found = re.search(r"\s+".join(map(re.escape, marker.split())), text, re.IGNORECASE)
    if found is None:
        return None, f"“{marker}” is not in the description"
    rest = text[found.end():].lstrip()
    for entry in assignment["names"]:
        pattern = r"\s+".join(map(re.escape, entry["name"].split())) + r"(?![^\W_])"
        if re.match(pattern, rest, re.IGNORECASE):
            return entry["entity"], f"“{marker}” {entry['name']}"
    shown = " ".join(rest.split())[:40]
    return None, f"the name after “{marker}” (“{shown}”) is none of those listed"


def _missing_note(row: Row) -> str:
    return f"the Source's Personal classification is missing ({row.source_class_basis or 'no owner recorded'})"


def execute(spec: dict, row: Row) -> Exec:
    """The rule on one movement. Rule conditions false → NO_MATCH; not
    decidable (missing classification) → UNKNOWN. Branches are checked in
    order: the first whose conditions hold assigns; one that cannot be
    decided makes the fields it — and any later branch — would set
    "Da verificare" (never the next branch's value)."""
    holds = _all(spec["conditions"], row)
    if holds is False:
        return Exec("NO_MATCH")
    if holds is None:
        return Exec("UNKNOWN", note=f"{TO_VERIFY}: {_missing_note(row)}.")
    result = Exec("MATCH", status=spec.get("status"), only_if_who_differs=bool(spec.get("only_if_who_differs")),
                  replace_existing=bool(spec.get("replace_existing")))

    def assign(kind: str, assignment, label: str) -> str | None:
        if assignment is None:
            return None
        if assignment["mode"] == "to_verify":
            setattr(result, kind, None)
            setattr(result, f"{kind}_verify", f"the rule says {TO_VERIFY} ({label})")
            if kind == "why":
                result.why_default = None
            return None
        if assignment["mode"] == "who_default":
            result.why, result.why_verify, result.why_default = None, None, assignment["if_missing"]
            return None
        if assignment["mode"] in ("before_final_number", "to_end"):
            extract = extract_to_end if assignment["mode"] == "to_end" else extract_before_final_number
            outcome, name = extract(row.txn.description_original, assignment)
            if outcome != "MATCH":
                return outcome
            outcome, name, verify = clean_extracted(name, assignment)
            if outcome != "MATCH":
                return outcome
            setattr(result, kind, name)
            setattr(result, f"{kind}_verify", verify)
            return None
        elif assignment["mode"] == "between":
            outcome, name = extract_between(row.txn.description_original, {
                "starts_with": assignment["start"], "end_marker": assignment["end"],
                "anywhere": assignment.get("start_at") == "anywhere",
                "end_ignore_case": assignment.get("end_case") == "ignore"})
            if outcome != "MATCH":
                return outcome
            outcome, name, verify = clean_extracted(name, assignment)
            if outcome != "MATCH":
                return outcome
            setattr(result, kind, name)
            setattr(result, f"{kind}_verify", verify)
            return None
        else:
            setattr(result, kind, assignment["name"])
            if kind == "why":
                result.why_default = None
        setattr(result, f"{kind}_verify", None)
        return None

    def assign_for_whom(assignment) -> None:
        if assignment is None:
            return
        result.for_whom_verify = None
        if assignment["mode"] == "fixed":
            result.for_whom, result.for_whom_note = assignment["entity"], None
            return
        result.for_whom, result.for_whom_note = match_after_text(row.txn.description_original, assignment)
        if result.for_whom is not None:
            result.for_whom_note = None
        else:
            result.for_whom_note = f"For Whom unchanged: {result.for_whom_note}"

    for kind in ("who", "why"):
        problem = assign(kind, spec.get(kind), "rule")
        if problem:
            return Exec("NO_MATCH") if problem == "NO_PREFIX" else Exec(problem)
    assign_for_whom(spec.get("for_whom"))
    branches = spec.get("branches") or []
    for i, branch in enumerate(branches, start=1):
        decided = _all(branch["conditions"], row)
        if decided is False:
            continue
        if decided is None:
            reason = f"branch {i} cannot be decided: {_missing_note(row)}"
            for later in branches[i - 1:]:
                for kind in ("who", "why", "for_whom"):
                    if later.get(kind) is not None:
                        setattr(result, kind, None)
                        setattr(result, f"{kind}_verify", reason)
                        if kind == "why":
                            result.why_default = None
                        if kind == "for_whom":
                            result.for_whom_note = None
            result.branch = f"branch {i}: {TO_VERIFY}"
            break
        for kind in ("who", "why"):
            problem = assign(kind, branch.get(kind), f"branch {i}")
            if problem:
                return Exec("NO_MATCH") if problem == "NO_PREFIX" else Exec(problem)
        assign_for_whom(branch.get("for_whom"))
        result.branch = f"branch {i}" if branch["conditions"] else "otherwise"
        break
    else:
        if branches:
            result.branch = "no branch applies"
            # BANK_AI_RULES_021 — no "otherwise" and nothing assigned outside the
            # branches: a movement where no branch holds is not this rule's.
            if not any(spec.get(k) is not None for k in ("who", "why", "for_whom")):
                return Exec("NO_MATCH")
    return result


_FIELD_LABEL = {"description": "the description", "source_name": "the Source name",
                "source_owner_name": "the Source owner's name", "source_type": "the Source",
                "direction": "the movement", "source_class": "the Source"}
_OP_LABEL = {"contains": "contains", "not_contains": "does not contain", "starts_with": "starts with",
             "starts_with_word": "starts with (followed by a space or the end)",
             "not_starts_with_word": "does not start with (followed by a space or the end)",
             "is": "is", "is_not": "is not"}
_ENUM_LABEL = {"card": "a card", "bank account": "a bank account", "money out": "money out", "money in": "money in",
               "Personal": "classified Personal", "not Personal": "classified not Personal",
               "missing": "without a Personal classification (missing)"}


def _condition_text(c: dict, quote: bool = True) -> str:
    if c["op"] == "ends_with_number":
        return (f"{_FIELD_LABEL[c['field']]} ends with a FINAL NUMBER (a space, then only digits — a code mixing "
                "letters and digits is not one)")
    if c["field"] in TEXT_FIELDS:
        return f"{_FIELD_LABEL[c['field']]} {_OP_LABEL[c['op']]} “{c['value']}”" + (" (upper/lower case alike)" if quote else "")
    return f"{_FIELD_LABEL[c['field']]} {_OP_LABEL[c['op']]} {_ENUM_LABEL[c['value']]}"


def _uses_class(spec: dict) -> bool:
    return any(c["field"] == "source_class" for c in spec["conditions"]) or any(
        c["field"] == "source_class" for b in spec.get("branches") or [] for c in b["conditions"])


def _assignment_text(kind: str, assignment, who_status: _WhoStatus, why_catalog: _WhyCatalog) -> str:
    if assignment is None:
        return f"{kind.upper()}: unchanged"
    if assignment["mode"] == "to_verify":
        return f"{kind.upper()}: {TO_VERIFY}"
    if assignment["mode"] == "who_default":
        return ("WHY: the default WHY registered on the WHO assigned (never deduced); if that WHO has none: "
                + ("the WHY is emptied" if assignment["if_missing"] == "clear" else "the WHY stays as it is"))
    if assignment["mode"] == "to_end":
        starts = " or ".join(f"“{s}”" for s in assignment["starts"])
        where = "at the start" if assignment.get("start_at") == "beginning" else "anywhere in the description"
        after = f", after the first following “{assignment['after']}”" if assignment.get("after") else ""
        return (f"WHO: the text after the first {starts} ({where}, any case){after}, up to the END of the "
                "description — nothing removed (codes and numbers stay), outer spaces trimmed, upper case; no start "
                "text, no marker after it or nothing after: the movement is not changed")
    if assignment["mode"] == "before_final_number":
        where = ("anywhere in the description" if assignment.get("start_at") == "anywhere"
                 else "at the start, leading spaces ignored")
        return (f"WHO: the text after “{assignment['start']}” ({where}, any case) and before the description's FINAL "
                "NUMBER (the last block of only digits, after a space; trailing spaces ignored), spaces trimmed and "
                "collapsed, upper case, other numbers kept; no final number or nothing between: the movement is not "
                "changed")
    if assignment["mode"] == "between":
        where = "anywhere in the description" if assignment.get("start_at") == "anywhere" else "at the start"
        case = "any case" if assignment.get("end_case") == "ignore" else "as written"
        return (f"WHO: the text after “{assignment['start']}” ({where}, any case) and before the first following "
                f"“{assignment['end']}” ({case}, also attached to a code), spaces trimmed and collapsed, upper case; "
                "a missing text, the wrong order or nothing between: the movement is not changed")
    if kind == "who":
        who_id, name, error = who_status(assignment["name"])
        state = (f"cannot be created: {error}" if error else "new WHO" if who_id is None
                 else "existing" if normalize_who(name) == normalize_who(assignment["name"]) else f"is already the WHO {name}")
        return f"WHO: {normalize_who(assignment['name'])} ({state})"
    why_id = why_catalog.resolve(assignment["name"])
    return (f"WHY: {why_catalog.name_of[why_id]} (existing, {why_catalog.code_of[why_id]})" if why_id
            else f"WHY: “{assignment['name']}” — not in the WHY list: not applied (a WHY is never created)")


def _entity_text(value: str, entities: "EntityCatalog | None") -> str:
    if entities is None:
        return value
    entity_id = entities.resolve(value)
    return (f"{entities.name_of[entity_id]} (existing entity, {entities.code_of[entity_id]})" if entity_id
            else f"“{value}” — not an active entity: not applied (an entity is never created)")


def _for_whom_text(assignment, entities: "EntityCatalog | None") -> str:
    if assignment is None:
        return "FOR WHOM: unchanged"
    if assignment["mode"] == "fixed":
        return f"FOR WHOM: {_entity_text(assignment['entity'], entities)}"
    names = "; ".join(f"“{e['name']}” → {_entity_text(e['entity'], entities)}" for e in assignment["names"])
    return (f"FOR WHOM (decided on its own, not from the WHO): after the first “{assignment['marker']}” of the "
            f"description (any case), spaces skipped, the text begins with — the complete name, any case, followed "
            f"by the end, spaces or other data: {names}. “{assignment['marker']}” missing or another name: "
            "For Whom unchanged")


def _options_text(assignment) -> str:
    parts = []
    if isinstance(assignment, dict):
        if assignment.get("after_adjacent"):
            parts.append(f"only spaces between the start text and “{assignment.get('after')}”")
        if assignment.get("strip_digits"):
            parts.append("every digit 0-9 removed from the extracted text (letters and punctuation kept)")
        if assignment.get("require_letter"):
            parts.append(f"no letter left → no WHO, {TO_VERIFY}")
    return ("; " + "; ".join(parts)) if parts else ""


def describe_spec(spec: dict, who_status: _WhoStatus, why_catalog: _WhyCatalog,
                  entities: "EntityCatalog | None" = None) -> list[str]:
    """The interpretation in words — conditions and assignments of the rule
    and of each branch, the data checked, how WHO, WHY and For Whom
    resolve."""
    lines = []
    for c in spec["conditions"]:
        lines.append("IF " + _condition_text(c))
    who = spec.get("who")
    if who and who["mode"] == "between":
        verb = "contains" if who.get("start_at") == "anywhere" else "starts with"
        lines.append(f"IF the description {verb} “{who['start']}” and later contains “{who['end']}”")
    if who and who["mode"] == "before_final_number":
        verb = "contains" if who.get("start_at") == "anywhere" else "starts with"
        lines.append(f"IF the description {verb} “{who['start']}” and ends with a final number after it")
    if who and who["mode"] == "to_end":
        verb = "starts with" if who.get("start_at") == "beginning" else "contains"
        lines.append(f"IF the description {verb} " + " or ".join(f"“{s}”" for s in who["starts"])
                     + (f" and later contains “{who['after']}”" if who.get("after") else ""))
    if who is not None or not spec.get("branches"):
        lines.append(_assignment_text("who", who, who_status, why_catalog) + _options_text(who))
    if spec.get("why") is not None or not spec.get("branches"):
        lines.append(_assignment_text("why", spec.get("why"), who_status, why_catalog))
    if spec.get("for_whom") is not None:
        lines.append(_for_whom_text(spec.get("for_whom"), entities))
    branches = spec.get("branches") or []
    for i, branch in enumerate(branches, start=1):
        head = ("OTHERWISE" if not branch["conditions"]
                else f"BRANCH {i} — IF " + " AND ".join(_condition_text(c, quote=False) for c in branch["conditions"]))
        parts = [_assignment_text(k, branch.get(k), who_status, why_catalog)
                 + (_options_text(branch.get(k)) if k == "who" else "") for k in ("who", "why")
                 if branch.get(k) is not None]
        if branch.get("for_whom") is not None:
            parts.append(_for_whom_text(branch["for_whom"], entities))
        lines.append(f"{head} → " + "; ".join(parts))
    if branches:
        lines.append("Branches are checked in order; the first that holds applies. If one cannot be decided "
                     f"(classification missing) its WHO/WHY/For Whom — and any later branch's — is {TO_VERIFY}, "
                     "never assigned. If none applies, they stay unchanged.")
    if spec.get("only_if_who_differs"):
        lines.append("ONLY IF the movement's WHO differs (case and spaces aside): with the same WHO nothing changes "
                     "— no WHO, WHY, For Whom or status change")
    if spec.get("status"):
        lines.append(f"STATUS: a movement whose WHO, WHY or For Whom this rule changes becomes “{TO_CONFIRM_LABEL}” "
                     f"(decision not resolved: {TO_CONFIRM_DECISION_STATUS}; reconciliation status Needs review); "
                     "a movement on which nothing changes keeps its status")
    if spec.get("replace_existing"):
        lines.append("REPLACES a different WHO / WHY / For Whom decided by another rule or an earlier automatic "
                     "decision")
    if spec.get("version", 0) >= 3:
        lines.append(PROTECTIONS_TEXT)
    if _uses_class(spec):
        lines.append("Data checked — " + SOURCE_CLASS_BASIS)
    for entry in spec.get("coverage") or []:
        lines.append(f"INSTRUCTION “{entry['instruction']}” → {entry['represented_by']}")
    return lines


def _match_reason(spec: dict, ex: "Exec | None" = None) -> str:
    parts = [_condition_text(c, quote=False) for c in spec["conditions"]]
    who = spec.get("who")
    if who and who["mode"] == "between":
        parts.append(f"WHO extracted between “{who['start']}” and “{who['end']}”")
    if who and who["mode"] == "before_final_number":
        parts.append(f"WHO extracted between “{who['start']}” and the final number")
    if who and who["mode"] == "to_end":
        parts.append("WHO extracted after " + " / ".join(f"“{s}”" for s in who["starts"])
                     + (f" and the first “{who['after']}”" if who.get("after") else "") + " up to the end of the description")
    if not parts:
        parts.append("no condition besides the extraction")
    text = "Conditions checked by the code: " + "; ".join(parts) + "."
    if ex is not None and ex.branch:
        text += f" Branch: {ex.branch}."
    if ex is not None:
        for kind, reason in (("WHO", ex.who_verify), ("WHY", ex.why_verify), ("For Whom", ex.for_whom_verify)):
            if reason:
                text += f" {kind} {TO_VERIFY}: {reason}."
        if ex.for_whom_note:
            text += f" {ex.for_whom_note}."
    return text


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def _item(row: Row, verdict: str, reason: str | None, is_origin: bool, resolved: dict) -> "m.BankAiRulePreviewItem":
    who_error = resolved.pop("who_error", None)
    who_note = resolved.pop("who_note", None)
    if who_note:
        reason = f"{reason} {who_note}" if reason else who_note
    if who_error:
        said = who_error if who_error.startswith(WHO_DOUBT) else f"WHO cannot be created: {who_error}"
        reason = f"{reason} — {said}" if reason else said
    return m.BankAiRulePreviewItem(
        financial_transaction_id=row.id, verdict=verdict, is_origin=is_origin, posting_date=row.txn.posting_date,
        description=row.txn.description_original or "", amount_minor=row.txn.amount_minor, currency=row.currency,
        source_label=row.source_label[:255], current_who_name=row.current_who, current_why_name=row.current_why,
        reason=(reason or "")[:2000] or None, **resolved)




# ---------------------------------------------------------------------------
# What applying would do (BANK_AI_RULES_006) — shared by Preview, the
# application to existing movements and the import
# ---------------------------------------------------------------------------

UPDATED, UNCHANGED, PROTECTED, CONFLICT, UNRESOLVED = "UPDATED", "UNCHANGED", "PROTECTED", "CONFLICT", "UNRESOLVED"
PLAN_OUTCOMES = (UPDATED, UNCHANGED, PROTECTED, CONFLICT, UNRESOLVED)


def rule_note_prefix(rule_id: int | None) -> str | None:
    """How a decision written by an operative AI rule starts its notes, so a
    later application of the SAME rule may replace its own earlier output."""
    return f"AI Rule #{rule_id} " if rule_id else None


@dataclass
class Target:
    """What a rule assigns to one movement, resolved in the catalogs. Only
    the fields the rule names are set; the others stay as they are."""
    who_set: bool = False
    who_id: int | None = None
    who_name: str | None = None
    who_new: bool = False
    who_error: str | None = None
    why_set: bool = False
    why_id: int | None = None
    why_name: str | None = None
    # BANK_AI_RULES_008
    why_clear: bool = False                 # the WHY is emptied
    why_note: str | None = None             # how the WHY was resolved (the WHO's default WHY)
    to_confirm: bool = False                # a changed movement becomes "Da confermare"
    only_if_who_differs: bool = False
    replace_existing: bool = False
    # BANK_AI_RULES_010 — For Whom: the active entity the rule assigns;
    # `for_whom_name` is the rule's text when it is not an active entity.
    for_whom_set: bool = False
    for_whom_id: int | None = None
    for_whom_name: str | None = None
    # BANK_AI_RULES_011 — the rule's option "Sostituisci anche WHO/WHY
    # manuali, Standard o confermati" (off by default, set per rule).
    override_protected: bool = False

    @property
    def sets_anything(self) -> bool:
        return self.who_set or self.why_set or self.for_whom_set

    def who_key(self):
        return self.who_id if self.who_id is not None else ("NEW", self.who_name)

    def why_key(self):
        if self.why_clear:
            return ("CLEAR",)
        return self.why_id if self.why_id is not None else ("NAME", _norm(self.why_name))


def _default_why(session: Session, target: Target, if_missing: str, why_catalog: _WhyCatalog) -> None:
    """The WHY of a `who_default` assignment: the default WHY registered on the
    WHO the rule assigns (`BankOccurrence.default_transaction_reason_id`),
    never deduced. A new WHO, an unusable WHO or no default: `if_missing`."""
    occurrence = session.get(m.BankOccurrence, target.who_id) if target.who_id is not None else None
    default_id = occurrence.default_transaction_reason_id if occurrence is not None else None
    if default_id is not None:
        target.why_set, target.why_id = True, default_id if default_id in why_catalog.name_of else None
        target.why_name = why_catalog.name_of.get(default_id) or f"default WHY #{default_id} (not active)"
        target.why_note = f"default WHY of {target.who_name}"
        return
    if not target.who_set or target.who_error:
        return                               # no WHO to take a default from: the WHY is not touched
    whose = f"new WHO {target.who_name}" if target.who_new else f"WHO {target.who_name}"
    if if_missing == "clear":
        target.why_set, target.why_clear, target.why_note = True, True, (
            f"{whose} has no default WHY: WHY empty — da completare (never invented; not settled by AI rules)")
    else:
        target.why_note = f"{whose} has no default WHY: WHY unchanged"


def target_for(who: str | None, why: str | None, who_status: _WhoStatus, why_catalog: _WhyCatalog,
               ex: "Exec | None" = None, entities: "EntityCatalog | None" = None) -> Target:
    target = Target()
    if ex is not None and ex.for_whom:
        entities = entities or EntityCatalog(who_status.session)
        entity_id = entities.resolve(ex.for_whom)
        target.for_whom_set, target.for_whom_id = True, entity_id
        target.for_whom_name = entities.name_of[entity_id] if entity_id else ex.for_whom
    if who:
        who_id, name, error = who_status(who)
        target.who_set, target.who_id, target.who_name, target.who_error = True, who_id, name, error
        target.who_new = who_id is None and error is None
    if why:
        why_id = why_catalog.resolve(why)
        target.why_set, target.why_id = True, why_id
        target.why_name = why_catalog.name_of[why_id] if why_id else why
    if ex is not None:
        if ex.why_default:
            _default_why(who_status.session, target, ex.why_default, why_catalog)
        target.to_confirm = bool(ex.status)
        target.only_if_who_differs = ex.only_if_who_differs
        target.replace_existing = ex.replace_existing
    return target


def _active_rule_specs(session: Session, exclude_rule_id: int | None = None) -> list[tuple[int, dict]]:
    """(rule id, executable structure) of every ACTIVE operative rule's
    current version that the code can execute."""
    found = []
    for rule in session.scalars(select(m.BankAiRule).where(m.BankAiRule.status == "ACTIVE",
                                                           m.BankAiRule.deleted_at.is_(None))):
        if rule.id == exclude_rule_id or not rule.versions:
            continue
        version = rule.versions[-1]
        spec = json.loads(version.spec) if version.spec else None
        if spec_usable(spec):
            found.append((rule.id, spec))
    return found


FW_NONE, FW_HUMAN, FW_AUTOMATIC, FW_UNCERTAIN = "NONE", "HUMAN", "AUTOMATIC", "UNCERTAIN"


@dataclass
class ForWhomState:
    """A movement's current For Whom and WHERE IT COMES FROM
    (BANK_AI_RULES_010), read from its allocations:

      NONE        no allocation;
      HUMAN       chosen by a person (decision source HUMAN);
      AUTOMATIC   one line written by a rule (decision source RULE, no
                  document evidence) — may be updated;
      UNCERTAIN   anything else: a split, a line with no decision source
                  (e.g. pending evidence), a line from document evidence —
                  kept, with `reason`.

    `complete`: the allocation set is accounting-complete (confirmed or
    automatic) — the movement itself is then protected."""
    provenance: str = FW_NONE
    entity_id: int | None = None
    name: str | None = None
    complete: bool = False
    mine: bool = False
    reason: str | None = None


def for_whom_state(allocations: list, names: dict[int, str], prefix: str | None) -> ForWhomState:
    if not allocations:
        return ForWhomState()
    complete = all(a.status == m.ALLOCATION_COMPLETE for a in allocations)
    if len(allocations) > 1:
        shown = ", ".join(sorted({names.get(a.reporting_entity_id) or "—" for a in allocations}))
        return ForWhomState(FW_UNCERTAIN, None, f"split: {shown}", complete,
                            reason=f"the movement is split across {len(allocations)} allocations")
    a = allocations[0]
    name = (names.get(a.reporting_entity_id) or a.reporting_entity_name_snapshot) if a.reporting_entity_id else None
    state = ForWhomState(FW_UNCERTAIN, a.reporting_entity_id, name, complete)
    if a.decision_source == "HUMAN":
        state.provenance = FW_HUMAN
    elif a.decision_source == "RULE" and not a.evidence_kind:
        state.provenance = FW_AUTOMATIC
        state.mine = bool(prefix and (a.notes or "").startswith(prefix))
    elif a.decision_source == "RULE":
        state.reason = f"written from document evidence ({a.evidence_kind})"
    else:
        state.reason = f"no decision source recorded (allocation {a.status})"
    return state


@dataclass
class Plan:
    """What applying would do to one movement."""
    outcome: str
    note: str
    who_after: str | None
    why_after: str | None
    for_whom_before: str | None = None
    for_whom_after: str | None = None
    changes: tuple[str, ...] = ()
    # BANK_AI_RULES_011 — the protections the rule's option overrides on this
    # movement (traced in the note and in the decision written); whether its
    # confirmation is withdrawn (For Whom kept); other AI rules on it.
    overridden: tuple[str, ...] = ()
    withdraw_acceptance: bool = False
    overlaps: tuple[str, ...] = ()

    def as_tuple(self) -> tuple[str, str, str | None, str | None]:
        return self.outcome, self.note, self.who_after, self.why_after


def own_account_ids(session: Session) -> set[int]:
    """The movements between two of RF-One's own accounts — both sides of
    every matched internal transfer. They have no WHO by design, so a rule
    never gives them one. (The structural WHO recognitions this once also
    read belonged to the old rule system, retired by BANK_RULES_RESET_001.)"""
    own: set[int] = set()
    for a, b in session.execute(select(m.FinancialTransactionMatch.transaction_a_id,
                                       m.FinancialTransactionMatch.transaction_b_id)):
        own.update((a, b))
    return own


class Planner:
    """Plans, for one movement a rule matched, what applying would do —
    never writing anything:

      PROTECTED   a manual (HUMAN) classification, a Standard, an own-account
                  movement (no WHO by design), a movement whose For Whom is
                  accounting-complete or written by a Standard, or a movement
                  where the only change would touch a For Whom chosen by a
                  person or of uncertain origin (kept, with the reason);
      UNRESOLVED  a WHO that cannot become one, a new WHO without "Crea WHO
                  mancanti", a WHY not in the WHY list (a WHY is never
                  created), an entity that is not an active one (never
                  created);
      CONFLICT    a field the rule sets already holds a DIFFERENT value
                  decided by something else (another rule, an earlier
                  decision), or another active AI rule assigns a different
                  value to the same movement — reported, never settled by
                  execution order;
      UNCHANGED   every field the rule sets already has that value;
      UPDATED     otherwise: the fields the rule sets — and only those —
                  get the rule's values.

    For Whom is protected by PROVENANCE (`ForWhomState`, BANK_AI_RULES_010),
    never just because one is recorded: a For Whom kept while WHO / WHY
    change is said in the note."""

    def __init__(self, session: Session, *, rule_id: int | None = None, preload: bool = True,
                 other_rules: bool = True):
        self.session = session
        self.prefix = rule_note_prefix(rule_id)
        self.own = own_account_ids(session) if preload else None
        self.allocations: dict[int, list] | None = None
        if preload:
            self.allocations = {}
            for a in session.scalars(select(m.BankTransactionAllocation)
                                     .order_by(m.BankTransactionAllocation.allocation_index)):
                self.allocations.setdefault(a.financial_transaction_id, []).append(a)
        self.others = _active_rule_specs(session, exclude_rule_id=rule_id) if other_rules else []
        self.who_status = _WhoStatus(session)
        self.why_catalog = _WhyCatalog(_catalog(session)[1])
        self.entities = EntityCatalog(session)

    def is_own(self, txn_id: int) -> bool:
        if self.own is not None:
            return txn_id in self.own
        return bool(self.session.scalar(
            select(func.count(m.FinancialTransactionMatch.id)).where(or_(
                m.FinancialTransactionMatch.transaction_a_id == txn_id,
                m.FinancialTransactionMatch.transaction_b_id == txn_id))))

    def allocations_of(self, txn_id: int) -> list:
        if self.allocations is not None:
            return self.allocations.get(txn_id, [])
        return list(self.session.scalars(select(m.BankTransactionAllocation).where(
            m.BankTransactionAllocation.financial_transaction_id == txn_id)
            .order_by(m.BankTransactionAllocation.allocation_index)))

    def for_whom(self, txn_id: int) -> ForWhomState:
        return for_whom_state(self.allocations_of(txn_id), self.entities.name_of, self.prefix)

    def target(self, who: str | None, why: str | None) -> Target:
        return target_for(who, why, self.who_status, self.why_catalog)

    def target_of(self, ex: Exec) -> Target:
        """The target of a structured rule's result, with its options."""
        return target_for(ex.who, ex.why, self.who_status, self.why_catalog, ex, self.entities)

    def other_conflicts(self, row: Row, target: Target) -> list[str]:
        return self.other_rules(row, target)[0]

    def other_rules(self, row: Row, target: Target) -> tuple[list[str], list[str]]:
        """(conflicts, overlaps) with the other ACTIVE AI rules: a different
        value for the same field is a conflict; any other active AI rule that
        also matches the movement — or wrote its current WHO / WHY — is an
        overlap, shown (BANK_AI_RULES_011)."""
        notes, overlaps = [], []
        current = row.explanation
        written = re.match(r"AI Rule #(\d+) ", (current.explanation_notes or "") if current is not None else "")
        if written and f"AI Rule #{written.group(1)} " != self.prefix:
            overlaps.append(f"current WHO / WHY written by AI rule #{written.group(1)}")
        for other_id, spec in self.others:
            ex = execute(spec, row)
            if ex.outcome != "MATCH" or not ex.assigns:
                continue
            other = self.target_of(ex)
            same = []
            if target.who_set and other.who_set and other.who_key() == target.who_key():
                same.append(f"same WHO {other.who_name}")
            overlaps.append(f"also matched by AI rule #{other_id}" + (f" ({', '.join(same)})" if same else ""))
            if target.who_set and other.who_set and other.who_key() != target.who_key():
                notes.append(f"AI rule #{other_id} assigns WHO {other.who_name}")
            if target.why_set and other.why_set and other.why_key() != target.why_key():
                notes.append(f"AI rule #{other_id} assigns WHY {other.why_name}")
            if target.for_whom_set and other.for_whom_set and other.for_whom_id != target.for_whom_id:
                notes.append(f"AI rule #{other_id} assigns For Whom {other.for_whom_name}")
        return notes, overlaps

    def plan(self, row: Row, target: Target, *, create_missing_who: bool) -> tuple[str, str, str | None, str | None]:
        """(outcome, note, WHO after, WHY after)."""
        return self.plan_full(row, target, create_missing_who=create_missing_who).as_tuple()

    def plan_full(self, row: Row, target: Target, *, create_missing_who: bool) -> Plan:
        current = row.explanation
        who_before, why_before = row.current_who, row.current_why
        fw = self.for_whom(row.id)

        def keep(outcome: str, note: str) -> Plan:
            return Plan(outcome, note, who_before, why_before, fw.name, fw.name)

        if not target.sets_anything:
            return keep(UNCHANGED, "The rule names no WHO, no WHY and no For Whom for this movement.")
        if target.who_set and target.who_error:
            return keep(UNRESOLVED, (f"{target.who_error}: not applied." if target.who_error.startswith(WHO_DOUBT)
                                     else f"WHO cannot be created: {target.who_error}"))
        if target.who_set and target.who_new and not create_missing_who:
            return keep(UNRESOLVED, f"WHO {target.who_name} is not in the WHO list and “Create missing WHO” is off.")
        if target.why_set and not target.why_clear and target.why_id is None:
            return keep(UNRESOLVED, f"WHY “{target.why_name}” is not in the WHY list (a WHY is never created).")
        if target.for_whom_set and target.for_whom_id is None:
            return keep(UNRESOLVED, f"For Whom “{target.for_whom_name}” is not an active entity (an entity is "
                                    "never created).")
        # BANK_AI_RULES_011 — the rule's explicit option may override the
        # protections of WHO / WHY (never For Whom, never own-account): the
        # movement's For Whom is kept, its confirmation withdrawn.
        override = target.override_protected and (target.who_set or target.why_set) and not target.for_whom_set
        overridden = []
        if current is not None and current.decision_source == "HUMAN":
            if not override:
                return keep(PROTECTED, "Protected: classified manually.")
            overridden.append("a manual classification")
        split = len(self.allocations_of(row.id)) > 1
        if fw.complete:
            # An accepted For Whom: changing WHO / WHY / status would undo that acceptance.
            who_did = "confirmed by a person" if fw.provenance == FW_HUMAN else "accounting-complete"
            if not override:
                return keep(PROTECTED, f"Protected: For Whom {fw.name or '—'} {who_did}.")
            if split:
                return keep(PROTECTED, f"Protected: For Whom {fw.name or '—'} {who_did} on a split movement — its "
                                       "For Whom could not be kept, so it is not overridden.")
            overridden.append("a confirmation")
        if target.who_set and self.is_own(row.id):
            return keep(PROTECTED, "Protected: own-account movement (no WHO by design).")
        have_who = current.occurrence_id if current is not None else None
        same_who = target.who_set and have_who is not None and not target.who_new and have_who == target.who_id
        if target.only_if_who_differs and same_who:
            return keep(UNCHANGED, "Same WHO: nothing changes (WHY, For Whom and status kept).")
        mine = bool(current is not None and self.prefix and (current.explanation_notes or "").startswith(self.prefix))
        replace = mine or target.replace_existing or bool(overridden)
        changes, conflicts, kept = [], [], []
        if target.who_set:
            if same_who:
                pass
            elif have_who is None or replace:
                changes.append("WHO")
            else:
                conflicts.append(f"the WHO is already {who_before}, decided elsewhere")
        if target.why_set:
            have = current.transaction_reason_id if current is not None else None
            want = None if target.why_clear else target.why_id
            if have == want:
                pass
            elif have is None or replace:
                changes.append("WHY")
            else:
                conflicts.append(f"the WHY is already {why_before}, decided elsewhere")
        if target.for_whom_set:
            if fw.entity_id == target.for_whom_id:
                pass
            elif fw.provenance == FW_NONE:
                changes.append("For Whom")
            elif fw.provenance == FW_HUMAN:
                kept.append(f"For Whom {fw.name or '—'} chosen by a person: kept")
            elif fw.provenance == FW_AUTOMATIC:
                if fw.mine or target.replace_existing:
                    changes.append("For Whom")
                else:
                    conflicts.append(f"For Whom is already {fw.name or '—'}, decided by another rule")
            else:
                kept.append(f"For Whom {fw.name or '—'} kept: its origin is uncertain ({fw.reason})")
        other_conflicts, overlaps = self.other_rules(row, target)
        conflicts += other_conflicts
        also = (" Overlap: " + "; ".join(overlaps) + ".") if overlaps else ""
        if conflicts:
            plan = keep(CONFLICT, "Conflict: " + "; ".join(conflicts) + "." + also)
            plan.overlaps = tuple(overlaps)
            return plan
        if not changes:
            if kept:
                plan = keep(PROTECTED, "Protected: " + "; ".join(kept) + "." + also)
            else:
                plan = keep(UNCHANGED, "Already as the rule says" + (" (nothing is overridden, status kept)"
                                                                     if overridden else "") + "." + also)
            plan.overlaps = tuple(overlaps)
            return plan
        who_after = target.who_name if "WHO" in changes else who_before
        why_after = (None if target.why_clear else target.why_name) if "WHY" in changes else why_before
        for_whom_after = target.for_whom_name if "For Whom" in changes else fw.name
        what = ", ".join(changes[:-1]) + " and " + changes[-1] if len(changes) > 1 else changes[0]
        note = f"{what} would change" + (" (new WHO created)" if target.who_new and "WHO" in changes else "")
        if target.why_note:
            note += f"; {target.why_note}"
        for item in kept:
            note += f"; {item}"
        if overridden:
            note += (f"; OVERRIDES {' and '.join(overridden)} (rule option “{OVERRIDE_LABEL}”)"
                     + ("; confirmation withdrawn, For Whom kept" if fw.complete else ""))
        if target.to_confirm or overridden:
            note += f"; status → {TO_CONFIRM_LABEL}"
        return Plan(UPDATED, note + "." + also, who_after, why_after, fw.name, for_whom_after, tuple(changes),
                    overridden=tuple(overridden), withdraw_acceptance=bool(overridden and fw.complete),
                    overlaps=tuple(overlaps))


# ---------------------------------------------------------------------------
# Conflicts with the other active rules
# ---------------------------------------------------------------------------
# A rule and another ACTIVE rule that both match the same movement and assign
# it a different WHO or WHY: the Planner reports such a movement as CONFLICT
# and changes nothing (BANK_AI_RULES_011). These helpers say it BEFORE the
# rule is applied — at Rewrite with AI, Preview and Save and Apply — as a
# conflict between rules, distinct from a problem of the rule's own text.
# Read only: nothing is resolved, no rule is changed or disabled.

def rule_label(rule_id: int | None, title: str | None) -> str:
    """How a rule is named in a conflict: "Rule #104 ‘SHELL’", or "This rule"
    for a rule not saved yet."""
    name = " ".join((title or "").split())
    if rule_id:
        return f"Rule #{rule_id}" + (f" ‘{name}’" if name else "")
    return "This rule" + (f" ‘{name}’" if name else "")


def _rule_paths(spec: dict) -> list[tuple[list[dict], dict | None, dict | None, str | None]]:
    """(conditions, WHO assignment, WHY assignment, branch) of every way the
    rule can assign: the rule itself, or each of its branches."""
    branches = spec.get("branches") or []
    if not branches:
        return [(list(spec["conditions"]), spec.get("who"), spec.get("why"), None)]
    return [(list(spec["conditions"]) + list(b["conditions"]), b.get("who") or spec.get("who"),
             b.get("why") or spec.get("why"), f"branch {i}" if b["conditions"] else "otherwise")
            for i, b in enumerate(branches, start=1)]


def _matched_conditions(spec: dict, ex: Exec) -> list[dict]:
    """The conditions that made the rule assign on one movement: the rule's
    and those of the branch that applied."""
    conditions = list(spec["conditions"])
    found = re.match(r"branch (\d+)$", ex.branch or "")
    if found:
        conditions += (spec.get("branches") or [])[int(found.group(1)) - 1]["conditions"]
    return conditions


def _conditions_text(conditions: list[dict]) -> str:
    return " and ".join(_condition_text(c, quote=False) for c in conditions) or "any movement"


def _fixed_name(assignment: dict | None) -> str | None:
    return assignment["name"] if assignment and assignment.get("mode") == "fixed" else None


def _static_overlap(a: list[dict], b: list[dict]) -> bool:
    """Two sets of conditions that can hold on the same movement, judged on the
    text alone: every condition is "the description contains" and, for each
    pair, one text contains the other (any case)."""
    if not a or not b or any(c["field"] != "description" or c["op"] != "contains" for c in a + b):
        return False
    return all(x["value"].casefold() in y["value"].casefold() or y["value"].casefold() in x["value"].casefold()
               for x in a for y in b)


def rule_conflicts(session: Session, spec: dict | None, *, rule_id: int | None = None, title: str | None = None,
                   rows: list[Row] | None = None) -> list[dict]:
    """The other ACTIVE rules that assign a different WHO or WHY to movements
    this rule also assigns: one entry per rule, with the overlapping
    conditions, what each rule assigns, how many movements and an example.
    Found on the movements in scope; when none shows it, two "description
    contains" rules whose texts overlap are reported too, without an example.
    Read only."""
    if not spec or not spec_usable(spec):
        return []
    others = _active_rule_specs(session, exclude_rule_id=rule_id)
    if not others:
        return []
    planner = Planner(session, rule_id=rule_id, preload=False, other_rules=False)
    if rows is None:
        rows = scope_rows(session, scope=SCOPE_ALL, date_from=None, date_to=None)
    titles = {r.id: (r.user_title or r.title) for r in session.scalars(
        select(m.BankAiRule).where(m.BankAiRule.id.in_([rid for rid, _s in others])))}
    own = rule_label(rule_id, title)
    found: dict[int, dict] = {}
    for row in rows:
        ex = execute(spec, row)
        if ex.outcome != "MATCH" or not (ex.who or ex.why):
            continue
        mine = planner.target_of(ex)
        for other_id, other_spec in others:
            oex = execute(other_spec, row)
            if oex.outcome != "MATCH" or not (oex.who or oex.why):
                continue
            theirs = planner.target_of(oex)
            fields = []
            if mine.who_set and theirs.who_set and mine.who_key() != theirs.who_key():
                fields.append("WHO")
            if mine.why_set and theirs.why_set and mine.why_key() != theirs.why_key():
                fields.append("WHY")
            if not fields:
                continue
            entry = found.get(other_id)
            if entry is None:
                entry = found[other_id] = dict(
                    rule_id=other_id, rule_title=titles.get(other_id) or "", fields=fields, count=0,
                    this=dict(who=mine.who_name if mine.who_set else None, why=mine.why_name if mine.why_set else None,
                              conditions=_conditions_text(_matched_conditions(spec, ex))),
                    other=dict(who=theirs.who_name if theirs.who_set else None,
                               why=theirs.why_name if theirs.why_set else None,
                               conditions=_conditions_text(_matched_conditions(other_spec, oex)), branch=oex.branch),
                    example=dict(id=row.txn.id, date=row.txn.posting_date.isoformat() if row.txn.posting_date else None,
                                 description=row.txn.description_original,
                                 amount=f"{row.txn.amount_minor / 100:.2f}"))
            entry["count"] += 1
    # Text-only overlap of two "description contains" rules no movement shows yet.
    for other_id, other_spec in others:
        if other_id in found:
            continue
        for conds, who, why, _branch in _rule_paths(spec):
            for oconds, owho, owhy, obranch in _rule_paths(other_spec):
                if not _static_overlap(conds, oconds):
                    continue
                fields = []
                if _fixed_name(who) and _fixed_name(owho) and normalize_who(_fixed_name(who)) != normalize_who(_fixed_name(owho)):
                    fields.append("WHO")
                if _fixed_name(why) and _fixed_name(owhy) and _fixed_name(why).casefold() != _fixed_name(owhy).casefold():
                    fields.append("WHY")
                if fields and other_id not in found:
                    found[other_id] = dict(
                        rule_id=other_id, rule_title=titles.get(other_id) or "", fields=fields, count=0,
                        this=dict(who=_fixed_name(who), why=_fixed_name(why), conditions=_conditions_text(conds)),
                        other=dict(who=_fixed_name(owho), why=_fixed_name(owhy), conditions=_conditions_text(oconds),
                                   branch=obranch),
                        example=None)
    result = []
    for entry in sorted(found.values(), key=lambda e: e["rule_id"]):
        def said(side: dict) -> str:
            return " and ".join(f"{f} = {side[f.lower()]}" for f in entry["fields"])
        other = rule_label(entry["rule_id"], entry["rule_title"])
        entry["message"] = (f"{own} assigns {said(entry['this'])}, while {other[0].lower() + other[1:]}"
                            f" assigns {said(entry['other'])} to the movements where {entry['other']['conditions']}.")
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def preview_rule(session: Session, *, rule_text: str | None, origin_transaction_id: int | None,
                 date_from: date | None, date_to: date | None, draft_id: int | None = None,
                 account_id: int | None = None, create_missing_who: bool = False,
                 scope: str = SCOPE_PERIOD, selected_ids: list[int] | None = None, ai_rule_id: int | None = None,
                 generate: Callable[[str], dict] | None = None,
                 allow_ai_batches: bool = False, override_protected: bool = False,
                 only_unsettled: bool = False, who_only: bool = False,
                 title: str | None = None) -> "m.BankAiRulePreview":
    """Evaluate the rule on every movement of the scope — the displayed
    period, ALL the in-scope movements, or the SELECTED ones — and plan what
    applying would do to each match. The rule is interpreted once (or the
    saved interpretation reused); a rule with an executable structure is run
    by code with no size limit. A rule the structure cannot fully represent
    is BLOCKED with the reason (BANK_AI_RULES_008): it is judged by the AI in
    batches (at most MAX_PERIOD_MOVEMENTS, throttling retried, completed
    batches kept) only when that is asked explicitly (`allow_ai_batches`),
    never as an automatic fallback. A preview that could not evaluate every
    movement is FAILED, never shown as complete. Nothing is written on
    movements. The caller commits."""
    rule_text = (rule_text or "").strip()
    if not rule_text:
        raise AiRuleError("Write the rule before asking for a preview.")
    if scope not in SCOPES:
        raise AiRuleError("Unknown scope.")
    origin = row_for(session, origin_transaction_id)
    if origin is None:
        raise AiRuleError("The origin transaction could not be found; reload the page.")
    rows = scope_rows(session, scope=scope, date_from=date_from, date_to=date_to, selected_ids=selected_ids)
    if scope == SCOPE_PERIOD and all(r.id != origin.id for r in rows):
        rows = [origin] + rows          # exploring a period: the example is always evaluated too
    rows, excluded_by_rule = without_ai_settled(session, rows, only_unsettled)
    provider, model = active_ai_description()
    preview = m.BankAiRulePreview(
        draft_id=draft_id, rule_text=rule_text, origin_transaction_id=origin.id,
        date_from=date_from if scope == SCOPE_PERIOD else None, date_to=date_to if scope == SCOPE_PERIOD else None,
        examined_count=len(rows), match_count=0, doubt_count=0, ai_calls=0, provider=provider,
        model=model, status="FAILED", method=m.AI_RULE_METHOD_AI, create_missing_who=bool(create_missing_who),
        override_protected=bool(override_protected), only_unsettled=bool(only_unsettled), who_only=bool(who_only),
        excluded_ai_settled=sum(excluded_by_rule.values()),
        scope=scope, scope_key=scope_key(rule_text=rule_text, scope=scope, selected_ids=selected_ids,
                                         create_missing_who=create_missing_who, date_from=date_from, date_to=date_to,
                                         override_protected=override_protected, only_unsettled=only_unsettled,
                                         who_only=who_only),
        created_by_account_id=account_id, started_at=datetime.now(timezone.utc))
    generate = generate or default_generate()
    who_status = _WhoStatus(session)
    whos, whys = _catalog(session)
    why_catalog = _WhyCatalog(whys)
    instruction = current_instruction(session)
    instructions = instruction.instructions if instruction and instruction.instructions else None
    limiter, calls = _Limiter(PARALLEL), _Calls()
    info: dict = {"excluded_by_rule": excluded_by_rule}

    def finish(status: str, message: str | None = None) -> "m.BankAiRulePreview":
        preview.status = status
        preview.error_message = message[:2000] if message else None
        preview.ai_calls = calls.count
        info["throttled"] = limiter.throttled
        preview.interpretation = json.dumps(info, ensure_ascii=False)
        preview.finished_at = datetime.now(timezone.utc)
        session.add(preview)
        session.flush()
        return preview

    try:
        interpretation, reused = _interpret(session, rule_text, origin.txn.description_original, instructions,
                                            generate, limiter, calls)
    except SessionInterpretationNeeded:
        calls.count = 0                       # nothing was called: the session interprets
        finish("FAILED", session_wait_message("?"))
        preview.error_message = session_wait_message(preview.id)
        return preview
    except ai_client.AIProviderUnavailable as exc:
        return finish("FAILED", f"The AI could not interpret the rule: {exc}")
    info.update(interpretation_id=interpretation.id, reused=reused, rejected=interpretation.rejection_reason)
    # Who actually answered: the interpretation's own provider and model (it
    # may be a saved one, from another provider or a Claude Code session).
    info.update(interpretation_provider=interpretation.provider, interpretation_model=interpretation.model)
    spec = json.loads(interpretation.spec) if interpretation.spec else None
    # row, verdict, reason, WHO, WHY, fields "Da verificare", structured result
    found: list[tuple[Row, str, str | None, str | None, str | None, str | None, Exec | None]] = []

    if spec is not None:
        preview.method = m.AI_RULE_METHOD_CODE
        preview.provider, preview.model = interpretation.provider, interpretation.model
        info.update(spec=spec, lines=describe_spec(spec, who_status, why_catalog, EntityCatalog(session)))
        if who_only:
            info["lines"].insert(0, f"MODE “{WHO_ONLY_LABEL}”: only the WHO part of this rule is executed — its WHY, "
                                    "the WHO's default WHY and For Whom are NOT applied now (kept in the rule for a "
                                    "later phase); a conflict is a different WHO only")
        outcomes: dict[str, int] = {}
        for row in rows:
            ex = execute(spec, row)
            if who_only:
                ex = who_only_exec(ex)
                if ex.outcome == "MATCH" and ex.who is None and not ex.who_verify:
                    outcomes["NO_WHO"] = outcomes.get("NO_WHO", 0) + 1     # the rule names no WHO here
                    continue
            outcomes[ex.outcome] = outcomes.get(ex.outcome, 0) + 1
            if ex.outcome == "MATCH":
                # Every field the rule would set is "Da verificare": nothing to apply — a doubtful case.
                verdict = MATCH if ex.assigns or not ex.to_verify else DOUBT
                found.append((row, verdict, _match_reason(spec, ex), ex.who, ex.why, ex.to_verify, ex))
            elif ex.outcome == "EMPTY":
                found.append((row, DOUBT, "No text between the two delimiters: no WHO to extract.", None, None,
                              None, None))
            elif ex.outcome == "UNKNOWN":
                found.append((row, DOUBT, ex.note, None, None, "RULE", None))
        info["outcomes"] = outcomes
    elif not allow_ai_batches:
        preview.provider, preview.model = interpretation.provider, interpretation.model
        return finish("FAILED", (
            "Blocked: the interpretation does not represent every instruction of the rule "
            f"({interpretation.rejection_reason or 'no executable form'}). No simplified version is "
            "executed and no movement-by-movement AI evaluation is started automatically."))
    else:
        if len(rows) > MAX_PERIOD_MOVEMENTS:
            return finish("FAILED", (
                f"This rule has no form the code can execute, so the AI must judge each movement: the scope has "
                f"{len(rows)} movements and the AI evaluates at most {MAX_PERIOD_MOVEMENTS}. Choose a shorter period "
                "or select the movements, or write the rule so the code can execute it."))
        refs = {f"T{i}": row for i, row in enumerate(rows, start=1)}
        lines = [_line(ref, row) for ref, row in refs.items()]
        context = _context(rule_text, _line("EXAMPLE", origin), instructions, whos, whys)
        batches = [lines[i:i + BATCH_SIZE] for i in range(0, len(lines), BATCH_SIZE)]
        hashes = [_hash(_prompt(context, batch)) for batch in batches]
        saved = {r.prompt_hash: json.loads(r.items_json) for r in session.scalars(
            select(m.BankAiRuleBatchResult).where(m.BankAiRuleBatchResult.prompt_hash.in_(hashes)))}
        todo = [i for i, h in enumerate(hashes) if h not in saved]
        answers: dict[int, list[dict]] = {i: saved[h] for i, h in enumerate(hashes) if h in saved}
        failures: list[tuple[int, str]] = []
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            futures = {i: pool.submit(_ask, generate, context, batches[i], limiter, calls) for i in todo}
            for i, future in futures.items():
                try:
                    answers[i] = future.result()
                except ai_client.AIProviderUnavailable as exc:
                    failures.append((i + 1, str(exc)))
        for i in todo:                  # every completed batch is kept, even when another failed
            if i in answers:
                session.add(m.BankAiRuleBatchResult(prompt_hash=hashes[i],
                                                    items_json=json.dumps(answers[i], ensure_ascii=False)))
        info.update(batches=len(batches), batches_reused=len(batches) - len(todo),
                    batches_done=len(answers), batches_failed=len(failures))
        if failures:
            number, error = failures[0]
            return finish("FAILED", (
                f"{len(failures)} of {len(batches)} AI calls failed after retries (call {number}: {error}). "
                f"{len(answers)} of {len(batches)} are completed and kept: run Preview again to continue — "
                "they will not be asked again. No partial result is shown."))
        seen: set[str] = set()
        for i in sorted(answers):
            for item in answers[i]:
                ref = str(item.get("ref") or "").strip()
                verdict = str(item.get("verdict") or "").strip().upper()
                row = refs.get(ref)
                if row is None or ref in seen or verdict not in (MATCH, DOUBT):
                    continue
                seen.add(ref)
                why_value = str(item.get("why_code") or "").strip() or str(item.get("why_name") or "").strip() or None
                found.append((row, verdict, str(item.get("reason") or "").strip(), item.get("who"), why_value, None,
                              None))

    planner = Planner(session, rule_id=ai_rule_id)
    counts = dict.fromkeys(PLAN_OUTCOMES, 0)
    overlap_count, overlap_rules, overridden_count, who_reused = 0, {}, 0, 0
    for row, verdict, reason, who, why_value, to_verify, ex in found:
        target = planner.target_of(ex) if ex is not None else planner.target(who, why_value)
        target.override_protected = bool(override_protected)
        if ex is not None and ex.why_default and target.why_set and not target.why_clear:
            why_value = target.why_name           # the WHO's default WHY, shown as the proposed WHY
        resolved = _resolve({"who": who, "why_name": why_value}, who_status, why_catalog)
        if verdict == MATCH and (resolved.get("who_error") or "").startswith(WHO_DOUBT):
            verdict, to_verify = DOUBT, None      # several existing WHO could be it: shown, never chosen
        if resolved.get("extracted_who_name") and who_status.how.get(resolved["extracted_who_name"]) == REUSED_SUBJECT:
            who_reused += 1
        item = _item(row, verdict, reason, row.id == origin.id, resolved)
        item.to_verify = to_verify
        # BANK_AI_RULES_010 — For Whom, current and proposed, on every item.
        item.current_for_whom_name = planner.for_whom(row.id).name
        if target.for_whom_set:
            item.proposed_for_whom_name, item.proposed_for_whom_id = target.for_whom_name, target.for_whom_id
        if verdict == MATCH:
            plan = planner.plan_full(row, target, create_missing_who=bool(create_missing_who))
            outcome, note = plan.outcome, plan.note
            if plan.overlaps:
                overlap_count += 1
                keys = set()                          # each movement counted once per rule
                for text in plan.overlaps:
                    found_rule = re.search(r"(AI rule|WHO rule) #(\d+)", text)
                    if found_rule:
                        keys.add(("" if found_rule.group(1) == "AI rule" else "WHO ") + found_rule.group(2))
                for key in keys:
                    overlap_rules[key] = overlap_rules.get(key, 0) + 1
            if plan.overridden:
                overridden_count += 1
            if to_verify:
                note += f" {to_verify.replace(',', ' and ')} {TO_VERIFY}: not assigned."
            item.plan, item.plan_note = outcome, note
            counts[outcome] += 1
        elif (resolved.get("who_error") or "").startswith(WHO_DOUBT):
            item.plan_note = f"{resolved['who_error']}: never applied — choose the WHO by hand."
        else:
            item.plan_note = (f"{TO_VERIFY}: never applied." if to_verify else "Doubtful: never applied.")
        preview.items.append(item)
    preview.items.sort(key=lambda i: (not i.is_origin, i.posting_date or date.min, i.financial_transaction_id or 0))
    preview.match_count = sum(1 for i in preview.items if i.verdict == MATCH)
    preview.doubt_count = sum(1 for i in preview.items if i.verdict == DOUBT)
    preview.planned_updates, preview.unchanged_count = counts[UPDATED], counts[UNCHANGED]
    preview.protected_count, preview.conflict_count = counts[PROTECTED], counts[CONFLICT]
    preview.unresolved_count = counts[UNRESOLVED]
    info.update(overlaps=overlap_count, overlap_rules=overlap_rules, overridden=overridden_count,
                who_reused=who_reused)
    # Conflicts with the other active rules on EVERY in-scope movement, whatever this Preview's scope: what
    # Save and Apply (and the import) would report as CONFLICT, said as a conflict between rules.
    if ai_rule_id and not title:
        saved_rule = session.get(m.BankAiRule, ai_rule_id)
        title = saved_rule.user_title if saved_rule is not None else None
    info.update(rule_conflicts=rule_conflicts(session, info.get("spec"), rule_id=ai_rule_id, title=title))
    return finish("COMPLETED")


def uses_for_whom(spec: dict | None) -> bool:
    """The rule assigns For Whom somewhere (rule or branch)."""
    return bool(spec) and (spec.get("for_whom") is not None
                           or any(b.get("for_whom") is not None for b in spec.get("branches") or []))


def preview_as_dict(preview: "m.BankAiRulePreview") -> dict:
    def item(i):
        return dict(id=i.financial_transaction_id, is_origin=i.is_origin,
                    date=i.posting_date.isoformat() if i.posting_date else None, description=i.description,
                    amount=f"{i.amount_minor / 100:.2f}", currency=i.currency or "", source=i.source_label,
                    who=i.current_who_name, why=i.current_why_name, reason=i.reason,
                    proposed_who=i.proposed_who_name, proposed_who_is_new=i.proposed_who_is_new,
                    extracted_who=i.extracted_who_name,
                    proposed_why=i.proposed_why_name, proposed_why_is_new=i.proposed_why_is_new,
                    who_to_verify="WHO" in (i.to_verify or "").split(",") or i.to_verify == "RULE",
                    why_to_verify="WHY" in (i.to_verify or "").split(",") or i.to_verify == "RULE",
                    for_whom=i.current_for_whom_name, proposed_for_whom=i.proposed_for_whom_name,
                    proposed_for_whom_is_entity=i.proposed_for_whom_id is not None,
                    for_whom_to_verify="FOR_WHOM" in (i.to_verify or "").split(","),
                    plan=i.plan, plan_note=i.plan_note)
    origin = next((i for i in preview.items if i.is_origin), None)
    info = json.loads(preview.interpretation) if preview.interpretation else {}
    outcomes = info.get("outcomes") or {}
    new_names = sorted({i.proposed_who_name for i in preview.items
                        if i.verdict == MATCH and i.proposed_who_is_new and i.proposed_who_name})
    return dict(
        ok=preview.status == "COMPLETED", preview_id=preview.id, status=preview.status, error=shown_message(preview.error_message),
        rule_text=preview.rule_text, examined=preview.examined_count, matches=preview.match_count,
        doubts=preview.doubt_count, ai_calls=preview.ai_calls, provider=preview.provider, model=preview.model,
        method=preview.method, interpretation_lines=info.get("lines") or [],
        interpretation_reused=bool(info.get("reused")), interpretation_rejected=info.get("rejected"),
        interpretation_provider=info.get("interpretation_provider"),
        interpretation_model=info.get("interpretation_model"),
        not_matching=outcomes.get("NO_MATCH"), not_matching_with_prefix=outcomes.get("NO_MARKER"),
        batches=info.get("batches"), batches_reused=info.get("batches_reused"), throttled=info.get("throttled"),
        create_missing_who=preview.create_missing_who, new_who_names=new_names,
        for_whom_rule=uses_for_whom(info.get("spec")) and not preview.who_only,
        who_only=bool(preview.who_only), who_only_label=WHO_ONLY_LABEL,
        override_protected=bool(preview.override_protected), override_label=OVERRIDE_LABEL,
        overlaps=info.get("overlaps") or 0, overlap_rules=info.get("overlap_rules") or {},
        overridden=info.get("overridden") or 0, who_reused=info.get("who_reused") or 0,
        only_unsettled=bool(preview.only_unsettled), only_unsettled_label=ONLY_UNSETTLED_LABEL,
        excluded_ai_settled=preview.excluded_ai_settled or 0, excluded_by_rule=info.get("excluded_by_rule") or {},
        rule_conflicts=info.get("rule_conflicts") or [],
        scope=preview.scope, scope_key=preview.scope_key,
        planned_updates=preview.planned_updates, unchanged=preview.unchanged_count,
        protected=preview.protected_count, conflicts=preview.conflict_count, unresolved=preview.unresolved_count,
        date_from=preview.date_from.isoformat() if preview.date_from else None,
        date_to=preview.date_to.isoformat() if preview.date_to else None,
        origin_verdict=origin.verdict if origin is not None else None,
        match_items=[item(i) for i in preview.items if i.verdict == MATCH],
        doubt_items=[item(i) for i in preview.items if i.verdict == DOUBT],
    )


# ---------------------------------------------------------------------------
# "Inserisci nuovi WHO in elenco" — the WHO catalog only
# ---------------------------------------------------------------------------

def create_missing_whos(session: Session, *, preview_id: int) -> dict:
    """Create the missing WHO of the CERTAIN matches (MATCH) of a completed
    preview made with "Crea WHO mancanti". Each distinct name once; a name
    that already is a WHO (case and spaces aside) is reused, so pressing
    again creates nothing. Created through the existing WHO service: an
    active Counterparty WHO with no WHY — nothing invented. Touches the WHO
    catalog only. The caller commits."""
    from . import configuration
    from . import who_rules

    preview = session.get(m.BankAiRulePreview, preview_id)
    if preview is None:
        raise AiRuleError("This preview no longer exists; run Preview again.")
    if preview.status != "COMPLETED":
        raise AiRuleError("Only a completed preview can add WHO to the list.")
    if not preview.create_missing_who:
        raise AiRuleError("“Create missing WHO” was not active for this preview.")
    names = list(dict.fromkeys(normalize_who(i.proposed_who_name) for i in preview.items
                               if i.verdict == MATCH and i.proposed_who_name))
    created, present, errors = [], [], []
    for name in names:
        try:
            existing, clean = who_rules.check_new_who(session, name)
        except ValueError as exc:
            errors.append({"name": name, "error": str(exc)})
            continue
        if existing is not None:
            present.append(existing.canonical_name)
            continue
        occurrence = configuration.save_who(
            session, occurrence_id=None, name=clean, active=True, reason_ids=[], default_reason_id=None,
            reporting_entity_ids=[])
        session.flush()
        created.append(occurrence.canonical_name)
    return {"ok": True, "created": created, "already_present": present, "errors": errors,
            "created_count": len(created), "present_count": len(present), "error_count": len(errors)}
