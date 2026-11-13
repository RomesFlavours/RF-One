"""Automated synthetic tests for AI-Governed Natural-Language Rule
Authoring applied to Tip Distribution Rules
(`01 Domains/Shared Domains/AI_GOVERNED_RULE_AUTHORING_001.md` §12).

Mirrors `tips_distribution_rule_validation.py`'s pattern: builds a synthetic
(never-real) fixture inside one transaction, exercises
`tips.rule_ai_authoring`, asserts the required behaviors, and always rolls
back — no synthetic row is ever left in the target database.

The real `ai_client.generate_json` is never called here — every scenario
injects a canned/failing `ai_generate_json_fn`, exactly the same test seam
`primary_screening_service.py`'s own tests already use for its AI evaluator,
so these checks run without any AI provider credentials configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips import distribution_rule_service as rule_svc
from .tips import rule_ai_authoring as ai_svc

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _build_fixture_and_assert(session, result)
        finally:
            session.rollback()
    return result


def _fake_ai(response: dict):
    def _fn(prompt: str) -> dict:
        return response
    return _fn


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    restaurant = m.Restaurant(name="Synthetic AI Rule Authoring Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()

    server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
    session.add_all([server, host])
    session.flush()

    # =====================================================================
    # Scenario A — fully specified rule: no unnecessary clarification,
    # correct structured proposal, nothing persisted before confirmation.
    # =====================================================================
    fully_specified_ai_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server",
            "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP",
            "rate": "10.0000",
            "effective_from": "2026-09-01",
            "effective_to": None,
            "human_readable_summary": (
                "10% of voluntary tips goes to the Host present when payment is made; the remaining 90% "
                "stays with the Server. If no Host is present, the Server keeps 100%. Effective 2026-09-01."
            ),
            "warnings": [],
        },
    }
    rule_count_before = len(rule_svc.list_rules(session, restaurant.id))
    result_a = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement=(
            "For this restaurant, give 10% of tips to Hosts present at payment time and leave the "
            "remaining 90% with the Server. If no Host is present, Server keeps everything. Split equally "
            "between multiple Hosts. Effective September 1, 2026."
        ),
        ai_generate_json_fn=_fake_ai(fully_specified_ai_response),
    )
    result.check("A: fully specified statement produces PROPOSED (no unnecessary clarification)", result_a.outcome == ai_svc.OUTCOME_PROPOSED)
    result.check("A: proposal resolves Source Role to Server", result_a.proposal is not None and result_a.proposal.source_role_id == server.id)
    result.check("A: proposal resolves Recipient Role to Host", result_a.proposal is not None and result_a.proposal.recipient_role_id == host.id)
    result.check("A: proposal rate is 10.0000", result_a.proposal is not None and result_a.proposal.rate == "10.0000")
    result.check("A: proposal calculation_base is VOLUNTARY_TIP", result_a.proposal is not None and result_a.proposal.calculation_base == "VOLUNTARY_TIP")
    result.check("A: proposal effective_from is 2026-09-01", result_a.proposal is not None and result_a.proposal.effective_from == "2026-09-01")
    result.check(
        "A: nothing persisted before confirmation",
        len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before,
    )

    # =====================================================================
    # Scenario B — missing effective date: asks only for the effective date.
    # =====================================================================
    missing_date_ai_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server",
            "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP",
            "rate": "10.0000",
            "effective_from": None,
            "effective_to": None,
            "human_readable_summary": "10% of voluntary tips goes to the Host present at payment time.",
            "warnings": [],
        },
    }
    result_b = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement="Give 10% of tips to the Host present at payment time, rest stays with the Server.",
        ai_generate_json_fn=_fake_ai(missing_date_ai_response),
    )
    result.check("B: missing effective date asks for clarification", result_b.outcome == ai_svc.OUTCOME_CLARIFICATION_NEEDED)
    result.check(
        "B: clarification question is specifically about the effective date",
        result_b.clarification is not None and "effect" in result_b.clarification.question.lower(),
    )

    # =====================================================================
    # Scenario C — ambiguous/unresolvable role: clarification.
    # =====================================================================
    ambiguous_role_ai_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Service Owner",  # not an exact configured Role name
            "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP",
            "rate": "10.0000",
            "effective_from": "2026-09-01",
            "effective_to": None,
            "human_readable_summary": "10% to Host, 90% to Service Owner.",
            "warnings": [],
        },
    }
    result_c = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement="Give 10% of tips to the Host, the Service Owner keeps the rest.",
        ai_generate_json_fn=_fake_ai(ambiguous_role_ai_response),
    )
    result.check("C: unresolvable role name asks for clarification", result_c.outcome == ai_svc.OUTCOME_CLARIFICATION_NEEDED)

    # =====================================================================
    # Scenario D — unsupported semantics: explicit unsupported response, no
    # silent approximation, nothing persisted.
    # =====================================================================
    unsupported_ai_response = {
        "outcome": "UNSUPPORTED",
        "unsupported_summary": "Weighted-by-hours splitting among multiple Hosts is not supported.",
        "unsupported_detail": "RF-One can only split equally among eligible Hosts today, never by hours worked.",
        "preserved_intent": "Split the Host share proportionally to hours worked by each eligible Host.",
    }
    rule_count_before_d = len(rule_svc.list_rules(session, restaurant.id))
    result_d = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement="Split the Host share proportionally to hours worked by each eligible Host.",
        ai_generate_json_fn=_fake_ai(unsupported_ai_response),
    )
    result.check("D: unsupported semantics returns explicit UNSUPPORTED outcome", result_d.outcome == ai_svc.OUTCOME_UNSUPPORTED)
    result.check(
        "D: unsupported response preserves the user's original intent",
        result_d.unsupported is not None and "hours" in result_d.unsupported.preserved_intent.lower(),
    )
    result.check(
        "D: nothing persisted for an unsupported request",
        len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before_d,
    )

    # Defense-in-depth: the engine boundary is also re-checked in Python
    # even when the AI itself claims PROPOSED with an out-of-contract value
    # (never trust the AI's own gating alone).
    defiant_ai_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server",
            "recipient_role_name": "Host",
            "calculation_base": "TOTAL_SALES",  # storable, but NOT engine-implemented
            "rate": "10.0000",
            "effective_from": "2026-09-01",
            "effective_to": None,
            "human_readable_summary": "10% of total sales goes to the Host.",
            "warnings": [],
        },
    }
    result_d2 = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id, statement="10% of total sales goes to the Host.",
        ai_generate_json_fn=_fake_ai(defiant_ai_response),
    )
    result.check(
        "D2: a calculation base outside the engine-implemented set is downgraded to UNSUPPORTED even if the AI said PROPOSED",
        result_d2.outcome == ai_svc.OUTCOME_UNSUPPORTED,
    )

    # =====================================================================
    # Scenario E — confirmation creates the correct RuleVersion.
    # =====================================================================
    assert result_a.proposal is not None
    created = ai_svc.confirm_rule_proposal(session, result_a.proposal, created_by="ai-authoring-test")
    session.flush()
    result.check("E: confirmation creates exactly one new Rule", len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before + 1)
    versions = rule_svc.list_versions(session, created.id)
    result.check("E: created Rule has exactly one Version", len(versions) == 1)
    v = versions[0]
    result.check("E: persisted Version has the correct Source Role", v.source_role_id == server.id)
    result.check("E: persisted Version has the correct Recipient Role", v.recipient_role_id == host.id)
    result.check("E: persisted Version has the correct rate", v.rate == Decimal("10.0000"))
    result.check("E: persisted Version has the correct calculation_base", v.calculation_base == "VOLUNTARY_TIP")
    result.check("E: persisted Version has the correct eligibility_mode", v.eligibility_mode == m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT)
    result.check("E: persisted Version has the correct distribution_method", v.distribution_method == m.DISTRIBUTION_METHOD_EQUAL)
    result.check(
        "E: persisted Version has the correct no_eligible_recipient_behavior",
        v.no_eligible_recipient_behavior == m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS,
    )
    result.check("E: persisted Version has the correct transaction_scope", v.transaction_scope == m.TRANSACTION_SCOPE_ALL)
    result.check("E: persisted Version records the confirming actor", v.created_by == "ai-authoring-test")

    # =====================================================================
    # Scenario F — change before confirmation: a revised proposal, the
    # original (rejected) proposal is never persisted.
    # =====================================================================
    rule_count_before_f = len(rule_svc.list_rules(session, restaurant.id))
    original_proposal_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server", "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000",
            "effective_from": "2026-10-01", "effective_to": None,
            "human_readable_summary": "10% to Host, 90% to Server, effective 2026-10-01.", "warnings": [],
        },
    }
    result_f1 = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id, statement="10% to Host, effective October 1st 2026.",
        ai_generate_json_fn=_fake_ai(original_proposal_response),
    )
    result.check("F: original proposal is produced first", result_f1.outcome == ai_svc.OUTCOME_PROPOSED)

    revised_proposal_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server", "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP", "rate": "15.0000",  # revised rate
            "effective_from": "2026-10-01", "effective_to": None,
            "human_readable_summary": "15% to Host, 85% to Server, effective 2026-10-01.", "warnings": [],
        },
    }
    history_after_first_proposal = [
        ai_svc.ConversationTurn(role="user", content="10% to Host, effective October 1st 2026."),
        ai_svc.ConversationTurn(role="assistant", content=result_f1.proposal.human_readable_summary),
    ]
    result_f2 = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id, statement="Actually make it 15%, not 10%.",
        history=history_after_first_proposal, ai_generate_json_fn=_fake_ai(revised_proposal_response),
    )
    result.check("F: revision produces an updated proposal", result_f2.outcome == ai_svc.OUTCOME_PROPOSED)
    result.check("F: revised proposal reflects the new rate", result_f2.proposal is not None and result_f2.proposal.rate == "15.0000")
    result.check(
        "F: neither the original nor the revised proposal is persisted merely by being interpreted",
        len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before_f,
    )

    # =====================================================================
    # Scenario G — cancel: nothing persisted. (The web layer's Cancel route
    # is a stateless discard — modeled here as simply never calling
    # `confirm_rule_proposal` for a produced proposal.)
    # =====================================================================
    rule_count_before_g = len(rule_svc.list_rules(session, restaurant.id))
    result_g = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id, statement="20% to Host, effective 2026-11-01.",
        ai_generate_json_fn=_fake_ai({
            "outcome": "PROPOSED",
            "proposal": {
                "source_role_name": "Server", "recipient_role_name": "Host",
                "calculation_base": "VOLUNTARY_TIP", "rate": "20.0000",
                "effective_from": "2026-11-01", "effective_to": None,
                "human_readable_summary": "20% to Host, effective 2026-11-01.", "warnings": [],
            },
        }),
    )
    result.check("G: a proposal was produced to be cancelled", result_g.outcome == ai_svc.OUTCOME_PROPOSED)
    # Cancel == never confirmed.
    result.check(
        "G: an un-confirmed (cancelled) proposal leaves no trace in the database",
        len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before_g,
    )

    # =====================================================================
    # No roles configured at all — deterministic clarification, no AI call.
    # =====================================================================
    bare_restaurant = m.Restaurant(name="Synthetic AI Rule Authoring Test Restaurant (no roles)", default_currency="USD")
    session.add(bare_restaurant)
    session.flush()

    def _fail_if_called(prompt: str) -> dict:
        raise AssertionError("AI must not be called when no Roles are configured yet.")

    result_no_roles = ai_svc.interpret_rule_statement(
        session, restaurant_id=bare_restaurant.id, statement="Give 10% of tips to the Host.",
        ai_generate_json_fn=_fail_if_called,
    )
    result.check(
        "No Roles configured: deterministic clarification without ever calling the AI",
        result_no_roles.outcome == ai_svc.OUTCOME_CLARIFICATION_NEEDED,
    )

    # =====================================================================
    # AI provider unavailable: raises the documented sentinel, never
    # fabricates a result.
    # =====================================================================
    def _raise_unavailable(prompt: str) -> dict:
        raise ai_svc.ai_client.AIProviderUnavailable("no provider configured")

    try:
        ai_svc.interpret_rule_statement(
            session, restaurant_id=restaurant.id, statement="Give 10% of tips to the Host.",
            ai_generate_json_fn=_raise_unavailable,
        )
        result.check("AIProviderUnavailable propagates as AIRuleAuthoringUnavailable", False)
    except ai_svc.AIRuleAuthoringUnavailable:
        result.check("AIProviderUnavailable propagates as AIRuleAuthoringUnavailable", True)

    # =====================================================================
    # confirm_rule_proposal re-validates from scratch — a tampered proposal
    # claiming an unsupported capability is refused even at confirm time.
    # =====================================================================
    tampered = ai_svc.RuleProposal(
        restaurant_id=restaurant.id, restaurant_name=restaurant.name, rule_id=None,
        source_semantics=m.TIP_SOURCE_SEMANTICS_ROLE,
        source_role_id=server.id, source_role_name="Server", recipient_role_id=host.id, recipient_role_name="Host",
        calculation_base="TOTAL_SALES", rate="10.0000", eligibility_mode=m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT,
        distribution_method=m.DISTRIBUTION_METHOD_EQUAL, no_eligible_recipient_behavior=m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS,
        transaction_scope=m.TRANSACTION_SCOPE_ALL, effective_from="2026-09-01", effective_to=None,
        human_readable_summary="tampered",
    )
    try:
        ai_svc.confirm_rule_proposal(session, tampered)
        result.check("confirm_rule_proposal refuses an unsupported calculation_base even if presented directly", False)
    except ValueError:
        result.check("confirm_rule_proposal refuses an unsupported calculation_base even if presented directly", True)

    # =====================================================================
    # RULE_AUTHORING_EFFECTIVE_DATE_001 — the AI must never invent
    # `effective_from`; a deterministic Python gate downgrades to
    # CLARIFICATION_NEEDED whenever the human's own words never mentioned a
    # date, regardless of what the AI's response claims.
    # =====================================================================
    rule_count_before_date_gate = len(rule_svc.list_rules(session, restaurant.id))

    # --- Task-A: missing effective date -> clarification required, no
    # confirmable proposal, nothing persisted -----------------------------
    ai_invents_today_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server", "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000",
            "effective_from": "2026-09-19", "effective_to": None,  # the AI inventing "today"
            "human_readable_summary": "10% to Host, 90% to Server.", "warnings": [],
        },
    }
    result_date_a = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement=(
            "For Winter Park, 10% of each voluntary tip goes to the Host working at the time the payment is "
            "made. The remaining 90% stays with the Server who owns the Order. If no Host is working at that "
            "time, the Server keeps 100% of the tip. If more than one Host is working, divide the Host share "
            "equally among the eligible Hosts. Service Charges are not Tips and must remain separate. Cash "
            "tips are excluded because RF-One cannot observe them."
        ),
        ai_generate_json_fn=_fake_ai(ai_invents_today_response),
    )
    result.check(
        "Date-Task-A: missing effective date is CLARIFICATION_NEEDED even though the AI proposed one",
        result_date_a.outcome == ai_svc.OUTCOME_CLARIFICATION_NEEDED,
    )
    result.check(
        "Date-Task-A: clarification asks specifically about the effective date",
        result_date_a.clarification is not None and "effective date" in result_date_a.clarification.question.lower(),
    )
    result.check(
        "Date-Task-A: nothing persisted",
        len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before_date_gate,
    )

    # --- Task-B: explicit effective date -> proposal contains it, no
    # clarification for date ------------------------------------------------
    explicit_date_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server", "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000",
            "effective_from": "2026-09-01", "effective_to": None,
            "human_readable_summary": "10% to Host, 90% to Server. Effective September 1, 2026.", "warnings": [],
        },
    }
    result_date_b = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement="10% of tips to the Host present at payment time, rest to the Server. Effective September 1, 2026.",
        ai_generate_json_fn=_fake_ai(explicit_date_response),
    )
    result.check("Date-Task-B: explicit effective date produces PROPOSED, not a clarification", result_date_b.outcome == ai_svc.OUTCOME_PROPOSED)
    result.check(
        "Date-Task-B: proposal's effective_from is exactly 2026-09-01",
        result_date_b.proposal is not None and result_date_b.proposal.effective_from == "2026-09-01",
    )

    # --- Task-C: clarification answer -> proposal becomes valid, original
    # Rule semantics preserved ----------------------------------------------
    result_date_c1 = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement="10% of tips to the Host present at payment time, rest stays with the Server.",
        ai_generate_json_fn=_fake_ai({
            "outcome": "PROPOSED",
            "proposal": {
                "source_role_name": "Server", "recipient_role_name": "Host",
                "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000",
                "effective_from": "2026-09-19", "effective_to": None,  # AI still must not win without a human date
                "human_readable_summary": "10% to Host, 90% to Server.", "warnings": [],
            },
        }),
    )
    result.check("Date-Task-C: initial statement (no date) is CLARIFICATION_NEEDED", result_date_c1.outcome == ai_svc.OUTCOME_CLARIFICATION_NEEDED)

    date_c_history = [
        ai_svc.ConversationTurn(role="user", content="10% of tips to the Host present at payment time, rest stays with the Server."),
        ai_svc.ConversationTurn(role="assistant", content=result_date_c1.clarification.question),
    ]
    result_date_c2 = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id, statement="September 1, 2026.", history=date_c_history,
        ai_generate_json_fn=_fake_ai({
            "outcome": "PROPOSED",
            "proposal": {
                "source_role_name": "Server", "recipient_role_name": "Host",
                "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000",
                "effective_from": "2026-09-01", "effective_to": None,
                "human_readable_summary": "10% to Host, 90% to Server. Effective 2026-09-01.", "warnings": [],
            },
        }),
    )
    result.check("Date-Task-C: answering with a real date produces PROPOSED", result_date_c2.outcome == ai_svc.OUTCOME_PROPOSED)
    result.check(
        "Date-Task-C: the proposal uses the human-supplied date, not the earlier AI-invented one",
        result_date_c2.proposal is not None and result_date_c2.proposal.effective_from == "2026-09-01",
    )
    result.check(
        "Date-Task-C: original Rule semantics (roles, rate, calculation base) are preserved",
        result_date_c2.proposal is not None
        and result_date_c2.proposal.source_role_id == server.id
        and result_date_c2.proposal.recipient_role_id == host.id
        and result_date_c2.proposal.rate == "10.0000"
        and result_date_c2.proposal.calculation_base == "VOLUNTARY_TIP",
    )

    # --- Task-D: AI attempts to invent a date the user never supplied ------
    # (same scenario as Task-A, asserted from the "AI defiance" angle: the
    # deterministic gate rejects/downgrades regardless of what the AI put
    # in `effective_from`, including a plausible-looking real calendar date
    # that simply was never mentioned by the human.)
    ai_invents_plausible_date_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_role_name": "Server", "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000",
            "effective_from": "2026-10-15", "effective_to": None,  # invented; never mentioned by the human
            "human_readable_summary": "10% to Host, 90% to Server.", "warnings": [],
        },
    }
    result_date_d = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement="10% of tips to the Host present at payment time, rest to the Server.",
        ai_generate_json_fn=_fake_ai(ai_invents_plausible_date_response),
    )
    result.check(
        "Date-Task-D: an AI-invented (never-mentioned) date is rejected/downgraded to clarification",
        result_date_d.outcome == ai_svc.OUTCOME_CLARIFICATION_NEEDED,
    )
    result.check(
        "Date-Task-D: nothing persisted for an AI-invented date",
        len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before_date_gate,
    )
