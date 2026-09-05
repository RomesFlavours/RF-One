"""Sample Requirement Templates for the Restaurant Industry Extension
(Task 3A §9/§10). This is DATA, not Selection logic —
`requirements_service.py`/`core/requirement_model.py` have no knowledge
this module exists and never import it; seeding is optional and explicit
(`seed_sample_templates`, called the same way `03 Software/Selection/
app.py`'s `_bootstrap_restaurant` seeds its one Restaurant row).

Proves task §9 ("multiple templates for the SAME nominal role") with three
differently styled SERVER templates, plus one management-role template — a
small, representative set, not a full catalog (task's own instruction).

Rome's Flavours' specific hiring philosophy (§10 — teamwork/listening/
humility/absence of counter-dependent behavior) is deliberately NOT a
template here: it is one restaurant's own philosophy, not a reusable
starting point for others. `seed_romes_flavours_requirement_set` clones a
generic template and then adds those traits as ordinary Requirement rows on
THAT restaurant's own Requirement Set — proving the clone-then-customize
flow, never encoding Rome's Flavours into universal RF-One behavior.

Task 3C extends this file with `seed_sample_signal_definitions()` and
`seed_default_review_priority_policy()` — same rule: these are DATA seeded
per-restaurant, never imported by `signal_service.py`/`core/signal_model.py`
(the universal Signal framework), exactly like the Requirement templates
above.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import models as m
from .. import in_person_interview_service as ip_svc
from .. import outcome_service as outcome_svc
from .. import phone_interview_service as pi_svc
from .. import primary_screening_service as ps_svc
from .. import queue_service as queue_svc
from .. import requirements_service as svc
from .. import signal_service as sig_svc
from ..core import fit_assessment_model as fam
from ..core import in_person_interview_model as ipm
from ..core import outcome_model as om
from ..core import phone_interview_model as pim
from ..core import primary_screening_model as psm
from ..core import requirement_model as rm
from ..core import signal_model as sm


def seed_sample_templates(session: Session) -> dict[str, int]:
    """Idempotent (matches by template name) — creates a small,
    representative set of templates if they do not already exist. Returns
    {template_name: template_id} for every template, old or new."""

    existing = {t.name: t.id for t in session.scalars(select(m.RequirementTemplate)).all()}
    result: dict[str, int] = dict(existing)

    def _new(name: str, **kwargs) -> int:
        template = svc.create_template(session, name=name, **kwargs)
        result[name] = template.id
        return template.id

    if "High-Touch Hospitality Server" not in existing:
        tid = _new(
            "High-Touch Hospitality Server", intended_role="SERVER",
            description="Upscale/attentive service style — guest relationship and polish weighted heavily.",
        )
        svc.add_template_item(
            session, tid, name="Guest-first attitude", category="Customer Orientation",
            criticality=rm.MUST_HAVE, trainability=rm.PARTIALLY_TRAINABLE,
            assessment_stages=[rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW],
            evidence_positive="Describes anticipating guest needs, personalizing service.",
            evidence_insufficient="A generic 'I like helping people' with no specific example.",
            display_order=0,
        )
        svc.add_template_item(
            session, tid, name="Wine/menu knowledge", category="Technical Knowledge",
            criticality=rm.PREFERRED, trainability=rm.TRAINABLE,
            assessment_stages=[rm.RESUME, rm.PRACTICAL_ASSESSMENT], display_order=1,
        )
        svc.add_template_item(
            session, tid, name="Poise under pressure", category="Attitude / Behavioral Traits",
            criticality=rm.MUST_HAVE, trainability=rm.NOT_TRAINABLE,
            assessment_stages=[rm.IN_PERSON_INTERVIEW], display_order=2,
        )

    if "High-Volume Server" not in existing:
        tid = _new(
            "High-Volume Server", intended_role="SERVER",
            description="Fast-paced, high-table-count service style — speed and stamina weighted heavily.",
        )
        svc.add_template_item(
            session, tid, name="Works quickly under volume", category="Role Skills",
            criticality=rm.MUST_HAVE, trainability=rm.PARTIALLY_TRAINABLE,
            assessment_stages=[rm.RESUME, rm.PHONE_INTERVIEW], display_order=0,
        )
        svc.add_template_item(
            session, tid, name="POS/ordering system familiarity", category="Technical Knowledge",
            criticality=rm.PREFERRED, trainability=rm.TRAINABLE,
            assessment_stages=[rm.PRACTICAL_ASSESSMENT], display_order=1,
        )
        svc.add_template_item(
            session, tid, name="Team player during rush", category="Teamwork",
            criticality=rm.MUST_HAVE, trainability=rm.NOT_TRAINABLE,
            assessment_stages=[rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW], display_order=2,
        )

    if "Sales-Oriented Server" not in existing:
        tid = _new(
            "Sales-Oriented Server", intended_role="SERVER",
            description="Upsell/check-average-focused service style.",
        )
        svc.add_template_item(
            session, tid, name="Upsell track record", category="Sales",
            criticality=rm.PREFERRED, trainability=rm.TRAINABLE,
            assessment_stages=[rm.RESUME, rm.PHONE_INTERVIEW], display_order=0,
        )
        svc.add_template_item(
            session, tid, name="Confident communication", category="Communication",
            criticality=rm.MUST_HAVE, trainability=rm.PARTIALLY_TRAINABLE,
            assessment_stages=[rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW], display_order=1,
        )

    if "Restaurant Assistant General Manager" not in existing:
        tid = _new(
            "Restaurant Assistant General Manager", intended_role="ASSISTANT_GENERAL_MANAGER",
            description="Floor leadership + operational support for the General Manager.",
        )
        svc.add_template_item(
            session, tid, name="Prior FOH supervisory experience", category="Experience",
            criticality=rm.MUST_HAVE, trainability=rm.NOT_TRAINABLE,
            assessment_stages=[rm.RESUME, rm.PHONE_INTERVIEW], display_order=0,
        )
        svc.add_template_item(
            session, tid, name="Scheduling/labor cost awareness", category="Technical Knowledge",
            criticality=rm.PREFERRED, trainability=rm.TRAINABLE,
            assessment_stages=[rm.IN_PERSON_INTERVIEW], display_order=1,
        )
        svc.add_template_item(
            session, tid, name="Food handler certification", category="Certifications / Legal Requirements",
            criticality=rm.MUST_HAVE, trainability=rm.TRAINABILITY_UNKNOWN,
            assessment_stages=[rm.RESUME, rm.REFERENCE_CHECK], display_order=2,
        )

    session.commit()
    return result


def seed_romes_flavours_requirement_set(session: Session, *, restaurant_id: int) -> int:
    """Demonstrates the clone-then-customize flow (task §11), using Rome's
    Flavours as ONE example restaurant (task §10) — its non-negotiable
    attitude traits are added here as ordinary Requirement rows on ITS OWN
    Requirement Set, exactly as any restaurant would customize a cloned
    template, never as universal Selection logic. Idempotent."""

    existing = session.scalars(
        select(m.RequirementSet).where(
            m.RequirementSet.restaurant_id == restaurant_id,
            m.RequirementSet.name == "Server - Rome's Flavours",
        )
    ).first()
    if existing:
        return existing.id

    templates = seed_sample_templates(session)
    requirement_set = svc.instantiate_requirement_set_from_template(
        session, template_id=templates["High-Touch Hospitality Server"], restaurant_id=restaurant_id,
        name="Server - Rome's Flavours", target_role="SERVER",
    )

    # Task §10's own example traits — restaurant data, not architecture.
    # For Rome's Flavours these are assessed at PHONE_INTERVIEW, not
    # inferred from the résumé unless the résumé explicitly evidences them.
    romes_flavours_traits = [
        ("Works effectively as part of a team", "Teamwork"),
        ("Listens to and follows instruction", "Attitude / Behavioral Traits"),
        ("Applies coaching/teaching when given", "Trainability / Learning"),
        ("Humility combined with capability", "Attitude / Behavioral Traits"),
        ("Absence of strongly conflictual/counter-dependent behavior", "Attitude / Behavioral Traits"),
    ]
    for offset, (name, category) in enumerate(romes_flavours_traits):
        svc.add_requirement(
            session, requirement_set.id, name=name, category=category,
            criticality=rm.DISQUALIFIER, trainability=rm.NOT_TRAINABLE,
            assessment_stages=[rm.PHONE_INTERVIEW],
            guidance_notes=(
                "Assessed during phone interview; only inferred from the résumé if the résumé "
                "explicitly contains relevant evidence."
            ),
            display_order=100 + offset,
        )

    session.commit()
    return requirement_set.id


def seed_sample_signal_definitions(session: Session, *, restaurant_id: int) -> dict[str, int]:
    """Idempotent (matches by name, scoped to this restaurant) — creates a
    small, representative set of Selection Signal Definitions (Task 3C),
    one per family, each wired to a real detector in `signal_detector.py`.
    Restaurant-owned like `Requirement` (never a shared template, per
    concept note §5's own "each restaurant decides which Signals it wants
    to use"). Returns {name: signal_definition_id}."""

    existing = {
        d.name: d.id for d in session.scalars(
            select(m.SignalDefinition).where(m.SignalDefinition.restaurant_id == restaurant_id)
        ).all()
    }
    result: dict[str, int] = dict(existing)

    def _ensure(name: str, **kwargs) -> None:
        if name in existing:
            return
        definition = sig_svc.create_signal_definition(session, restaurant_id=restaurant_id, name=name, **kwargs)
        result[name] = definition.id

    _ensure(
        "Fit Assessment strength", signal_family=sm.FIT_EXPERIENCE, signal_subtype="fit_assessment_strength",
        description="At least half of the assessed Requirements (2 or more) are EVIDENCED.",
        assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_DERIVED_INFORMATION],
        detection_guidance="Reuses an existing Fit Assessment's summary counts for this candidate, where one exists.",
    )
    _ensure(
        "Recent relevant experience", signal_family=sm.READINESS_RECENCY,
        signal_subtype="recent_relevant_experience",
        description="Current or recently-ended (within 6 months) work in the target role/role family.",
        assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_FACT, fam.RESUME_DERIVED_INFORMATION],
    )
    _ensure(
        "Long relevant gap", signal_family=sm.READINESS_RECENCY, signal_subtype="long_relevant_gap",
        description="No relevant operational experience in the previous 24+ months.",
        assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_DERIVED_INFORMATION],
        detection_guidance="A professional-fact observation only — never a personal/protected explanation.",
    )
    _ensure(
        "Progression since previous application", signal_family=sm.MOTIVATION_PROFESSIONAL,
        signal_subtype="progression_since_previous_application",
        description="This person applied before for a different role; they have since gained experience "
                     "directly relevant to the CURRENT target role.",
        assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_DERIVED_INFORMATION],
    )
    _ensure(
        "Explicit interest statement", signal_family=sm.MOTIVATION_PERSONAL,
        signal_subtype="explicit_interest_statement",
        description="The résumé's own summary/self-description explicitly expresses interest in this "
                     "restaurant or in returning to this kind of work.",
        assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_FACT],
        detection_guidance="Kept at LOW confidence even when found — a self-report, never proof of motivation.",
    )
    # Deliberately assessable only later — proves the framework correctly
    # reports NOT_ASSESSED at the RESUME stage rather than guessing a
    # behavioral trait from résumé proxies (concept note §3B).
    _ensure(
        "Teamwork attitude", signal_family=sm.MOTIVATION_PERSONAL, signal_subtype=None,
        description="Ability to work effectively as part of a team.",
        assessment_stages=[rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW],
        evidence_sources_allowed=[fam.PHONE_INTERVIEW_RESPONSE, fam.IN_PERSON_OBSERVATION],
        detection_guidance="Not assessable from the résumé alone unless it explicitly and unusually states this.",
    )

    session.commit()
    return result


def seed_romes_flavours_in_person_interview_structure(session: Session, *, restaurant_id: int) -> dict[str, int]:
    """Task 4B §2/§7 — Rome's Flavours' own example In-Person Interview
    structure (6 Sections + example Assessment Items, incl. the SERVER
    Practical Assessment examples), as ONE restaurant's configured DATA —
    exactly like every other seeding function in this file. The universal
    In-Person engine (`core/in_person_interview_model.py`/
    `in_person_interview_service.py`) has no knowledge this content exists.
    "Professional presentation" is represented only through a lawful, job-
    related standard (task §5) — never appearance based on a protected
    characteristic. Idempotent — matches Sections by (restaurant, name).
    Returns {section_name: section_id}."""

    existing = {
        s.name: s.id for s in session.scalars(
            select(m.InPersonInterviewSectionDefinition).where(
                m.InPersonInterviewSectionDefinition.restaurant_id == restaurant_id,
                m.InPersonInterviewSectionDefinition.target_role == "SERVER",
            )
        ).all()
    }
    result: dict[str, int] = dict(existing)

    def _section(name: str, kind: str, order: int) -> m.InPersonInterviewSectionDefinition | None:
        if name in existing:
            return None
        section = ip_svc.create_section_definition(
            session, restaurant_id=restaurant_id, name=name, section_kind=kind, target_role="SERVER",
            display_order=order,
        )
        result[name] = section.id
        return section

    welcome = _section("Welcome & Observation", ipm.WELCOME_OBSERVATION, 0)
    if welcome:
        ip_svc.create_item_definition(
            session, welcome.id, item_type=ipm.OBSERVATION, title_or_question="Professional presentation",
            objective="Note whether the candidate presents in a manner suitable for guest-facing service.",
            importance=ipm.IMPORTANCE_LEVELS[1],
            selezionatore_instructions=(
                "Assess only lawful, job-related professional-presentation standards (e.g. clean, guest-"
                "appropriate attire consistent with this role) — never race, national origin, sex, age, "
                "disability, or any other protected characteristic."
            ),
        )
        ip_svc.create_item_definition(
            session, welcome.id, item_type=ipm.OBSERVATION, title_or_question="Face-to-face communication style",
            objective="Note clarity, listening behavior, and interaction style in natural conversation.",
            importance=ipm.IMPORTANCE_LEVELS[1],
        )
        ip_svc.create_item_definition(
            session, welcome.id, item_type=ipm.OBSERVATION, title_or_question="Energy / presence",
            objective="Note observable energy and presence — a direct observation only possible in person.",
            importance=ipm.IMPORTANCE_LEVELS[2],
        )

    personality = _section("Work Personality", ipm.WORK_PERSONALITY, 1)
    if personality:
        ip_svc.create_item_definition(
            session, personality.id, item_type=ipm.QUESTION, title_or_question="Describe your ideal workday.",
            objective="Understand working-style preferences.", importance=ipm.IMPORTANCE_LEVELS[2],
        )
        ip_svc.create_item_definition(
            session, personality.id, item_type=ipm.QUESTION,
            title_or_question="Tell me about a time you disagreed with a coworker. How did you handle it?",
            objective="Assess teamwork/conflict-handling behavior.", importance=ipm.IMPORTANCE_LEVELS[1],
        )

    hospitality = _section("Hospitality & Motivation", ipm.HOSPITALITY_MOTIVATION, 2)
    if hospitality:
        ip_svc.create_item_definition(
            session, hospitality.id, item_type=ipm.QUESTION,
            title_or_question="What does great hospitality mean to you?",
            objective="Assess hospitality mindset.", importance=ipm.IMPORTANCE_LEVELS[1],
        )
        ip_svc.create_item_definition(
            session, hospitality.id, item_type=ipm.QUESTION,
            title_or_question="Now that you've seen the restaurant, what would you look forward to here?",
            objective="Assess motivation with the benefit of having seen the actual workplace.",
            importance=ipm.IMPORTANCE_LEVELS[2],
        )

    practical = _section("Practical / Technical", ipm.PRACTICAL_TECHNICAL, 3)
    if practical:
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.ROLE_PLAY,
            title_or_question="Describe a dish from your previous restaurant as if I were a guest.",
            objective="Assess menu-description technique.", importance=ipm.IMPORTANCE_LEVELS[1],
            scenario="The Selezionatore plays the role of a guest asking about a dish.",
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.ROLE_PLAY,
            title_or_question="Recommend a pasta dish to me as if I were deciding what to order.",
            objective="Assess sales/upsell technique in a realistic role-play.", importance=ipm.IMPORTANCE_LEVELS[1],
            scenario="The Selezionatore plays the role of an undecided guest.",
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.PRACTICAL_TEST,
            title_or_question="Appetizers are still on the table and entrées are ready — what do you do?",
            objective="Assess practical service-timing judgment.", importance=ipm.IMPORTANCE_LEVELS[1],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.PRACTICAL_TEST,
            title_or_question="What do you do when you have no active tables?",
            objective="Assess proactive/hospitality mindset in a concrete scenario.",
            importance=ipm.IMPORTANCE_LEVELS[2],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.QUESTION, title_or_question="Explain side work.",
            objective="Assess practical operational knowledge.", importance=ipm.IMPORTANCE_LEVELS[2],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.QUESTION, title_or_question="Explain opening duties.",
            objective="Assess practical operational knowledge.", importance=ipm.IMPORTANCE_LEVELS[2],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.QUESTION, title_or_question="Explain closing duties.",
            objective="Assess practical operational knowledge.", importance=ipm.IMPORTANCE_LEVELS[2],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.PRACTICAL_TEST,
            title_or_question="Walk through the complete service sequence, start to finish.",
            objective="Assess end-to-end service-sequence knowledge.", importance=ipm.IMPORTANCE_LEVELS[1],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.ROLE_PLAY,
            title_or_question="Train me as if today were my first day at your previous restaurant.",
            objective="Assess ability to explain and teach a familiar process.", importance=ipm.IMPORTANCE_LEVELS[2],
            scenario="The Selezionatore plays the role of a brand-new coworker on their first shift.",
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.QUESTION, title_or_question="Basic wine knowledge — walk me through it.",
            objective="Assess baseline wine knowledge.", importance=ipm.IMPORTANCE_LEVELS[3],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.PRACTICAL_TEST,
            title_or_question="Demonstrate wine presentation / service technique.",
            objective="Assess wine service technique directly.", importance=ipm.IMPORTANCE_LEVELS[2],
        )
        ip_svc.create_item_definition(
            session, practical.id, item_type=ipm.PRACTICAL_TEST,
            title_or_question="Demonstrate proper handling of a wine glass and other service equipment.",
            objective="Assess equipment-handling technique directly.", importance=ipm.IMPORTANCE_LEVELS[3],
        )

    commitment = _section("Commitment", ipm.COMMITMENT, 4)
    if commitment:
        ip_svc.create_item_definition(
            session, commitment.id, item_type=ipm.QUESTION,
            title_or_question="Now that you've seen the role in more detail, does the schedule we discussed still work for you?",
            objective="Re-confirm schedule commitment with fuller information.", importance=ipm.IMPORTANCE_LEVELS[0],
            mandatory_within_selection_process=True,
        )
        ip_svc.create_item_definition(
            session, commitment.id, item_type=ipm.QUESTION,
            title_or_question="What are your professional goals over the next year?",
            objective="Assess commitment/goal alignment.", importance=ipm.IMPORTANCE_LEVELS[2],
        )

    final_observation = _section("Final Observation", ipm.FINAL_OBSERVATION, 5)
    if final_observation:
        ip_svc.create_item_definition(
            session, final_observation.id, item_type=ipm.COURTESY,
            title_or_question="Do you have any questions about how we operate?",
            objective="Close the interview and address the candidate's own questions.",
            importance=ipm.IMPORTANCE_LEVELS[3],
        )
        ip_svc.create_item_definition(
            session, final_observation.id, item_type=ipm.COURTESY, title_or_question="What else would you like to know?",
            objective="Cover tips, schedule, training, growth, and expectations as relevant.",
            importance=ipm.IMPORTANCE_LEVELS[3],
            selezionatore_instructions=(
                "Informal/courtesy phase — any observation made here becomes evidence ONLY if explicitly "
                "recorded as such; this phase never reveals the candidate's \"true personality.\""
            ),
        )

    session.commit()
    return result


def seed_romes_flavours_primary_screening_criteria(session: Session, *, restaurant_id: int) -> dict[str, int]:
    """Task 3D §11 — Rome's Flavours' own example Primary Screening
    Criteria, derived from its own hiring philosophy, as ONE restaurant's
    configured DATA — exactly like every other seeding function in this
    file. The universal Primary Screening Engine
    (`core/primary_screening_model.py`/`primary_screening_service.py`) has
    no knowledge this content exists; a different restaurant seeds nothing
    here and defines entirely different Criteria with entirely different
    coefficients/level meanings instead (task §10). None of these Criteria
    touch a protected personal characteristic (task §27). "Experience
    Recency" is wired to the existing "Recent relevant experience" Signal
    via the engine's optional auto-evaluation mapping (task §12/§18),
    demonstrating — not requiring — that shortcut. Idempotent — matches by
    (restaurant, target_role, name). Returns {criterion_name: criterion_id}."""

    existing = {
        c.name: c.id for c in session.scalars(
            select(m.PrimaryScreeningCriterion).where(
                m.PrimaryScreeningCriterion.restaurant_id == restaurant_id,
                m.PrimaryScreeningCriterion.target_role == "SERVER",
            )
        ).all()
    }
    result: dict[str, int] = dict(existing)
    signal_definitions = seed_sample_signal_definitions(session, restaurant_id=restaurant_id)

    def _ensure(name: str, **kwargs) -> None:
        if name in existing:
            return
        criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant_id, target_role="SERVER", name=name, **kwargs
        )
        result[name] = criterion.id

    _ensure(
        "Relevant experience", category="Experience", coefficient=2.0, direction=psm.POSITIVE,
        description="How much directly relevant restaurant service experience this candidate has on record.",
        level_descriptions={
            "0": "No relevant restaurant experience found.", "1": "Brief or tangential relevant experience.",
            "2": "Some directly relevant experience.", "3": "Solid, multi-role relevant experience.",
            "4": "Extensive, clearly strong relevant experience.",
        },
        evidence_sources_allowed=[psm.RESUME_FACT, psm.RESUME_DERIVED_INFORMATION],
        evaluation_guidance="Base this on the résumé's own work history entries for restaurant/hospitality roles.",
    )
    _ensure(
        "Experience recency", category="Experience", coefficient=1.5, direction=psm.POSITIVE,
        description="How recently the candidate held relevant restaurant experience.",
        level_descriptions={
            "0": "No relevant recent experience.", "1": "Limited — relevant experience is old.",
            "2": "Moderate — some relevant experience within the last couple of years.",
            "3": "Recent — relevant experience within the last year.",
            "4": "Very recent/highly relevant — current or just-ended relevant role.",
        },
        evidence_sources_allowed=[psm.RESUME_DERIVED_INFORMATION, psm.SELECTION_SIGNAL],
        auto_evaluation_signal_definition_id=signal_definitions.get("Recent relevant experience"),
        auto_evaluation_level_map={sm.DETECTED: 4, sm.POSSIBLE: 2, sm.NOT_DETECTED: 0, sm.CONFLICTING: 2},
    )
    _ensure(
        "Availability / schedule compatibility", category="Availability", coefficient=3.0, direction=psm.NEGATIVE,
        description="How incompatible the candidate's stated availability is with this role's operational needs.",
        level_descriptions={
            "0": "Fully compatible schedule.", "1": "Minor gaps, easily worked around.",
            "2": "Some real limitations on availability.", "3": "Significant, hard-to-accommodate limitations.",
            "4": "Availability is fundamentally incompatible with the role's required schedule.",
        },
        evidence_sources_allowed=[psm.APPLICATION, psm.SELEZIONATORE_INPUT],
        is_hard_disqualifier=True, hard_disqualifier_trigger_level=4,
        evaluation_guidance="Base this on any stated availability on the Application, or on direct Selezionatore input.",
    )
    _ensure(
        "Repeated-application history", category="History", coefficient=1.0, direction=psm.POSITIVE,
        description="Whether a repeated applicant shows meaningful positive progression since a prior Application.",
        level_descriptions={
            "0": "No repeat-Application history (first-time applicant).", "1": "Repeat applicant, no notable change.",
            "2": "Repeat applicant with a minor positive change.", "3": "Repeat applicant with a clear positive change.",
            "4": "Repeat applicant with strong, directly relevant progression since the prior Application.",
        },
        evidence_sources_allowed=[psm.APPLICATION_HISTORY, psm.SELECTION_SIGNAL],
        auto_evaluation_signal_definition_id=signal_definitions.get("Progression since previous application"),
        auto_evaluation_level_map={sm.DETECTED: 4, sm.POSSIBLE: 2, sm.NOT_DETECTED: 0},
    )
    _ensure(
        "Job stability", category="History", coefficient=1.5, direction=psm.NEGATIVE,
        description="How much of a concern short-tenure/frequent job changes are on this candidate's record.",
        level_descriptions={
            "0": "Stable employment record.", "1": "One shorter-than-typical role.",
            "2": "A couple of shorter roles.", "3": "A clear pattern of short tenures.",
            "4": "A strong, repeated pattern of very short tenures across most roles.",
        },
        evidence_sources_allowed=[psm.RESUME_DERIVED_INFORMATION],
    )
    _ensure(
        "Motivation signals", category="Motivation", coefficient=1.0, direction=psm.POSITIVE,
        description="Strength of any explicit motivation/interest signal found so far.",
        level_descriptions={
            "0": "No motivation signal found.", "1": "Weak/generic signal.", "2": "Some genuine signal.",
            "3": "Clear, specific signal.", "4": "Strong, specific, well-supported signal.",
        },
        evidence_sources_allowed=[psm.RESUME_FACT, psm.SELECTION_SIGNAL],
        auto_evaluation_signal_definition_id=signal_definitions.get("Explicit interest statement"),
        auto_evaluation_level_map={sm.DETECTED: 4, sm.POSSIBLE: 2, sm.NOT_DETECTED: 0},
    )

    session.commit()
    return result


def seed_default_review_priority_policy(session: Session, *, restaurant_id: int) -> int:
    """Idempotent — one example Review Priority Policy (concept note §9),
    demonstrating that Signal detection (universal) and how much a detected
    Signal matters (this restaurant's own policy) are separate layers. A
    DIFFERENT restaurant could use the identical Signal Definitions above
    with a completely different policy (or none at all, leaving every
    Application STANDARD)."""

    existing = session.scalars(
        select(m.ReviewPriorityPolicy).where(
            m.ReviewPriorityPolicy.restaurant_id == restaurant_id,
            m.ReviewPriorityPolicy.name == "Default Review Priority Policy",
        )
    ).first()
    if existing:
        return existing.id

    definitions = seed_sample_signal_definitions(session, restaurant_id=restaurant_id)
    policy = sig_svc.create_policy(session, restaurant_id=restaurant_id, name="Default Review Priority Policy")

    rules = [
        ("Fit Assessment strength", sm.DETECTED, sm.INCREASE),
        ("Recent relevant experience", sm.DETECTED, sm.INCREASE),
        ("Long relevant gap", sm.DETECTED, sm.DECREASE),
        ("Progression since previous application", sm.DETECTED, sm.STRONGLY_INCREASE),
        ("Progression since previous application", sm.POSSIBLE, sm.INCREASE),
        ("Explicit interest statement", sm.POSSIBLE, sm.INCREASE),
    ]
    for signal_name, observed_status, contribution in rules:
        if signal_name in definitions:
            sig_svc.add_policy_rule(
                session, policy.id, signal_definition_id=definitions[signal_name],
                observed_status=observed_status, contribution=contribution,
            )

    session.commit()
    return policy.id


def seed_romes_flavours_phone_interview_questions(session: Session, *, restaurant_id: int) -> dict[str, int]:
    """Task 4A §18 — Rome's Flavours' own example SERVER Phone Interview
    Core Question set, as ONE restaurant's configured DATA
    (`PhoneInterviewQuestionDefinition` rows), exactly like every other
    seeding function in this file. The universal Phone Interview engine
    (`core/phone_interview_model.py`/`phone_interview_service.py`) has no
    knowledge this content exists — a different restaurant seeds nothing
    here and authors its own Core Questions instead (`/phone-interview-
    questions` UI). None of these questions touch a protected personal
    characteristic (task §19); reliability/attendance topics are asked
    directly rather than inferred from one. Idempotent — matches by
    (restaurant, target_role, question_text). Returns
    {question_text: definition_id} for every question, old or new."""

    existing = {
        d.question_text: d.id for d in session.scalars(
            select(m.PhoneInterviewQuestionDefinition).where(
                m.PhoneInterviewQuestionDefinition.restaurant_id == restaurant_id,
                m.PhoneInterviewQuestionDefinition.target_role == "SERVER",
            )
        ).all()
    }
    result: dict[str, int] = dict(existing)

    def _ensure(question_text: str, **kwargs) -> None:
        if question_text in existing:
            return
        definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant_id, target_role="SERVER", question_text=question_text, **kwargs
        )
        result[question_text] = definition.id

    # SINE QUA NON / EARLY — genuine non-negotiable job requirements this
    # restaurant configured; the framework itself assumes none of these
    # (task §5).
    _ensure(
        "What is your current work status (employed, notice period, available immediately)?",
        objective="Confirm practical availability timeline.", importance=pim.CRITICAL, is_sine_qua_non=True,
        mandatory_within_selection_process=True,
    )
    _ensure(
        "Are you looking for full-time or part-time work?",
        objective="Confirm full-time/part-time preference matches the role.", importance=pim.CRITICAL,
        is_sine_qua_non=True, mandatory_within_selection_process=True,
    )
    _ensure(
        "Are you available to work weekends?",
        objective="Confirm weekend availability, a genuine requirement of this role.", importance=pim.CRITICAL,
        is_sine_qua_non=True, mandatory_within_selection_process=True,
    )
    _ensure(
        "Are you available to work closing shifts?",
        objective="Confirm closing-shift availability, a genuine requirement of this role.", importance=pim.CRITICAL,
        is_sine_qua_non=True, mandatory_within_selection_process=True,
    )
    _ensure(
        "When could you start training if offered the role?",
        objective="Confirm training-start compatibility with the restaurant's own timeline.",
        importance=pim.CRITICAL, is_sine_qua_non=True, mandatory_within_selection_process=True,
    )
    _ensure(
        "Do you have any known schedule conflicts we should be aware of?",
        objective="Surface any known schedule conflict before investing time in the rest of the interview.",
        importance=pim.CRITICAL, is_sine_qua_non=True, mandatory_within_selection_process=True,
    )

    # RELIABILITY / WORK HISTORY — asked directly (task §19: attendance,
    # punctuality, schedule compatibility, commitment, contingency
    # handling, previous work behavior), never inferred from a protected
    # characteristic.
    _ensure(
        "Why did you leave your last job?",
        objective="Understand the candidate's own account of their most recent job change.", importance=pim.HIGH,
        follow_up_guidance="If vague, ask what specifically led to the decision.",
    )
    _ensure(
        "Why did you leave the job before that?",
        objective="Look for a pattern (or lack of one) across job changes.", importance=pim.MEDIUM,
    )
    _ensure(
        "During your previous employment, how would your manager describe your attendance and punctuality?",
        objective="Assess reliability directly, in the candidate's own words.", importance=pim.HIGH,
    )
    _ensure(
        "Tell me about the last time something unexpected affected a work commitment. What did you do?",
        objective="Assess contingency handling with a concrete example.", importance=pim.HIGH,
        follow_up_guidance="If no concrete example is given, ask for a specific instance.",
    )
    _ensure(
        "If something happens shortly before a shift and you may be late, walk me through what you would do.",
        objective="Assess communication/commitment under a realistic scheduling scenario.", importance=pim.HIGH,
    )

    # ATTITUDE / TEAM / COACHABILITY
    _ensure(
        "Describe the best manager you worked for.",
        objective="Understand what management style the candidate responds well to.", importance=pim.MEDIUM,
    )
    _ensure(
        "Describe the manager you liked least and why.",
        objective="Understand management-compatibility risk factors, in the candidate's own words.",
        importance=pim.MEDIUM,
        follow_up_guidance="If the answer centers on a conflict, ask what specifically was difficult about it "
                            "— capture evidence first, never label the candidate.",
    )
    _ensure(
        "Describe your ideal coworker.",
        objective="Understand teamwork expectations/preferences.", importance=pim.MEDIUM,
    )
    _ensure(
        "Tell me one strength at work.", objective="Understand self-assessment of strengths.", importance=pim.LOW,
    )
    _ensure(
        "Tell me one weakness, and what you have done to improve it.",
        objective="Understand self-awareness and coachability.", importance=pim.MEDIUM,
    )
    _ensure(
        "Tell me about a mistake you made at work and what you learned from it.",
        objective="Assess accountability and learning from mistakes.", importance=pim.HIGH,
    )
    _ensure(
        "Do you prefer clear structure or improvisation?",
        objective="Understand working-style fit.", importance=pim.LOW,
    )

    # MOTIVATION
    _ensure(
        "Did you know Rome's Flavours before applying? What do you know about the restaurant?",
        objective="Assess genuine interest/preparation.", importance=pim.MEDIUM,
    )
    _ensure(
        "Why did you apply here, and what do you expect from working here?",
        objective="Assess motivation and expectation alignment.", importance=pim.HIGH,
    )
    _ensure(
        "What are your professional goals?",
        objective="Assess longer-term motivation alignment.", importance=pim.LOW,
    )
    _ensure(
        "If offered the job today, would you accept, or would you want time to think it over?",
        objective="Gauge current level of interest/certainty.", importance=pim.MEDIUM,
    )
    _ensure(
        "What would make you choose Rome's Flavours over another offer?",
        objective="Understand what this candidate values in an employer.", importance=pim.LOW,
    )

    # HOSPITALITY / TECHNICAL
    _ensure(
        "What do you do when you have no tables to attend to?",
        objective="Assess proactive/hospitality mindset.", importance=pim.MEDIUM,
        assessment_stages=[rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW],
    )
    _ensure(
        "Describe a dish from your previous restaurant as if I were a guest.",
        objective="Assess menu-description/selling technique.", importance=pim.MEDIUM,
    )
    _ensure(
        "What do you do if entrées are ready while appetizers are still on the table?",
        objective="Assess practical service-timing judgment.", importance=pim.MEDIUM,
    )
    _ensure(
        "Are you familiar with Italian cuisine? Can you explain a dish you know?",
        objective="Assess baseline cuisine familiarity.", importance=pim.LOW,
    )

    # COURTESY — Escape Route closing questions (task §7); short and
    # professional, never substantive.
    _ensure(
        "Thank you for your time today — do you have any questions for us before we wrap up?",
        objective="Close the call professionally.", importance=pim.LOW, is_courtesy=True,
    )
    _ensure(
        "Is there anything else about your background you'd like us to know?",
        objective="Close the call professionally, leaving room for the candidate to add anything relevant.",
        importance=pim.LOW, is_courtesy=True,
    )

    session.commit()
    return result


def seed_default_selection_queues(session: Session, *, restaurant_id: int) -> dict[str, int]:
    """Task 5A-FIX §8/§15 — RF-One's own basic example operational
    queues/lists (Active Review, Call Later, Hold, Reconsider, Hired,
    Closed — the task's own examples), seeded per-restaurant exactly like
    every other seeding function in this file. These are examples only,
    never a universal set — a restaurant may rename, deactivate, or add
    entirely different queues. Idempotent — matches by (restaurant, name).
    Returns {queue_name: queue_id}."""

    existing = {
        q.name: q.id for q in session.scalars(
            select(m.SelectionQueue).where(m.SelectionQueue.restaurant_id == restaurant_id)
        ).all()
    }
    result: dict[str, int] = dict(existing)

    def _ensure(name: str, description: str) -> None:
        if name in existing:
            return
        queue = queue_svc.create_queue(session, restaurant_id=restaurant_id, name=name, description=description)
        result[name] = queue.id

    _ensure("Active Review", "Applications currently under normal, ongoing consideration.")
    _ensure("Call Later", "Applications to follow up with by phone at a later time.")
    _ensure("Hold", "Applications paused, not currently being advanced.")
    _ensure("Reconsider", "Applications kept for later reconsideration.")
    _ensure("Hired", "Applications that resulted in a hire.")
    _ensure("Closed", "Applications no longer proceeding.")

    session.commit()
    return result


def seed_default_selection_outcomes(session: Session, *, restaurant_id: int) -> dict[str, int]:
    """Task 5A §4 — RF-One's own basic example Outcome Definitions
    (ACTIVE, HIRE, HOLD, STOP, WITHDRAWN), seeded per-restaurant exactly
    like every other seeding function in this file. These are "templates/
    default restaurant configuration, not the complete universal set of
    Outcomes" (task's own §4) — a restaurant may edit any of these or add
    entirely different ones; the universal Outcome engine
    (`core/outcome_model.py`/`outcome_service.py`) has no knowledge this
    content exists. Idempotent — matches by (restaurant, name). Returns
    {outcome_name: definition_id}.

    Task 5A-FIX §15: Hire/Hold/Stop/Withdrawn each target one of the
    default queues seeded above, demonstrating (never requiring) the
    Outcome -> Queue action out of the box."""

    queues = seed_default_selection_queues(session, restaurant_id=restaurant_id)
    existing = {
        d.name: d.id for d in session.scalars(
            select(m.SelectionOutcomeDefinition).where(m.SelectionOutcomeDefinition.restaurant_id == restaurant_id)
        ).all()
    }
    result: dict[str, int] = dict(existing)

    def _ensure(name: str, **kwargs) -> None:
        if name in existing:
            return
        definition = outcome_svc.create_outcome_definition(session, restaurant_id=restaurant_id, name=name, **kwargs)
        result[name] = definition.id

    _ensure(
        "Active / Continue", description="The Application remains open and under normal, ongoing consideration.",
        lifecycle_effect=om.ACTIVE, is_reopenable=True, requires_note=False, requires_reason=False,
        target_queue_id=queues.get("Active Review"), authority_label="Selezionatore",
        driven_by=om.DRIVEN_BY_RESTAURANT,
    )

    # Task 5A-ALIGN §5/§9/§10/§13 — "HIRABLE," never "HIRE": the
    # Selezionatore considers the candidate suitable to proceed toward
    # Training, NOT that they are already an employee. A restaurant that
    # seeded this Outcome before this fix, under the old name "Hire," gets
    # its LIVE definition row renamed in place (its id — and therefore
    # every historical decision's own immutable snapshot, which still says
    # "Hire" forever, exactly as it was when that decision was made — is
    # untouched); a brand-new restaurant simply gets "Hirable" directly.
    hirable_description = (
        "The Selezionatore considers this candidate suitable to proceed toward employment. This does NOT mean "
        "the candidate is already an employee — Training and a successful Training Check must still follow "
        "before HIRED (outside Selection's scope)."
    )
    if "Hire" in existing and "Hirable" not in existing:
        outcome_svc.update_outcome_definition(
            session, existing["Hire"], name="Hirable", description=hirable_description,
            authority_label="Selezionatore", driven_by=om.DRIVEN_BY_RESTAURANT,
        )
        result["Hirable"] = result.pop("Hire")
    else:
        _ensure(
            "Hirable", description=hirable_description, lifecycle_effect=om.CLOSED, is_reopenable=True,
            requires_note=False, requires_reason=False, future_contact_policy=om.CONTACT_ALLOWED,
            target_queue_id=queues.get("Hired"), authority_label="Selezionatore", driven_by=om.DRIVEN_BY_RESTAURANT,
        )

    _ensure(
        # Task 5A-ALIGN §10 — conceptually distinct from Stop: the
        # restaurant considered the candidate suitable, but the CANDIDATE
        # chose not to continue. Applying this AFTER "Hirable" never erases
        # the original Hirable decision — it simply appends one more,
        # exactly like any other Outcome change (task's own append-only
        # history rule).
        "Hirable / Declined",
        description=(
            "The candidate was judged Hirable but subsequently declined the opportunity before proceeding. "
            "The original Hirable decision remains on record. Conceptually different from Stop — the restaurant "
            "considered this person suitable; the candidate chose not to continue."
        ),
        lifecycle_effect=om.CLOSED, is_reopenable=True, requires_note=True, requires_reason=False,
        future_contact_policy=om.CONTACT_ALLOWED, target_queue_id=queues.get("Closed"),
        authority_label="Selezionatore", driven_by=om.DRIVEN_BY_CANDIDATE,
    )
    _ensure(
        "Hold", description="Interesting, but not being actively advanced right now — kept for later reconsideration.",
        lifecycle_effect=om.SUSPENDED, is_reopenable=True, requires_note=False, requires_reason=True,
        reason_choices=[
            "Sufficient pipeline already exists for this role", "Timing not right for this candidate",
            "Awaiting further information",
        ],
        target_queue_id=queues.get("Hold"), authority_label="Selezionatore", driven_by=om.DRIVEN_BY_RESTAURANT,
    )
    _ensure(
        "Stop", description="This Application will not proceed further right now.",
        lifecycle_effect=om.CLOSED, is_reopenable=True, requires_note=False, requires_reason=True,
        reason_choices=[
            "Experience too distant from the target role", "Availability incompatible with the role",
            "Candidate did not respond", "Better-fitting candidates identified",
        ],
        future_contact_policy=om.CONTACT_ALLOWED, target_queue_id=queues.get("Closed"),
        authority_label="Selezionatore", driven_by=om.DRIVEN_BY_RESTAURANT,
    )
    _ensure(
        "Withdrawn", description="The candidate communicated that they are withdrawing from consideration.",
        lifecycle_effect=om.CLOSED, is_reopenable=True, requires_note=True, requires_reason=False,
        future_contact_policy=om.CONTACT_ALLOWED, target_queue_id=queues.get("Closed"),
        authority_label="Selezionatore", driven_by=om.DRIVEN_BY_CANDIDATE,
    )

    # Task 5A-ALIGN §11/§12 — downstream Training outcomes. Training
    # itself is NOT implemented here (no Trainer UI, no Training domain) —
    # these two rows only let Selection PRESERVE the fact and its history
    # cleanly if/when a future Training integration (or, today, a
    # Selezionatore recording what a Trainer reported) needs to apply them.
    # "Training Check Not Passed" automatically creates a Candidate Flag
    # (task §12's own "a very strong historical negative fact... should be
    # immediately visible" on any future Application) — never an automatic
    # Hard Disqualifier; a restaurant wires that up itself, explicitly, in
    # Primary Screening Criteria configuration (task's own "do not hard-
    # code it universally as mandatory").
    _ensure(
        "Training Withdrawn",
        description=(
            "The candidate began Training and voluntarily withdrew. Training itself is not implemented in "
            "Selection — this Outcome only preserves the fact and its history."
        ),
        lifecycle_effect=om.CLOSED, is_reopenable=True, requires_note=True, requires_reason=False,
        future_contact_policy=om.CONTACT_ALLOWED, target_queue_id=queues.get("Closed"),
        authority_label="Selezionatore", driven_by=om.DRIVEN_BY_CANDIDATE,
    )
    _ensure(
        "Training Check Not Passed",
        description=(
            "The candidate reached the required Training Check but the Trainer determined it was not passed. "
            "The Trainer, not the Selezionatore, is the authority for this result. Training itself is not "
            "implemented in Selection."
        ),
        lifecycle_effect=om.CLOSED, is_reopenable=True, requires_note=True, requires_reason=False,
        future_contact_policy=om.CONTACT_ALLOWED, target_queue_id=queues.get("Closed"),
        authority_label="Trainer", driven_by=om.DRIVEN_BY_RESTAURANT,
        creates_candidate_flag=True, candidate_flag_name="Training Check Not Passed",
        candidate_flag_scope=om.FLAG_GLOBAL_WITHIN_RESTAURANT, candidate_flag_operational_effect=om.FLAG_WARNING,
        candidate_flag_default_reason="Did not pass the required Training Check on a previous Application.",
    )

    session.commit()
    return result
