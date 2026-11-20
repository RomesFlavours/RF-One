"""AI-Governed Natural-Language Rule Authoring for Tip Distribution Rules
(`01 Domains/Shared Domains/AI_GOVERNED_RULE_AUTHORING_001.md`, applied to
Tips per that document's §12 — first concrete application of the principle,
which itself defines no UI, provider, schema, or prompt design).

Reuses the existing provider-agnostic `rfone_data_store.selection.parsing.
ai_client.generate_json` abstraction — the same one Selection's résumé
parsing (`llm_parser.py`), Primary Screening AI evaluation
(`primary_screening_ai_evaluator.py`), and Organizational AI review
(`organizational_ai_review_service.py`) already use. No second AI
architecture is introduced.

Human language -> AI interpretation -> clarification only if genuinely
ambiguous -> canonical structured proposal -> human-readable confirmation
-> explicit human approval -> persisted `TipDistributionRuleVersion` via the
EXISTING `distribution_rule_service.create_rule`/`create_new_version`. This
module never writes to the database on interpretation alone, never lets the
AI's own judgment be the final word on what the canonical engine can
compute — every field is re-validated in Python against the exact same
closed vocabularies `distribution_rule_service.py` already enforces
(`TIP_DISTRIBUTION_ENGINE_IMPLEMENTED_CALCULATION_BASES`,
`ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT`, `DISTRIBUTION_METHOD_EQUAL`,
`NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS`, `TRANSACTION_SCOPE_ALL`) before a
proposal is ever shown as confirmable, and again at confirmation time.

Stateless/transport-neutral by design (task §10): `interpret_rule_statement`
takes the latest statement plus the full prior conversation turns as plain
data — never a Flask session, never any web-framework state — so the same
function can be called from a server-rendered form today, and a chat/voice
interface later, unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..selection.parsing import ai_client
from . import distribution_rule_service as rule_svc

UTC = timezone.utc

OUTCOME_CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"
OUTCOME_UNSUPPORTED = "UNSUPPORTED"
OUTCOME_PROPOSED = "PROPOSED"
_VALID_OUTCOMES = (OUTCOME_CLARIFICATION_NEEDED, OUTCOME_UNSUPPORTED, OUTCOME_PROPOSED)


class AIRuleAuthoringUnavailable(Exception):
    """No usable AI interpretation could be produced right now — no
    provider configured, a request failure, or a response that did not
    satisfy the structured-output contract badly enough that no honest
    downgrade to CLARIFICATION_NEEDED/UNSUPPORTED was possible. Callers
    must treat this exactly like the existing `AIProviderUnavailable`/
    `AIEvaluationUnavailable` sentinels: fall back to the existing
    Advanced/manual form, never fabricate an interpretation."""


@dataclass
class ConversationTurn:
    """One prior turn of the authoring conversation. `role` is `"user"` or
    `"assistant"` — plain data, never tied to any request/session object,
    so a caller can round-trip it through a web form's hidden field, a chat
    transcript, or anything else (task §10)."""

    role: str
    content: str


@dataclass
class RuleProposal:
    """Canonical structured proposal — maps ONLY onto fields
    `distribution_rule_service.create_rule`/`create_new_version` already
    accept. Never persisted directly; `confirm_rule_proposal` below is the
    only path from here to the database, and it re-validates every field
    again rather than trusting this object blindly (it may have round-
    tripped through an untrusted client in between)."""

    restaurant_id: int
    restaurant_name: str
    rule_id: int | None  # None => new Rule; set => new Version of an existing Rule
    source_semantics: str  # m.TIP_SOURCE_SEMANTICS_ROLE | m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER
    source_role_id: int | None  # required iff source_semantics == ROLE; None iff ORDER_SERVICE_OWNER
    source_role_name: str  # a Role name iff ROLE; a human label ("Service Owner...") iff ORDER_SERVICE_OWNER
    recipient_role_id: int
    recipient_role_name: str
    calculation_base: str
    rate: str  # canonical decimal string, e.g. "10.0000"
    eligibility_mode: str
    distribution_method: str
    no_eligible_recipient_behavior: str
    transaction_scope: str
    effective_from: str  # ISO date, e.g. "2026-09-01"
    effective_to: str | None
    human_readable_summary: str
    warnings: list[str] = field(default_factory=list)
    confidence: str = "HIGH"


@dataclass
class ClarificationNeeded:
    question: str


@dataclass
class UnsupportedRule:
    unsupported_summary: str
    unsupported_detail: str
    preserved_intent: str


@dataclass
class InterpretationResult:
    outcome: str  # one of _VALID_OUTCOMES
    clarification: ClarificationNeeded | None = None
    unsupported: UnsupportedRule | None = None
    proposal: RuleProposal | None = None


# ---------------------------------------------------------------------------
# Canonical engine boundary — the ONLY thing the AI is allowed to propose,
# stated once here and reused both in the prompt and in validation, so the
# prompt can never silently drift from what is actually enforced.
# ---------------------------------------------------------------------------

_CALCULATION_BASE_MEANINGS = {
    m.CALC_BASE_VOLUNTARY_TIP: (
        "Voluntary tips only — amounts a guest chose to add on a card/electronic payment. "
        "Unrecorded cash tips are already structurally excluded (no source record exists for them). "
        "Any automatic/mandatory Service Charge or gratuity is NOT included."
    ),
    m.CALC_BASE_GRATUITY: (
        "Automatic/mandatory Service Charge or gratuity only (Order-level fees) — voluntary card tips "
        "are NOT included."
    ),
    m.CALC_BASE_TIP_PLUS_GRATUITY: (
        "Voluntary tips AND automatic/mandatory Service Charge/gratuity combined."
    ),
}


def _capability_brief() -> str:
    bases = "\n".join(f"  - {code}: {desc}" for code, desc in _CALCULATION_BASE_MEANINGS.items())
    return f"""This is the ENTIRE set of Tip Distribution behaviors RF-One's Tip Distribution Engine can \
currently compute. Anything outside this list must be reported as UNSUPPORTED — never approximated.

WHAT MONEY IS DISTRIBUTED (pick exactly one, based on what the user described):
{bases}

RECIPIENT ELIGIBILITY (the only supported meaning — always this, never state anything else in the \
proposal): a Recipient Role holder is eligible only if they are assigned to that Role at the exact moment \
the Order's payment settles ("present at payment time" / "present at settlement"). There is no support for \
eligibility based on total hours worked, scheduled-but-not-present, or any other timing.

SPLIT AMONG MULTIPLE ELIGIBLE RECIPIENTS (the only supported meaning): split equally among every eligible \
recipient. There is no support for a weighted, seniority-based, or hours-proportional split.

WHEN NO RECIPIENT IS ELIGIBLE (the only supported meaning): the source (see below) retains the entire \
amount. There is no support for a house pool, a different fallback role, or forfeiting the money some \
other way.

WHICH ORDERS THE RULE APPLIES TO (the only supported meaning): every Order, with no scope narrowing by \
service period, order type, sales channel, day of week, or anything else.

WHO THE SOURCE IS — exactly two supported meanings, and the user's own wording decides which one applies; \
never guess, and never silently map one meaning onto the other:
  - "Service Owner" / "whoever owns the Order" / "the employee who owns the Order" / "the employee \
associated with the Order" (no specific job title named): this is the ORDER_SERVICE_OWNER meaning — \
whichever employee Clover attributed the Order to, REGARDLESS of that employee's own job title/Role \
(a Server, a Team Leader, a Manager, or anyone else who owns an Order all qualify identically). Their \
current RestaurantRole is irrelevant to whether their Order can be a source for this rule.
  - A SPECIFIC named Role stated as the source (e.g. "from the Server," "the Bartender gives up 10%," "any \
Cook who rings in a to-go order"): this is the ROLE meaning — the Order-owning employee must actually hold \
that exact configured Role for the rule to apply to their Order.
If the statement is genuinely ambiguous between the two (rare — most statements clearly say one or the \
other), ask a CLARIFICATION_NEEDED question rather than guessing.

EACH RULE HAS EXACTLY ONE source (ROLE or ORDER_SERVICE_OWNER, never both) and ONE Recipient Role, and ONE \
percentage Rate applied to the Calculation Base above. There is no support for a rule with more than one \
recipient role, a multi-tier split, or a formula beyond a single percentage."""


_OUTPUT_CONTRACT = """Return ONLY one JSON object, no prose, no markdown fences, matching exactly ONE of \
these three shapes:

1) You need ONE more piece of information that is genuinely missing or ambiguous (never ask about \
something the user already stated or that has only one reasonable reading):
{
  "outcome": "CLARIFICATION_NEEDED",
  "question": "<one short, specific question in plain human language>"
}

2) The user is asking for something outside what RF-One's Tip Distribution Engine can compute (see the \
capability list above) — never silently approximate it into something close:
{
  "outcome": "UNSUPPORTED",
  "unsupported_summary": "<one short sentence naming the specific unsupported capability>",
  "unsupported_detail": "<explain exactly what part of the request cannot be represented, and why>",
  "preserved_intent": "<restate, in the user's own terms, what they actually asked for, so nothing is lost>"
}

3) You have everything needed to propose a complete, valid rule:
{
  "outcome": "PROPOSED",
  "proposal": {
    "source_semantics": "ROLE | ORDER_SERVICE_OWNER",
    "source_role_name": "<REQUIRED and must be EXACTLY one of the restaurant's Role names listed above, \
ONLY when source_semantics is ROLE. Omit entirely (or null) when source_semantics is ORDER_SERVICE_OWNER \
— never invent a Role name for it.>",
    "recipient_role_name": "<must be EXACTLY one of the restaurant's Role names listed above>",
    "calculation_base": "VOLUNTARY_TIP | GRATUITY | TIP_PLUS_GRATUITY",
    "rate": "<the Recipient Role's percentage share, as a decimal string, e.g. \\"10.0000\\">",
    "effective_from": "<ISO date YYYY-MM-DD>",
    "effective_to": "<ISO date YYYY-MM-DD, or null if open-ended>",
    "human_readable_summary": "<a few plain-language bullet-point-style sentences describing exactly what \
this rule does, suitable to show the user for confirmation — no field names, no enum values, no ids>",
    "warnings": ["<any non-blocking observation worth the user's attention, or an empty list>"]
  }
}
"""


def _format_roles(roles: list[m.RestaurantRole]) -> str:
    if not roles:
        return "(none configured)"
    return ", ".join(f'"{r.name}"' for r in roles)


def build_prompt(
    *, restaurant_name: str, roles: list[m.RestaurantRole], today: str,
    history: list[ConversationTurn], statement: str,
) -> str:
    conversation = "\n".join(f"{turn.role.upper()}: {turn.content}" for turn in history) if history else "(none yet)"
    return f"""You are RF-One's assistant for Tip Distribution Rule authoring at a restaurant. A restaurant \
operator describes, in plain language, how tips should be split among staff. Your job is to turn that into \
a precise, executable Rule — the operator must never need to know database fields, internal codes, or \
rule ids.

RESTAURANT: {restaurant_name}
TODAY'S DATE: {today}
THIS RESTAURANT'S CONFIGURED ROLES (a Source Role and a Recipient Role must each be chosen from exactly \
this list — never invent a role name that is not here): {_format_roles(roles)}

{_capability_brief()}

CONVERSATION SO FAR:
{conversation}

NEWEST OPERATOR STATEMENT:
{statement}

INSTRUCTIONS
1. If the restaurant has NO configured Roles at all, or the statement's intended Source/Recipient Role \
cannot be matched with confidence to one of the exact names listed above, ask a CLARIFICATION_NEEDED \
question — do not guess a role name.
2. Ask a clarifying question ONLY for something genuinely missing or ambiguous. Do not ask about anything \
already stated, already implied unambiguously, or already fixed by the capability list above.
3. If the request needs a capability outside what is listed above, return UNSUPPORTED — never silently \
substitute the closest supported behavior.
4. Otherwise return a complete PROPOSED rule.

{_OUTPUT_CONTRACT}
"""


# ---------------------------------------------------------------------------
# Response validation — the AI's own claimed outcome is never trusted alone;
# every PROPOSED field is re-checked here against the exact same closed
# vocabularies the canonical engine (and `distribution_rule_service.py`)
# already enforce.
# ---------------------------------------------------------------------------

def _resolve_role_by_name(roles: list[m.RestaurantRole], name: object) -> m.RestaurantRole | None:
    if not isinstance(name, str) or not name.strip():
        return None
    target = name.strip().casefold()
    for role in roles:
        if role.name.casefold() == target:
            return role
    return None


def _parse_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _parse_iso_date(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


# Canonical principle: "AI may interpret user intent. AI must NEVER invent a
# materially required business value." `effective_from` is one such value —
# the canonical `TipDistributionRuleVersion` model requires it (NOT NULL).
# Whether the human actually supplied one is decided HERE, deterministically, from the
# human's own words — never by trusting the AI's own claim that it found
# one, and never by defaulting to "today" ourselves either. Deliberately
# conservative: an ambiguous/relative phrase not covered below (e.g. "next
# month") is treated as NOT specified, so RF-One asks rather than guesses —
# consistent with the same "ask, don't infer" principle for every other
# required field this module already treats as CLARIFICATION_NEEDED before
# a role or a value can be resolved.
_MONTH_NAMES = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_DATE_MENTION_RE = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b"  # ISO: 2026-09-01
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"  # 9/1/2026
    rf"|\b(?:{_MONTH_NAMES})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?\s*\d{{2,4}}?\b"  # September 1, 2026 / Sept 1
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+of\s+(?:{_MONTH_NAMES})\b"  # "1st of September"
    r"|\beffective\s+(?:immediately|today|now|tomorrow)\b"  # explicit relative anchor, human-chosen
    r"|\bstart(?:ing)?\s+(?:immediately|today|now|tomorrow)\b",
    re.IGNORECASE,
)


def _user_text_mentions_a_date(user_authored_text: str) -> bool:
    return bool(_DATE_MENTION_RE.search(user_authored_text or ""))


def _validate_and_build(
    raw: object, *, session: Session, restaurant: m.Restaurant, roles: list[m.RestaurantRole], rule_id: int | None,
    user_authored_text: str,
) -> InterpretationResult:
    if not isinstance(raw, dict):
        raise AIRuleAuthoringUnavailable("AI response was not a JSON object.")

    outcome = raw.get("outcome")
    if outcome not in _VALID_OUTCOMES:
        raise AIRuleAuthoringUnavailable(f"AI response outcome {outcome!r} is not one of {_VALID_OUTCOMES}.")

    if outcome == OUTCOME_CLARIFICATION_NEEDED:
        question = raw.get("question")
        if not isinstance(question, str) or not question.strip():
            raise AIRuleAuthoringUnavailable("AI response is missing a clarification 'question'.")
        return InterpretationResult(
            outcome=OUTCOME_CLARIFICATION_NEEDED, clarification=ClarificationNeeded(question=question.strip()),
        )

    if outcome == OUTCOME_UNSUPPORTED:
        summary = raw.get("unsupported_summary")
        detail = raw.get("unsupported_detail")
        preserved = raw.get("preserved_intent")
        if not all(isinstance(x, str) and x.strip() for x in (summary, detail, preserved)):
            raise AIRuleAuthoringUnavailable("AI response is missing required UNSUPPORTED fields.")
        return InterpretationResult(
            outcome=OUTCOME_UNSUPPORTED,
            unsupported=UnsupportedRule(
                unsupported_summary=summary.strip(), unsupported_detail=detail.strip(),
                preserved_intent=preserved.strip(),
            ),
        )

    # outcome == OUTCOME_PROPOSED
    proposal_raw = raw.get("proposal")
    if not isinstance(proposal_raw, dict):
        raise AIRuleAuthoringUnavailable("AI response is missing the 'proposal' object.")

    source_semantics = proposal_raw.get("source_semantics", m.TIP_SOURCE_SEMANTICS_ROLE)
    if source_semantics not in m.TIP_SOURCE_SEMANTICS:
        raise AIRuleAuthoringUnavailable(
            f"AI response source_semantics {source_semantics!r} is not one of {m.TIP_SOURCE_SEMANTICS}."
        )

    recipient_role = _resolve_role_by_name(roles, proposal_raw.get("recipient_role_name"))

    if source_semantics == m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER:
        # ORDER_SERVICE_OWNER_SOURCE_SEMANTICS_001 — the Order-owning
        # Employee is unconditionally the source; no Role to resolve, and
        # never silently mapped back onto a "Server" Role.
        source_role_id: int | None = None
        source_role_name = "Service Owner (whoever Clover attributed the Order to)"
        if recipient_role is None:
            return InterpretationResult(
                outcome=OUTCOME_CLARIFICATION_NEEDED,
                clarification=ClarificationNeeded(
                    question=(
                        "Which of this Restaurant's configured Roles should be the Recipient Role (who "
                        f"receives the share)? Configured Roles: {_format_roles(roles)}."
                    ),
                ),
            )
    else:
        source_role = _resolve_role_by_name(roles, proposal_raw.get("source_role_name"))
        if source_role is None or recipient_role is None:
            return InterpretationResult(
                outcome=OUTCOME_CLARIFICATION_NEEDED,
                clarification=ClarificationNeeded(
                    question=(
                        "Which of this Restaurant's configured Roles should be the Source Role (whose tips are "
                        "shared) and which should be the Recipient Role (who receives the share)? Configured "
                        f"Roles: {_format_roles(roles)}."
                    ),
                ),
            )
        source_role_id = source_role.id
        source_role_name = source_role.name

    calculation_base = proposal_raw.get("calculation_base")
    if calculation_base not in m.TIP_DISTRIBUTION_ENGINE_IMPLEMENTED_CALCULATION_BASES:
        return InterpretationResult(
            outcome=OUTCOME_UNSUPPORTED,
            unsupported=UnsupportedRule(
                unsupported_summary="This rule's basis for calculating tips is not one the engine can compute.",
                unsupported_detail=(
                    f"RF-One can only compute tip distribution from: "
                    f"{', '.join(_CALCULATION_BASE_MEANINGS)}."
                ),
                preserved_intent=str(proposal_raw.get("human_readable_summary") or "(not restated by the AI)"),
            ),
        )

    eligibility_mode = proposal_raw.get("eligibility_mode", m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT)
    distribution_method = proposal_raw.get("distribution_method", m.DISTRIBUTION_METHOD_EQUAL)
    no_eligible_recipient_behavior = proposal_raw.get(
        "no_eligible_recipient_behavior", m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS,
    )
    transaction_scope = proposal_raw.get("transaction_scope", m.TRANSACTION_SCOPE_ALL)
    unsupported_axis = None
    if eligibility_mode != m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT:
        unsupported_axis = "recipient eligibility timing"
    elif distribution_method != m.DISTRIBUTION_METHOD_EQUAL:
        unsupported_axis = "how the amount is split among multiple eligible recipients"
    elif no_eligible_recipient_behavior != m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS:
        unsupported_axis = "what happens when no recipient is eligible"
    elif transaction_scope != m.TRANSACTION_SCOPE_ALL:
        unsupported_axis = "which Orders the rule applies to"
    if unsupported_axis is not None:
        return InterpretationResult(
            outcome=OUTCOME_UNSUPPORTED,
            unsupported=UnsupportedRule(
                unsupported_summary=f"This rule needs a different {unsupported_axis} than RF-One supports today.",
                unsupported_detail=_capability_brief(),
                preserved_intent=str(proposal_raw.get("human_readable_summary") or "(not restated by the AI)"),
            ),
        )

    rate = _parse_decimal(proposal_raw.get("rate"))
    if rate is None or rate <= 0 or rate > 100:
        raise AIRuleAuthoringUnavailable(f"AI response rate {proposal_raw.get('rate')!r} is not a valid percentage.")

    effective_from = _parse_iso_date(proposal_raw.get("effective_from"))
    if effective_from is None:
        return InterpretationResult(
            outcome=OUTCOME_CLARIFICATION_NEEDED,
            clarification=ClarificationNeeded(question="What date should this Rule take effect from?"),
        )
    # Deterministic gate (never delegated to the AI's own judgment): the AI
    # may have filled `effective_from` with today's date, or any other
    # invented value, when the human never actually specified one. Checked
    # against the human's own words, not against what the AI claims it
    # read there.
    if not _user_text_mentions_a_date(user_authored_text):
        return InterpretationResult(
            outcome=OUTCOME_CLARIFICATION_NEEDED,
            clarification=ClarificationNeeded(question="What effective date should this Rule use?"),
        )
    effective_to = _parse_iso_date(proposal_raw.get("effective_to"))

    summary = proposal_raw.get("human_readable_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise AIRuleAuthoringUnavailable("AI response is missing a human_readable_summary.")

    warnings_raw = proposal_raw.get("warnings")
    warnings = [w for w in warnings_raw if isinstance(w, str) and w.strip()] if isinstance(warnings_raw, list) else []

    return InterpretationResult(
        outcome=OUTCOME_PROPOSED,
        proposal=RuleProposal(
            restaurant_id=restaurant.id, restaurant_name=restaurant.name, rule_id=rule_id,
            source_semantics=source_semantics, source_role_id=source_role_id, source_role_name=source_role_name,
            recipient_role_id=recipient_role.id, recipient_role_name=recipient_role.name,
            calculation_base=calculation_base, rate=str(rate),
            eligibility_mode=eligibility_mode, distribution_method=distribution_method,
            no_eligible_recipient_behavior=no_eligible_recipient_behavior, transaction_scope=transaction_scope,
            effective_from=effective_from, effective_to=effective_to,
            human_readable_summary=summary.strip(), warnings=warnings,
        ),
    )


# ---------------------------------------------------------------------------
# Public entry points.
# ---------------------------------------------------------------------------

def interpret_rule_statement(
    session: Session, *, restaurant_id: int, statement: str,
    history: list[ConversationTurn] | None = None, rule_id: int | None = None,
    today: str | None = None, ai_generate_json_fn=None,
) -> InterpretationResult:
    """The entire natural-language-authoring contract (task §1-§5). Never
    writes to the database. `history` is the full prior conversation (this
    module holds no state of its own — task §10, transport-neutral); pass
    the same list back on every call so multi-turn clarification works.
    `rule_id` is set only when the operator is revising an EXISTING Rule (a
    new Version), never when creating a brand-new one.

    Raises `AIRuleAuthoringUnavailable` if no provider is configured, the
    request failed, or the response could not honestly be interpreted as
    one of the three contractual outcomes — callers must fall back to the
    existing Advanced/manual form, never fabricate a result."""

    restaurant = session.get(m.Restaurant, restaurant_id)
    if restaurant is None:
        raise AIRuleAuthoringUnavailable(f"No Restaurant with id={restaurant_id}.")

    if not statement or not statement.strip():
        return InterpretationResult(
            outcome=OUTCOME_CLARIFICATION_NEEDED,
            clarification=ClarificationNeeded(question="What Tip Distribution Rule would you like to set up?"),
        )

    roles = list(
        session.scalars(
            select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id == restaurant_id).order_by(m.RestaurantRole.name)
        )
    )
    if not roles:
        return InterpretationResult(
            outcome=OUTCOME_CLARIFICATION_NEEDED,
            clarification=ClarificationNeeded(
                question=(
                    "This Restaurant has no configured Roles yet, so I cannot resolve who a Rule applies to. "
                    "Please add the relevant Roles (e.g. the role that serves guests, and the role that would "
                    "receive a tip-out) under Manage Roles first, then describe the Rule again."
                ),
            ),
        )

    generate_json = ai_generate_json_fn or ai_client.generate_json
    today = today or datetime.now(UTC).strftime("%Y-%m-%d")
    prompt = build_prompt(
        restaurant_name=restaurant.name, roles=roles, today=today, history=history or [], statement=statement,
    )

    try:
        raw = generate_json(prompt)
    except ai_client.AIProviderUnavailable as exc:
        raise AIRuleAuthoringUnavailable(str(exc)) from exc
    except Exception as exc:  # a custom ai_generate_json_fn, network layer, etc.
        raise AIRuleAuthoringUnavailable(f"AI rule interpretation call failed: {exc}") from exc

    user_authored_text = " ".join(
        [statement] + [turn.content for turn in (history or []) if turn.role == "user"]
    )
    return _validate_and_build(
        raw, session=session, restaurant=restaurant, roles=roles, rule_id=rule_id,
        user_authored_text=user_authored_text,
    )


def confirm_rule_proposal(
    session: Session, proposal: RuleProposal, *, created_by: str | None = None,
) -> m.TipDistributionRule | m.TipDistributionRuleVersion:
    """The ONLY path from an AI-produced `RuleProposal` to the database —
    called ONLY on explicit human CONFIRM (task §6). Re-validates every
    field from scratch: a `RuleProposal` may have round-tripped through an
    untrusted client (a hidden form field) between being proposed and being
    confirmed, so nothing about it is trusted blindly here, even though
    `interpret_rule_statement` already validated it once. Delegates the
    actual write to the EXISTING `distribution_rule_service.create_rule`/
    `create_new_version` — this module never constructs a
    `TipDistributionRuleVersion` itself, and never touches the retired
    `TipPolicy`/`TipPolicyComponent` legacy tables."""

    if proposal.calculation_base not in m.TIP_DISTRIBUTION_ENGINE_IMPLEMENTED_CALCULATION_BASES:
        raise ValueError(f"Calculation Base {proposal.calculation_base!r} is not implemented by the engine.")
    if proposal.eligibility_mode != m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT:
        raise ValueError(f"Eligibility Mode {proposal.eligibility_mode!r} is not implemented by the engine.")
    if proposal.distribution_method != m.DISTRIBUTION_METHOD_EQUAL:
        raise ValueError(f"Distribution Method {proposal.distribution_method!r} is not implemented by the engine.")
    if proposal.no_eligible_recipient_behavior != m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS:
        raise ValueError(
            f"No-Eligible-Recipient Behavior {proposal.no_eligible_recipient_behavior!r} is not implemented "
            "by the engine."
        )
    if proposal.transaction_scope != m.TRANSACTION_SCOPE_ALL:
        raise ValueError(f"Transaction Scope {proposal.transaction_scope!r} is not implemented by the engine.")
    if proposal.source_semantics not in m.TIP_SOURCE_SEMANTICS:
        raise ValueError(f"source_semantics {proposal.source_semantics!r} is not one of {m.TIP_SOURCE_SEMANTICS}.")
    if proposal.source_semantics == m.TIP_SOURCE_SEMANTICS_ROLE and proposal.source_role_id is None:
        raise ValueError("source_role_id is required when source_semantics='ROLE'.")
    if proposal.source_semantics == m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER and proposal.source_role_id is not None:
        raise ValueError("source_role_id must not be set when source_semantics='ORDER_SERVICE_OWNER'.")

    rate = _parse_decimal(proposal.rate)
    if rate is None or rate <= 0 or rate > 100:
        raise ValueError(f"Rate {proposal.rate!r} is not a valid percentage.")

    effective_from_date = _parse_iso_date(proposal.effective_from)
    if effective_from_date is None:
        raise ValueError(f"Effective From {proposal.effective_from!r} is not a valid ISO date.")
    effective_from = datetime.strptime(effective_from_date, "%Y-%m-%d").replace(tzinfo=UTC)

    effective_to = None
    if proposal.effective_to:
        effective_to_date = _parse_iso_date(proposal.effective_to)
        if effective_to_date is None:
            raise ValueError(f"Effective To {proposal.effective_to!r} is not a valid ISO date.")
        effective_to = datetime.strptime(effective_to_date, "%Y-%m-%d").replace(tzinfo=UTC)

    common_kwargs = dict(
        source_semantics=proposal.source_semantics, source_role_id=proposal.source_role_id,
        recipient_role_id=proposal.recipient_role_id,
        calculation_base=proposal.calculation_base, rate=rate, effective_from=effective_from,
        effective_to=effective_to, created_by=created_by,
        eligibility_mode=proposal.eligibility_mode, distribution_method=proposal.distribution_method,
        no_eligible_recipient_behavior=proposal.no_eligible_recipient_behavior,
        transaction_scope=proposal.transaction_scope,
    )

    if proposal.rule_id is None:
        return rule_svc.create_rule(session, restaurant_id=proposal.restaurant_id, **common_kwargs)
    return rule_svc.create_new_version(session, proposal.rule_id, **common_kwargs)
