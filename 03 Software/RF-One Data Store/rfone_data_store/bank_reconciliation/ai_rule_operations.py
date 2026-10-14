"""Operative AI rules: Salva, Salva e Applica, and the import (BANK_AI_RULES_006).

A draft (`BankAiRuleDraft`) is only kept. An OPERATIVE rule (`BankAiRule`) is
saved with "Salva" — a new version (`BankAiRuleVersion`) when the text or the
option changed, carrying the interpretation validated for it, so a rule the
code can execute never needs a new AI call to be applied — and may be:

  * applied to existing movements ("Salva e Applica"): ALL the in-scope
    movements of the database or exactly the SELECTED ones, only on the
    strength of a COMPLETED preview of the same text, scope, selection and
    option; the plan is recomputed on the current data at that moment;
  * applied by the import to new movements ("Per il futuro") — the only
    automatic classification at import (BANK_RULES_RESET_001); only rules the
    code can execute.

What is written: for each movement planned UPDATED (see `ai_rules.Planner`)
one new decision row through `recognition._create_decision_row` — the ONE
place decisions are created, append-only — setting ONLY the fields the rule
names (a WHO-only rule keeps the WHY, its WHAT and status); and, with "Crea
WHO mancanti", the WHO it needs, created by the WHO service once per name
(existing names and aliases reused). Never a WHY. Manual decisions are
protected; differing values
decided elsewhere are conflicts, reported and left as they are. Every
application is logged (`BankAiRuleApplication` and its items: outcome, WHO/WHY
before and after).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..selection.parsing import ai_client
from . import ai_rules
from . import economic_allocation
from . import recognition

AiRuleError = ai_rules.AiRuleError
MODE_ALL, MODE_SELECTED, MODE_IMPORT = "EXISTING_ALL", "SELECTED", "IMPORT"


class NeedsPreview(AiRuleError):
    """No valid preview of the same text and scope: preview first."""


class InterpretationInvalid(AiRuleError):
    """The interpretation of this text is not executable: nothing is saved as
    operative. Raised BEFORE anything else is written, so the caller may keep
    the interpretation itself (it is reused, with its reason, without asking
    the AI again)."""


def current_version(rule: "m.BankAiRule") -> "m.BankAiRuleVersion | None":
    return rule.versions[-1] if rule.versions else None


def rules(session: Session) -> list["m.BankAiRule"]:
    """The rules of the page: every rule not deleted."""
    return list(session.scalars(select(m.BankAiRule).where(m.BankAiRule.deleted_at.is_(None))
                                .order_by(m.BankAiRule.status, m.BankAiRule.id.desc())))


def delete_rule(session: Session, *, rule_id: int, account_id: int | None) -> "m.BankAiRule":
    """Delete (BANK_AI_RULES_014): the rule leaves the page and is never
    executed again — not by Preview, Apply or the import (status INACTIVE,
    `deleted_at`); it cannot be reactivated or saved. NOTHING written on
    movements changes: their decisions and allocations stay, and so does the
    history of where they came from (versions, previews, applications and
    their items, the decisions' notes). A draft of a change to it becomes a
    draft of a new rule."""
    rule = session.get(m.BankAiRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise AiRuleError("This rule no longer exists; reload the page.")
    rule.status = "INACTIVE"
    rule.apply_future = False
    rule.deleted_at = datetime.now(timezone.utc)
    rule.deleted_by_account_id = account_id
    for draft in session.scalars(select(m.BankAiRuleDraft).where(m.BankAiRuleDraft.ai_rule_id == rule.id)):
        draft.ai_rule_id = None
    session.flush()
    return rule


# ---------------------------------------------------------------------------
# Salva
# ---------------------------------------------------------------------------

@dataclass
class SaveResult:
    rule: "m.BankAiRule"
    version: "m.BankAiRuleVersion"
    new_version: bool
    created: bool


def save_rule(session: Session, *, rule_id: int | None, rule_text: str | None, create_missing_who: bool,
              apply_future: bool, origin_transaction_id: int | None, account_id: int | None,
              generate=None, draft_id: int | None = None, override_protected: bool = False) -> SaveResult:
    """Save the rule as OPERATIVE (active). The interpretation is the saved
    one for this text and these instructions, or a new one (one AI call).

    BANK_AI_RULES_009 — a rule becomes (or stays) operative ONLY with a valid
    interpretation of exactly this text: none yet, or one that is not
    executable, is refused with what is missing — nothing is saved, and an
    operative rule keeps its current version. The rule keeps its identity:
    the rule being edited, or the operative rule a draft belongs to; never a
    duplicate. The draft itself is removed by `remove_draft`, after success."""
    rule_text = (rule_text or "").strip()
    if not rule_text:
        raise AiRuleError("Write the rule before saving it.")
    draft = session.get(m.BankAiRuleDraft, draft_id) if draft_id else None
    if not rule_id and draft is not None and draft.ai_rule_id:
        rule_id = draft.ai_rule_id
    rule = session.get(m.BankAiRule, rule_id) if rule_id else None
    if rule_id and (rule is None or rule.deleted_at is not None):
        raise AiRuleError("This rule no longer exists (it was deleted); reload the page.")
    origin = session.get(m.FinancialTransaction, origin_transaction_id) if origin_transaction_id else None
    if rule is None and origin is None:
        raise AiRuleError("The origin transaction could not be found; reload the page.")
    instruction = ai_rules.current_instruction(session)
    instructions = instruction.instructions if instruction and instruction.instructions else None
    try:
        interpretation, _reused = ai_rules._interpret(
            session, rule_text, (origin.description_original if origin else rule.origin_description), instructions,
            generate or ai_rules.default_generate(), ai_rules._Limiter(1), ai_rules._Calls())
    except ai_rules.SessionInterpretationNeeded as exc:
        raise AiRuleError("Questa regola non ha ancora un'interpretazione: premi Preview e fai interpretare la regola "
                          "dalla sessione Claude Code, poi salva di nuovo.") from exc
    except ai_client.AIProviderUnavailable as exc:
        raise AiRuleError(f"The AI could not interpret the rule: {exc}") from exc
    if not interpretation.spec or not ai_rules.spec_usable(json.loads(interpretation.spec)):
        raise InterpretationInvalid("Non salvata come operativa: l'interpretazione di questo testo non è valida ("
                          f"{interpretation.rejection_reason or 'nessuna forma eseguibile'}). Correggi il testo, "
                          "premi Preview e fai interpretare la regola, poi salva di nuovo."
                          + (" La versione operativa attuale resta invariata." if rule is not None else ""))
    created = rule is None
    if created:
        rule = m.BankAiRule(title=" ".join(rule_text.split())[:200], status="ACTIVE", apply_future=bool(apply_future),
                            origin_transaction_id=origin.id, origin_description=origin.description_original,
                            created_by_account_id=account_id)
        session.add(rule)
        session.flush()
    version = current_version(rule)
    # A new version whenever the text, the option or the interpretation
    # changed: text, version and interpretation always belong together.
    new_version = (version is None or version.rule_text != rule_text
                   or bool(version.create_missing_who) != bool(create_missing_who)
                   or bool(version.override_protected) != bool(override_protected)
                   or version.interpretation_id != interpretation.id)
    if new_version:
        version = m.BankAiRuleVersion(
            rule_id=rule.id, version_no=(version.version_no + 1) if version else 1, rule_text=rule_text,
            create_missing_who=bool(create_missing_who), override_protected=bool(override_protected),
            method=m.AI_RULE_METHOD_CODE if interpretation.spec else m.AI_RULE_METHOD_AI,
            spec=interpretation.spec, interpretation_id=interpretation.id, instructions_snapshot=instructions,
            created_by_account_id=account_id)
        session.add(version)
        rule.title = " ".join(rule_text.split())[:200]
    rule.apply_future = bool(apply_future)
    rule.status = "ACTIVE"
    session.flush()
    session.refresh(rule)
    return SaveResult(rule, current_version(rule), new_version, created)


def remove_draft(session: Session, draft_id: int | None) -> bool:
    """The draft the window was opened from, once its rule is saved as
    operative (BANK_AI_RULES_009): removed from the drafts; previews made from
    it keep their history (their link is emptied, never left dangling)."""
    draft = session.get(m.BankAiRuleDraft, draft_id) if draft_id else None
    if draft is None:
        return False
    for preview in session.scalars(select(m.BankAiRulePreview).where(m.BankAiRulePreview.draft_id == draft.id)):
        preview.draft_id = None
    session.delete(draft)
    session.flush()
    return True


def set_status(session: Session, *, rule_id: int, active: bool) -> "m.BankAiRule":
    rule = session.get(m.BankAiRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise AiRuleError("This rule no longer exists (it was deleted).")
    rule.status = "ACTIVE" if active else "INACTIVE"
    session.flush()
    return rule


# ---------------------------------------------------------------------------
# Writing one decision and creating a WHO
# ---------------------------------------------------------------------------

class _WhoMaker:
    """The WHO a name needs, created once per name by the WHO service
    (existing names and aliases reused through `check_new_who`)."""

    def __init__(self, session: Session):
        self.session = session
        self.ids: dict[str, int] = {}
        self.created: list[str] = []

    def id_for(self, name: str) -> int:
        from . import configuration
        from . import who_rules
        key = ai_rules.normalize_who(name)
        if key in self.ids:
            return self.ids[key]
        existing, clean = who_rules.check_new_who(self.session, key)
        if existing is None:
            existing = configuration.save_who(
                self.session, occurrence_id=None, name=clean, active=True, reason_ids=[], default_reason_id=None,
                reporting_entity_ids=[])
            self.session.flush()
            self.created.append(existing.canonical_name)
        self.ids[key] = existing.id
        return existing.id


def _write(session: Session, txn: "m.FinancialTransaction", current, target: ai_rules.Target, who_id: int | None,
           note: str, *, overriding: bool = False) -> "m.BankTransactionExplanation":
    """One new RULE decision with ONLY the rule's fields changed. A decision
    that overrides a protected one (BANK_AI_RULES_011) is always "Da
    confermare": a rule never leaves a decision looking confirmed."""
    from .who_rules import _PURPOSE_FIELDS
    occurrence_id = who_id if target.who_set else (current.occurrence_id if current is not None else None)
    if target.why_set:
        reason_id = None if target.why_clear else target.why_id
    else:
        reason_id = current.transaction_reason_id if current is not None else None
    if target.to_confirm or overriding:         # "Da confermare" (BANK_AI_RULES_008 / 011)
        status = ai_rules.TO_CONFIRM_DECISION_STATUS
    else:
        status = current.decision_status if current is not None else "NEEDS_HUMAN_REVIEW"
    row = recognition._create_decision_row(
        session, txn, occurrence_id=occurrence_id, transaction_reason_id=reason_id,
        decision_source="RULE",
        decision_status=status,
        confidence=current.confidence if current is not None else None,
        explanation_notes=note,
        accounting_destination_source=(current.accounting_destination_source
                                       if current is not None and not target.why_set else m.DESTINATION_SOURCE_WHY),
    )
    if not target.why_set and current is not None:
        for name in _PURPOSE_FIELDS:            # the WHY is unchanged: so are its WHAT and accounting snapshot
            setattr(row, name, getattr(current, name))
    session.flush()
    return row


def _write_for_whom(session: Session, txn: "m.FinancialTransaction", target: ai_rules.Target, note: str) -> None:
    """For Whom by an AI rule (BANK_AI_RULES_010): ONE pending allocation for
    the whole amount — like the For Whom chosen on Review Transactions, but
    with decision source RULE and notes naming the AI Rule, so its provenance
    is known (automatic). The row's Confirm completes it."""
    economic_allocation.set_allocations(
        session, financial_transaction_id=txn.id,
        specs=[economic_allocation.AllocationSpec(
            amount_minor=txn.amount_minor, reporting_entity_id=target.for_whom_id,
            status=m.ALLOCATION_NEEDS_OPERATOR, decision_source="RULE", decided_by_account_id=None,
            notes=note[:2000])])


def _needs_decision(current, plan: ai_rules.Plan, target: ai_rules.Target) -> bool:
    """A new decision row is written when WHO or WHY change, or when only For
    Whom changes and the decision must become "Da confermare" (and is not)."""
    if "WHO" in plan.changes or "WHY" in plan.changes:
        return True
    return (target.to_confirm and current is not None
            and current.decision_status != ai_rules.TO_CONFIRM_DECISION_STATUS)


def _log_to_verify(application: "m.BankAiRuleApplication", row: ai_rules.Row, ex: "ai_rules.Exec",
                   for_whom: str | None = None) -> None:
    """A match whose every field is "Da verificare": logged, never applied."""
    reasons = "; ".join(r for r in (ex.who_verify, ex.why_verify, ex.for_whom_verify) if r)
    application.items.append(m.BankAiRuleApplicationItem(
        financial_transaction_id=row.id, outcome=ai_rules.UNRESOLVED, who_before=row.current_who,
        why_before=row.current_why, who_after=row.current_who, why_after=row.current_why,
        for_whom_before=for_whom, for_whom_after=for_whom,
        note=f"{ex.to_verify.replace(',', ' and ')} {ai_rules.TO_VERIFY}: {reasons}."[:2000]))
    _count(application, ai_rules.UNRESOLVED)


def _apply_one(session: Session, planner: ai_rules.Planner, row: ai_rules.Row, target: ai_rules.Target, *,
               create_missing_who: bool, maker: _WhoMaker, application: "m.BankAiRuleApplication", note: str,
               to_verify: str | None = None) -> str:
    plan = planner.plan_full(row, target, create_missing_who=create_missing_who)
    outcome, plan_note, who_after, why_after = plan.as_tuple()
    for_whom_after = plan.for_whom_after
    if to_verify:
        plan_note += f" {to_verify.replace(',', ' and ')} {ai_rules.TO_VERIFY}: not assigned."
    explanation_id = None
    if outcome == ai_rules.UPDATED:
        try:
            with session.begin_nested():
                if _needs_decision(row.explanation, plan, target):
                    who_id = maker.id_for(target.who_name) if target.who_set and target.who_new else target.who_id
                    written = target
                    if "WHO" not in plan.changes and "WHY" not in plan.changes:
                        # Only For Whom changes: the decision keeps WHO and WHY
                        # and only becomes "Da confermare".
                        written = dataclasses.replace(target, who_set=False, why_set=False)
                    decision = _write(session, row.txn, row.explanation, written, who_id, f"{note} {plan_note}",
                                      overriding=bool(plan.overridden))
                    explanation_id = decision.id
                if plan.withdraw_acceptance:
                    # The ONE implementation used by Review: a single COMPLETE
                    # allocation becomes pending for the same For Whom.
                    from .row_reconciliation import _withdraw_acceptance
                    _withdraw_acceptance(session, row.txn)
                if "For Whom" in plan.changes:
                    _write_for_whom(session, row.txn, target, f"{note} {plan_note}")
        except Exception as exc:  # noqa: BLE001 — this movement is not changed; logged and counted
            outcome, plan_note, who_after, why_after = "ERROR", f"Not applied: {exc}", row.current_who, row.current_why
            for_whom_after = plan.for_whom_before
    application.items.append(m.BankAiRuleApplicationItem(
        financial_transaction_id=row.id, outcome=outcome, who_before=row.current_who, why_before=row.current_why,
        who_after=who_after, why_after=why_after, for_whom_before=plan.for_whom_before,
        for_whom_after=for_whom_after, explanation_id=explanation_id, note=plan_note[:2000]))
    _count(application, outcome)
    return outcome


_COUNTERS = {ai_rules.UPDATED: "updated", ai_rules.UNCHANGED: "unchanged", ai_rules.PROTECTED: "protected",
             ai_rules.CONFLICT: "conflicts", ai_rules.UNRESOLVED: "unresolved", "ERROR": "errors"}


def _count(application: "m.BankAiRuleApplication", outcome: str) -> None:
    name = _COUNTERS[outcome]
    setattr(application, name, (getattr(application, name) or 0) + 1)


def application_as_dict(application: "m.BankAiRuleApplication") -> dict:
    return dict(
        ok=application.status == "COMPLETED", application_id=application.id, rule_id=application.rule_id,
        mode=application.mode, examined=application.examined, updated=application.updated,
        unchanged=application.unchanged, protected=application.protected, conflicts=application.conflicts,
        unresolved=application.unresolved, errors=application.errors,
        only_unsettled=bool(application.only_unsettled), excluded_ai_settled=application.excluded_ai_settled or 0,
        who_only=bool(application.who_only),
        who_created=json.loads(application.who_created) if application.who_created else [],
        error=application.error_message)


# ---------------------------------------------------------------------------
# Salva e Applica — existing movements
# ---------------------------------------------------------------------------

def already_applied(session: Session, preview_id: int | None) -> str | None:
    """A preview authorizes ONE complete application: a second press (or a
    resent request) never applies it twice. An application left incomplete
    may be completed with the same preview — what it already changed comes
    out unchanged."""
    if not preview_id:
        return None
    done = session.scalar(select(m.BankAiRuleApplication).where(
        m.BankAiRuleApplication.preview_id == preview_id, m.BankAiRuleApplication.status == "COMPLETED",
        m.BankAiRuleApplication.errors == 0).order_by(m.BankAiRuleApplication.id).limit(1))
    if done is None:
        return None
    return (f"Preview #{preview_id} has already been applied (rule #{done.rule_id}, application #{done.id}): "
            "it is never applied twice. To apply the rule again, press Preview first.")


def apply_rule(session: Session, *, rule: "m.BankAiRule", scope: str, selected_ids: list[int] | None,
               preview_id: int | None, account_id: int | None,
               only_unsettled: bool = False, who_only: bool = False) -> "m.BankAiRuleApplication":
    """Apply the rule's current version to ALL in-scope movements or to the
    SELECTED ones, on the strength of a completed preview of the same text,
    scope, selection and option (`AiRuleError` "needs a preview"
    otherwise). The plan is recomputed now, on the current data."""
    version = current_version(rule)
    if version is None or rule.status != "ACTIVE":
        raise AiRuleError("Only an active rule can be applied.")
    if scope not in (ai_rules.SCOPE_ALL, ai_rules.SCOPE_SELECTED):
        raise AiRuleError("Choose “Tutte le transazioni esistenti” or “Solo le transazioni selezionate”.")
    if version.spec and not ai_rules.spec_usable(json.loads(version.spec)):
        raise AiRuleError("This rule's saved interpretation is outdated (it read “Personal” as “owner is a "
                          "Person”): press Salva to interpret it again, then preview and apply.")
    preview = session.get(m.BankAiRulePreview, preview_id) if preview_id else None
    problem = ai_rules.preview_problem(preview, rule_text=version.rule_text, scope=scope, selected_ids=selected_ids,
                                       create_missing_who=version.create_missing_who,
                                       override_protected=bool(version.override_protected),
                                       only_unsettled=only_unsettled, who_only=who_only) \
        or already_applied(session, preview_id)
    if problem:
        raise NeedsPreview(problem)
    # BANK_AI_RULES_009 — the preview must have been made with the very
    # interpretation this version carries (same text AND same instructions).
    preview_info = json.loads(preview.interpretation) if preview.interpretation else {}
    if version.interpretation_id is None or preview_info.get("interpretation_id") != version.interpretation_id:
        raise NeedsPreview("The preview was made with another interpretation of this rule: run Preview again, check "
                           "it, then apply.")
    rows = ai_rules.scope_rows(session, scope=scope, date_from=None, date_to=None, selected_ids=selected_ids)
    # BANK_AI_RULES_013 — the same selection as the preview's, recomputed now.
    rows, excluded_by_rule = ai_rules.without_ai_settled(session, rows, only_unsettled)
    planner = ai_rules.Planner(session, rule_id=rule.id)
    application = m.BankAiRuleApplication(
        rule_id=rule.id, version_id=version.id, mode=MODE_ALL if scope == ai_rules.SCOPE_ALL else MODE_SELECTED,
        preview_id=preview.id, examined=len(rows), updated=0, unchanged=0, protected=0, conflicts=0, unresolved=0,
        errors=0, status="COMPLETED", created_by_account_id=account_id, started_at=datetime.now(timezone.utc),
        only_unsettled=bool(only_unsettled), excluded_ai_settled=sum(excluded_by_rule.values()),
        who_only=bool(who_only))
    session.add(application)
    maker = _WhoMaker(session)
    note = (f"AI Rule #{rule.id} v{version.version_no} applied to existing movements "
            f"({'all' if scope == ai_rules.SCOPE_ALL else 'selected'}) by account {account_id}.")
    if version.spec:
        spec = json.loads(version.spec)
        for row in rows:
            ex = ai_rules.execute(spec, row)
            if who_only:                    # BANK_AI_RULES_018 — the WHO part only
                ex = ai_rules.who_only_exec(ex)
            if ex.outcome != "MATCH":
                continue
            if not ex.assigns:
                if ex.to_verify:
                    _log_to_verify(application, row, ex, planner.for_whom(row.id).name)
                continue
            target = planner.target_of(ex)
            target.override_protected = bool(version.override_protected)
            _apply_one(session, planner, row, target,
                       create_missing_who=version.create_missing_who, maker=maker, application=application,
                       note=note, to_verify=ex.to_verify)
    else:
        # The AI judged each movement in the preview: its certain matches,
        # within the scope, are what is applied (doubtful cases never).
        by_id = {i.financial_transaction_id: i for i in preview.items if i.verdict == ai_rules.MATCH}
        for row in rows:
            item = by_id.get(row.id)
            if item is None:
                continue
            target = planner.target(item.proposed_who_name, item.proposed_why_name)
            target.override_protected = bool(version.override_protected)
            _apply_one(session, planner, row, target,
                       create_missing_who=version.create_missing_who, maker=maker, application=application, note=note)
    application.who_created = json.dumps(maker.created, ensure_ascii=False)
    application.finished_at = datetime.now(timezone.utc)
    rule.last_applied_at = application.finished_at
    session.flush()
    return application



# ---------------------------------------------------------------------------
# Per il futuro — the import step
# ---------------------------------------------------------------------------

class ImportContext:
    """Built once per import pass when at least one ACTIVE rule applies to
    new movements (only rules the code can execute)."""

    def __init__(self, session: Session, entries: list[tuple["m.BankAiRule", "m.BankAiRuleVersion", dict]]):
        self.session = session
        self.entries = entries
        self.builder = ai_rules.RowBuilder(session)
        self.planner = ai_rules.Planner(session, preload=False, other_rules=False)
        self.maker = _WhoMaker(session)
        self.applications: dict[tuple[int, int | None], "m.BankAiRuleApplication"] = {}

    def application(self, rule: "m.BankAiRule", version: "m.BankAiRuleVersion",
                    batch_id: int | None) -> "m.BankAiRuleApplication":
        key = (rule.id, batch_id)
        if key not in self.applications:
            application = m.BankAiRuleApplication(
                rule_id=rule.id, version_id=version.id, mode=MODE_IMPORT, import_batch_id=batch_id, examined=0,
                updated=0, unchanged=0, protected=0, conflicts=0, unresolved=0, errors=0, status="COMPLETED",
                started_at=datetime.now(timezone.utc))
            self.session.add(application)
            self.applications[key] = application
        return self.applications[key]


def import_context(session: Session) -> ImportContext | None:
    entries = []
    for rule in session.scalars(select(m.BankAiRule).where(m.BankAiRule.status == "ACTIVE",
                                                           m.BankAiRule.deleted_at.is_(None),
                                                           m.BankAiRule.apply_future.is_(True))):
        version = current_version(rule)
        spec = json.loads(version.spec) if version is not None and version.spec else None
        if ai_rules.spec_usable(spec):           # an outdated v1 structure is never executed
            entries.append((rule, version, spec))
    return ImportContext(session, entries) if entries else None


def apply_to_new_transaction(session: Session, txn: "m.FinancialTransaction",
                             context: ImportContext | None) -> bool:
    """Every rule for the future is evaluated on the new movement. Rules that
    match with incompatible values are ALL reported as conflicts and none is
    applied; otherwise their assignments are applied once, against the
    decision the earlier import steps made (same protections and conflicts).
    True when a decision was written."""
    if context is None:
        return False
    current = recognition.get_current_explanation(session, financial_transaction_id=txn.id)
    row = context.builder.row(txn, current)
    matched = []
    for rule, version, spec in context.entries:
        ex = ai_rules.execute(spec, row)
        if ex.outcome != "MATCH":
            continue
        if not ex.assigns:
            if ex.to_verify:
                application = context.application(rule, version, txn.import_batch_id)
                application.examined += 1
                _log_to_verify(application, row, ex, context.planner.for_whom(txn.id).name)
            continue
        target = context.planner.target_of(ex)
        target.override_protected = bool(version.override_protected)
        matched.append((rule, version, target))
    if not matched:
        session.flush()
        return False
    for rule, version, _target in matched:
        application = context.application(rule, version, txn.import_batch_id)
        application.examined += 1
    incompatible = []
    for i, (rule_a, _va, a) in enumerate(matched):
        for rule_b, _vb, b in matched[i + 1:]:
            if a.who_set and b.who_set and a.who_key() != b.who_key():
                incompatible.append(f"AI rules #{rule_a.id} and #{rule_b.id} assign different WHO")
            if a.why_set and b.why_set and a.why_key() != b.why_key():
                incompatible.append(f"AI rules #{rule_a.id} and #{rule_b.id} assign different WHY")
            if a.for_whom_set and b.for_whom_set and a.for_whom_id != b.for_whom_id:
                incompatible.append(f"AI rules #{rule_a.id} and #{rule_b.id} assign different For Whom")
    if incompatible:
        note = "Conflict: " + "; ".join(incompatible) + "."
        for_whom = context.planner.for_whom(txn.id).name
        for rule, version, _target in matched:
            application = context.application(rule, version, txn.import_batch_id)
            application.items.append(m.BankAiRuleApplicationItem(
                financial_transaction_id=txn.id, outcome=ai_rules.CONFLICT, who_before=row.current_who,
                why_before=row.current_why, who_after=row.current_who, why_after=row.current_why,
                for_whom_before=for_whom, for_whom_after=for_whom, note=note))
            _count(application, ai_rules.CONFLICT)
        session.flush()
        return False
    merged = ai_rules.Target()
    for _rule, _version, target in matched:
        if target.who_set:
            merged.who_set, merged.who_id, merged.who_name = True, target.who_id, target.who_name
            merged.who_new, merged.who_error = target.who_new, target.who_error
        if target.why_set:
            merged.why_set, merged.why_id, merged.why_name = True, target.why_id, target.why_name
            merged.why_clear, merged.why_note = target.why_clear, target.why_note
        if target.for_whom_set:
            merged.for_whom_set, merged.for_whom_id = True, target.for_whom_id
            merged.for_whom_name = target.for_whom_name
        merged.to_confirm = merged.to_confirm or target.to_confirm
        merged.only_if_who_differs = merged.only_if_who_differs or target.only_if_who_differs
        merged.replace_existing = merged.replace_existing or target.replace_existing
    # Protected values are overridden only when EVERY matching rule allows it.
    merged.override_protected = all(target.override_protected for _r, _v, target in matched)
    create = any(version.create_missing_who for _rule, version, target in matched if target.who_set)
    rule_names = ", ".join(f"#{rule.id} v{version.version_no}" for rule, version, _t in matched)
    first_rule, first_version, _t = matched[0]
    application = context.application(first_rule, first_version, txn.import_batch_id)
    outcome = _apply_one(session, context.planner, row, merged, create_missing_who=create, maker=context.maker,
                         application=application, note=f"AI Rule {rule_names} at import.")
    item = application.items[-1]
    for rule, version, _target in matched[1:]:          # the same outcome, logged for every rule that matched
        other = context.application(rule, version, txn.import_batch_id)
        other.items.append(m.BankAiRuleApplicationItem(
            financial_transaction_id=txn.id, outcome=item.outcome, who_before=item.who_before,
            why_before=item.why_before, who_after=item.who_after, why_after=item.why_after,
            for_whom_before=item.for_whom_before, for_whom_after=item.for_whom_after,
            explanation_id=item.explanation_id, note=item.note))
        _count(other, item.outcome)
    for rule, _version, _target in matched:
        rule.last_applied_at = datetime.now(timezone.utc)
    session.flush()
    return outcome == ai_rules.UPDATED


def finish_import(context: ImportContext | None) -> None:
    """Stamps the end of each import application with the WHO it created."""
    if context is None:
        return
    for application in context.applications.values():
        application.who_created = json.dumps(context.maker.created, ensure_ascii=False)
        application.finished_at = datetime.now(timezone.utc)
    context.session.flush()
