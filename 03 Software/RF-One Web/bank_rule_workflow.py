"""Conversational rule decisions, with no separate rule-application workflow."""
import json
from datetime import datetime

from flask import current_app
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules, ai_rule_operations as operations
from rfone_data_store.bank_reconciliation import rule_application_safety as safety

from rfone_data_store.bank_reconciliation import rule_organization as organization

ACTIONS = ("FUTURE", "PAST_AND_FUTURE")


def creates_extracted_who(payload):
    spec = payload["spec"]
    assignments = [spec.get("who")] + [branch.get("who") for branch in spec.get("branches", [])]
    return any((who or {}).get("mode") in ai_rules.WHO_EXTRACTIONS for who in assignments)


def signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="bank-conversation-rule-v1")


def _instructions(db):
    item = ai_rules.current_instruction(db)
    return item.instructions if item and item.instructions else None


def _active_rule(db, rule_id):
    rule = db.get(m.BankAiRule, rule_id) if rule_id else None
    if not rule or rule.deleted_at:
        raise ValueError("The rule is no longer available. Reopen the conversation.")
    return rule


def existing_token(db, rule, account_id):
    version = operations.current_version(rule)
    interpretation = db.get(m.BankAiRuleInterpretation, version.interpretation_id) if version and version.interpretation_id else None
    if not interpretation or version.instructions_snapshot != _instructions(db):
        return None
    try:
        raw = json.loads(interpretation.raw_answer)
        spec, error = ai_rules.validate_interpretation(raw, version.rule_text, entities=ai_rules.EntityCatalog(db))
        if error or spec != json.loads(version.spec):
            return None
    except (ValueError, TypeError):
        return None
    txn = db.get(m.FinancialTransaction, rule.origin_transaction_id)
    decision = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn and txn.explanation_id else None
    return signer().dumps(dict(rule_text=version.rule_text, origin_id=rule.origin_transaction_id,
        raw=raw, spec=spec, instructions=_instructions(db), provider=interpretation.provider,
        model=interpretation.model, engine_version=ai_rules.INTERPRETATION_VERSION,
        who_id=decision.occurrence_id if decision else None, rule_id=rule.id,
        previous_version=version.version_no, previous_future=rule.apply_future, previous_organization_kind=rule.organization_kind, organization_kind=organization.kind(rule, version), account_id=account_id))


def validate_confirmation(db, token, account_id):
    payload = signer().loads(token, max_age=1800)
    if payload.get("account_id") != account_id:
        raise PermissionError("This confirmation belongs to another session.")
    if payload.get("engine_version") != ai_rules.INTERPRETATION_VERSION or payload.get("instructions") != _instructions(db):
        raise ValueError("The instructions changed. Confirm the rule again in the conversation.")
    if payload.get("rule_id"):
        rule = _active_rule(db, payload["rule_id"])
        if (operations.current_version(rule).version_no != payload.get("previous_version") or
                ("previous_future" in payload and rule.apply_future != payload["previous_future"]) or
                ("previous_organization_kind" in payload and rule.organization_kind != payload["previous_organization_kind"])):
            raise ValueError("The rule changed. Reopen it before continuing.")
    if payload.get("capture_state"):
        origin=db.get(m.FinancialTransaction,payload["origin_id"])
        if not origin or safety.snapshot(db,origin)!=payload["capture_state"]:
            raise ValueError("The transaction changed. Create the profile again from its current values.")
    spec, error = ai_rules.validate_interpretation(payload["raw"], payload["rule_text"], entities=ai_rules.EntityCatalog(db))
    if error or spec != payload["spec"]:
        raise ValueError("The rule can no longer be verified. Reopen the conversation.")
    cached = ai_rules.saved_interpretation(db, payload["rule_text"], payload["instructions"])
    if cached and json.loads(cached.spec or "null") != spec:
        raise ValueError("There is a different interpretation. Confirm the rule again.")
    if not cached:
        db.add(m.BankAiRuleInterpretation(cache_key=ai_rules.interpretation_key(payload["rule_text"], payload["instructions"]),
            rule_text=payload["rule_text"], instructions_snapshot=payload["instructions"],
            raw_answer=json.dumps(payload["raw"], ensure_ascii=False), spec=json.dumps(spec, ensure_ascii=False),
            provider=payload["provider"], model=payload["model"]))
        db.flush()
    return payload


def _save(db, payload, account_id, future, override=False):
    previous = _active_rule(db, payload["rule_id"]) if payload.get("rule_id") else None
    if previous is None:
        # A resent confirmation must not create duplicate rules or reverse a later choice.
        duplicate = db.scalar(select(m.BankAiRule).join(m.BankAiRuleVersion).where(
            m.BankAiRule.deleted_at.is_(None), m.BankAiRule.origin_transaction_id == payload["origin_id"],
            m.BankAiRuleVersion.rule_text == payload["rule_text"]))
        if duplicate:
            raise ValueError("This rule already exists. Reopen it from the list to edit or apply it.")
    def no_generation(_):
        raise ai_rules.AiRuleError("Confirm the rule again: its verified interpretation is missing.")
    saved = operations.save_rule(db, rule_id=previous.id if previous else None, rule_text=payload["rule_text"],
        create_missing_who=creates_extracted_who(payload), apply_future=future, origin_transaction_id=payload["origin_id"],
        account_id=account_id, generate=no_generation, override_protected=override,
        user_title=previous.user_title if previous else None)
    saved.rule.organization_kind = payload.get("organization_kind") or organization.inferred_kind(payload["spec"])
    return saved


def decide(db, token, account_id, action, organization_kind=None):
    if action not in ACTIONS:
        raise ValueError("Choose future transactions only, or all existing and future transactions.")
    payload = validate_confirmation(db, token, account_id)
    if organization_kind is not None:
        if organization_kind not in organization.KINDS:
            raise ValueError("Choose a general rule or a recognition profile.")
        payload["organization_kind"] = organization_kind
    token = signer().dumps(payload)
    if action == "PAST_AND_FUTURE":
        # Preview does not save a version or enable future imports. That happens
        # atomically with Apply, after the person has reviewed this exact plan.
        preview = ai_rules.preview_rule(db, rule_text=payload["rule_text"],
            origin_transaction_id=payload["origin_id"], date_from=None, date_to=None,
            scope=ai_rules.SCOPE_ALL, account_id=account_id, ai_rule_id=payload.get("rule_id"),
            create_missing_who=creates_extracted_who(payload), application_mode=safety.UPDATE_ASSIGNED,
            generate=lambda _: (_ for _ in ()).throw(ValueError("Missing interpretation.")))
        result = ai_rules.preview_as_dict(preview)
        result.update(action=action, confirmed_rule=payload["rule_text"],
                      saved_rule_id=payload.get("rule_id"), confirmation_token=token)
        return result
    saved = _save(db, payload, account_id, future=action == "FUTURE")
    return dict(ok=True, action=action, saved_rule_id=saved.rule.id,
                saved_rule_version=saved.version.version_no, apply_future=saved.rule.apply_future,
                confirmation_token=existing_token(db, saved.rule, account_id), rule_text=payload["rule_text"])


def apply_past(db, token, account_id, preview_id):
    safety.lock_writes(db)
    payload = validate_confirmation(db, token, account_id)
    preview = db.get(m.BankAiRulePreview, preview_id) if preview_id else None
    problem = ai_rules.preview_problem(preview, rule_text=payload["rule_text"], scope=ai_rules.SCOPE_ALL,
        selected_ids=[], create_missing_who=creates_extracted_who(payload), override_protected=True,
        application_mode=safety.UPDATE_ASSIGNED) or operations.already_applied(db, preview_id)
    if problem:
        raise operations.NeedsPreview(problem)
    saved = _save(db, payload, account_id, future=True, override=True)
    application = operations.apply_rule(db, rule=saved.rule, scope=ai_rules.SCOPE_ALL,
        selected_ids=[], preview_id=preview_id, account_id=account_id, application_mode=safety.UPDATE_ASSIGNED)
    if application.errors:
        raise ValueError("Some transactions could not be updated. No changes were saved. Review the preview.")
    return dict(ok=True, saved_rule_id=saved.rule.id,
        saved_rule_version=saved.version.version_no, apply_future=True,
        application=operations.application_as_dict(application),
        confirmation_token=existing_token(db, saved.rule, account_id))


def context(db, account_id, *, rule_id=None, transaction_id=None, who_id=None):
    rule = _active_rule(db, rule_id) if rule_id else None
    txn = db.get(m.FinancialTransaction, transaction_id) if transaction_id else None
    if transaction_id and not txn:
        raise ValueError("The transaction no longer exists.")
    if not txn and rule:
        txn = db.get(m.FinancialTransaction, rule.origin_transaction_id)
    if not txn and who_id:
        txn = db.scalar(select(m.FinancialTransaction).join(m.BankTransactionExplanation,
            m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id).where(
            m.BankTransactionExplanation.occurrence_id == who_id).order_by(m.FinancialTransaction.id.desc()))
    explanation = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn and txn.explanation_id else None
    who = db.get(m.BankOccurrence, explanation.occurrence_id) if explanation and explanation.occurrence_id else (db.get(m.BankOccurrence, who_id) if who_id else None)
    related = []
    if txn and not rule:
        row = ai_rules.row_for(db, txn.id)
        for candidate in operations.rules(db):
            version = operations.current_version(candidate)
            if candidate.status != "ACTIVE" or not version or not version.spec or not row:
                continue
            spec = json.loads(version.spec)
            if ai_rules.spec_usable(spec) and ai_rules.execute(spec, row).outcome == "MATCH":
                related.append(dict(id=candidate.id, title=candidate.user_title or candidate.title,
                                    text=version.rule_text))
        if len(related) == 1:
            rule = _active_rule(db, related[0]["id"])
    version = operations.current_version(rule) if rule else None
    title = (rule.user_title or rule.title) if rule else (who.canonical_name if who else "New instruction")
    key = f"rule-{rule.id}" if rule else f"transaction-{txn.id}" if txn else "new-rule"
    return dict(ok=True, id=key, who=title, who_id=who.id if who else None,
        transaction_id=txn.id if txn else None, rule_id=rule.id if rule else None,
        organization_kind=organization.kind(rule, version) if rule else "RECOGNITION",
        rule_text=version.rule_text if version else None, rule_version=version.version_no if version else None, apply_future=rule.apply_future if rule else False,
        confirmation_token=existing_token(db, rule, account_id) if rule else None, related_rules=related,
        question="How should these transactions be handled?",
        context=(f"{txn.posting_date} · {txn.amount_minor/100:.2f} USD · {txn.description_original}" if txn else
                 "Explain the criteria, conditions and exceptions to follow."))
