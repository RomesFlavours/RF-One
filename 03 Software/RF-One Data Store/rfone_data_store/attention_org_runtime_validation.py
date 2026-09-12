"""Automated synthetic tests for the Organizational Responsibility +
Attention Management shared runtime (TASK_ATTENTION_ORG_RUNTIME §17-18).

Mirrors `tips_distribution_engine_validation.py`'s pattern: builds a
synthetic fixture inside a disposable database, exercises
`organizational_responsibility_service`/`attention_service` directly — NO
Domain package (Tips included) is imported anywhere in this file, proving
the Foundation needs none to be exercised. All names are clearly synthetic
(`TEST/DEMO` prefixed), never a real Rome's Flavours person (task §14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from . import attention_service as att_svc
from . import models as m
from . import organizational_responsibility_service as org_svc
from .organizational_responsibility_service import ScopeContext

UTC = timezone.utc
T0 = datetime(2026, 3, 1, tzinfo=UTC)

# Names this test suite must NEVER contain (task §14) — asserted directly,
# not just avoided by convention.
_REAL_ROMES_FLAVOURS_NAMES = ("Pino", "Anthony", "Tatiana", "Giovanna")


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
            _run_all_scenarios(session, result)
        finally:
            session.rollback()
    return result


def _identity(session: Session, name: str) -> "m.ActingIdentity":
    identity = m.ActingIdentity(kind=m.HUMAN_USER, display_name=name)
    session.add(identity)
    session.flush()
    return identity


def _run_all_scenarios(session: Session, result: ValidationResult) -> None:
    # === 1: Position distinct from Occupant ==================================
    position_a = org_svc.create_position(session, name="TEST/DEMO Position A")
    occupant_x = _identity(session, "TEST/DEMO Occupant X")
    session.commit()
    result.check(
        "1. Position is a distinct row from its Occupant (different tables/ids)",
        isinstance(position_a, m.Position) and isinstance(occupant_x, m.ActingIdentity)
        and position_a.id != occupant_x.id,
    )

    # === 2: scope matching correct ===========================================
    org_svc.add_position_scope(session, position=position_a, scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=42)
    session.commit()
    result.check(
        "2a. scope matching: Position scoped to Restaurant 42 matches context Restaurant 42",
        org_svc.position_matches_scope(
            session, position=position_a, context=ScopeContext(scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=42),
        ),
    )
    result.check(
        "2b. scope matching: Position scoped to Restaurant 42 does NOT match Restaurant 99",
        not org_svc.position_matches_scope(
            session, position=position_a, context=ScopeContext(scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=99),
        ),
    )

    # === 3: Position vacante ==================================================
    position_vacant = org_svc.create_position(session, name="TEST/DEMO Vacant Position")
    session.commit()
    result.check(
        "3. A Position with no assignment is VACANT (resolve_current_occupant returns None)",
        org_svc.resolve_current_occupant(session, position=position_vacant) is None,
    )

    # === 4: occupant effective-dated =========================================
    org_svc.assign_occupant(
        session, position=position_a, occupant=occupant_x, valid_from=T0 + timedelta(days=1),
        valid_to=T0 + timedelta(days=10),
    )
    session.commit()
    result.check(
        "4a. occupant effective-dated: not yet occupant BEFORE valid_from",
        org_svc.resolve_current_occupant(session, position=position_a, now=T0) is None,
    )
    result.check(
        "4b. occupant effective-dated: IS occupant DURING [valid_from, valid_to)",
        org_svc.resolve_current_occupant(session, position=position_a, now=T0 + timedelta(days=5)) is occupant_x,
    )
    result.check(
        "4c. occupant effective-dated: no longer occupant AFTER valid_to",
        org_svc.resolve_current_occupant(session, position=position_a, now=T0 + timedelta(days=11)) is None,
    )
    # Re-establish an open-ended occupancy for the remaining scenarios.
    org_svc.assign_occupant(session, position=position_a, occupant=occupant_x, valid_from=T0 + timedelta(days=11))
    session.commit()

    # === 5/6: temporary coverage attiva / scaduta ============================
    position_z = org_svc.create_position(session, name="TEST/DEMO Position Z")
    occupant_z = _identity(session, "TEST/DEMO Occupant Z")
    org_svc.assign_occupant(session, position=position_z, occupant=occupant_z, valid_from=T0)
    session.commit()

    expired_coverage = org_svc.create_temporary_coverage(
        session, covered_position=position_a, delegate_position=position_z,
        valid_from=T0 + timedelta(days=20), valid_to=T0 + timedelta(days=25),
    )
    session.commit()
    result.check(
        "5. temporary coverage ACTIVE within its own window",
        org_svc.resolve_active_coverage(session, position=position_a, now=T0 + timedelta(days=22)) is not None,
    )
    result.check(
        "6. temporary coverage EXPIRED after its own valid_to is not returned",
        org_svc.resolve_active_coverage(session, position=position_a, now=T0 + timedelta(days=26)) is None,
    )
    # No coverage active at the "current" reference time used below.
    result.check(
        "6b. no coverage active before this scenario's window starts",
        org_svc.resolve_active_coverage(session, position=position_a, now=T0 + timedelta(days=15)) is None,
    )

    # === 7/8: Process Ownership resolution + phase-specific =================
    domain_1, process_1 = "TESTDOMAIN_ONE", "TEST_PROCESS_ONE"
    org_svc.set_process_ownership(session, domain=domain_1, process_name=process_1, position=position_a)
    session.commit()
    owner = org_svc.resolve_process_owner(session, domain=domain_1, process_name=process_1)
    result.check("7. Process Ownership resolves to the correct whole-process Position", owner.position is position_a)

    position_ops_owner = org_svc.create_position(session, name="TEST/DEMO Operations Owner")
    org_svc.set_process_ownership(
        session, domain=domain_1, process_name=process_1, position=position_ops_owner,
        phase=m.PROCESS_PHASE_OPERATIONS,
    )
    session.commit()
    owner_ops = org_svc.resolve_process_owner(
        session, domain=domain_1, process_name=process_1, phase=m.PROCESS_PHASE_OPERATIONS,
    )
    owner_planning_falls_back = org_svc.resolve_process_owner(
        session, domain=domain_1, process_name=process_1, phase=m.PROCESS_PHASE_PLANNING,
    )
    result.check(
        "8a. phase-specific ownership: OPERATIONS resolves to its own dedicated Position",
        owner_ops.position is position_ops_owner,
    )
    result.check(
        "8b. phase-specific ownership: a phase with no dedicated row falls back to whole-process ownership",
        owner_planning_falls_back.position is position_a,
    )

    # === 9: Attention HIGH routing ============================================
    item_high = att_svc.create_attention(
        session, source_domain=domain_1, source_process_name=process_1, reason="TEST/DEMO: something needs review",
        priority=m.ATTENTION_PRIORITY_HIGH,
    )
    session.commit()
    att_svc.route_attention(session, item=item_high, now=T0 + timedelta(days=15))
    session.commit()
    result.check(
        "9. Attention HIGH routes to the Process Owner's current Occupant",
        item_high.resolved_recipient_acting_identity_id == occupant_x.id
        and item_high.status == m.ATTENTION_STATUS_OPEN,
    )

    # === 10: unresolved routing ================================================
    domain_2, process_2 = "TESTDOMAIN_TWO", "TEST_PROCESS_VACANT_OWNER"
    org_svc.set_process_ownership(session, domain=domain_2, process_name=process_2, position=position_vacant)
    item_unresolved = att_svc.create_attention(
        session, source_domain=domain_2, source_process_name=process_2, reason="TEST/DEMO: vacant owner case",
        priority=m.ATTENTION_PRIORITY_MEDIUM,
    )
    session.commit()
    att_svc.route_attention(session, item=item_unresolved)
    session.commit()
    result.check(
        "10. Unresolved routing (vacant Position, no coverage) stays OPEN with no recipient assigned",
        item_unresolved.resolved_recipient_acting_identity_id is None
        and item_unresolved.routing_unresolved_reason is not None
        and item_unresolved.status == m.ATTENTION_STATUS_OPEN,
    )

    # === 11: routing verso delegate vigente ===================================
    item_for_coverage = att_svc.create_attention(
        session, source_domain=domain_1, source_process_name=process_1, reason="TEST/DEMO: during coverage window",
        priority=m.ATTENTION_PRIORITY_HIGH,
    )
    session.commit()
    att_svc.route_attention(session, item=item_for_coverage, now=T0 + timedelta(days=22))
    session.commit()
    result.check(
        "11. Routing during an active temporary coverage reaches the DELEGATE's occupant, not the covered Position's",
        item_for_coverage.resolved_recipient_acting_identity_id == occupant_z.id,
    )

    # === 12: nessun hardcoding di persone =====================================
    all_display_names = " ".join(
        i.display_name for i in session.query(m.ActingIdentity).all()
    )
    result.check(
        "12. No real Rome's Flavours person name appears anywhere in this Foundation's own test data",
        not any(name in all_display_names for name in _REAL_ROMES_FLAVOURS_NAMES),
    )

    # === 13: più Domain possono usare lo stesso servizio ======================
    domain_3, process_3 = "TESTDOMAIN_THREE", "TEST_PROCESS_THREE"
    position_b = org_svc.create_position(session, name="TEST/DEMO Position B (Domain 3)")
    occupant_b = _identity(session, "TEST/DEMO Occupant B")
    org_svc.assign_occupant(session, position=position_b, occupant=occupant_b, valid_from=T0)
    org_svc.set_process_ownership(session, domain=domain_3, process_name=process_3, position=position_b)
    session.commit()
    owner_3 = org_svc.resolve_process_owner(session, domain=domain_3, process_name=process_3)
    result.check(
        "13. The identical service resolves ownership correctly for a THIRD, unrelated domain string",
        owner_3.position is position_b and domain_3 != domain_1 and domain_3 != domain_2,
    )

    # === 14: Attention resolved/acknowledged lifecycle ========================
    lifecycle_item = att_svc.create_attention(
        session, source_domain=domain_1, source_process_name=process_1, reason="TEST/DEMO: lifecycle",
        priority=m.ATTENTION_PRIORITY_LOW,
    )
    session.commit()
    att_svc.acknowledge_attention(session, item=lifecycle_item, by=occupant_x)
    ack_ok = lifecycle_item.status == m.ATTENTION_STATUS_ACKNOWLEDGED and lifecycle_item.acknowledged_by_identity_id == occupant_x.id
    att_svc.resolve_attention(session, item=lifecycle_item, by=occupant_x)
    resolved_ok = lifecycle_item.status == m.ATTENTION_STATUS_RESOLVED and lifecycle_item.resolved_by_identity_id == occupant_x.id
    session.commit()
    invalid_transition_raised = False
    try:
        att_svc.acknowledge_attention(session, item=lifecycle_item, by=occupant_x)
    except att_svc.AttentionError:
        invalid_transition_raised = True
    result.check(
        "14. Attention lifecycle: OPEN -> ACKNOWLEDGED -> RESOLVED, and re-acknowledging a RESOLVED item is refused",
        ack_ok and resolved_ok and invalid_transition_raised,
    )

    _run_integration_demo(session, result)


def _run_integration_demo(session: Session, result: ValidationResult) -> None:
    """Task §18's own explicit cross-domain demo, self-contained and
    independent of the numbered scenarios above (fresh Positions/Process
    name) so it can be read/verified on its own."""
    domain_demo, process_demo = "TEST/DEMO Domain", "TEST/DEMO Process P"

    position_demo_a = org_svc.create_position(session, name="TEST/DEMO Position A (integration demo)")
    occupant_demo_x = _identity(session, "TEST/DEMO Occupant X (integration demo)")
    org_svc.assign_occupant(session, position=position_demo_a, occupant=occupant_demo_x, valid_from=T0)
    org_svc.add_position_scope(
        session, position=position_demo_a, scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=999,
    )
    org_svc.set_process_ownership(session, domain=domain_demo, process_name=process_demo, position=position_demo_a)
    session.commit()

    demo_context = ScopeContext(scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=999)
    item_demo = att_svc.create_attention(
        session, source_domain=domain_demo, source_process_name=process_demo,
        reason="TEST/DEMO: integration demo attention", priority=m.ATTENTION_PRIORITY_HIGH, scope=demo_context,
    )
    session.commit()
    att_svc.route_attention(session, item=item_demo, now=T0 + timedelta(days=1))
    session.commit()
    result.check(
        "18a. Integration demo: Attention on Process P routes to Position A's Occupant X",
        item_demo.resolved_recipient_acting_identity_id == occupant_demo_x.id,
    )

    position_demo_z = org_svc.create_position(session, name="TEST/DEMO Position Z (integration demo)")
    occupant_demo_z = _identity(session, "TEST/DEMO Occupant Z (integration demo)")
    org_svc.assign_occupant(session, position=position_demo_z, occupant=occupant_demo_z, valid_from=T0)
    org_svc.create_temporary_coverage(
        session, covered_position=position_demo_a, delegate_position=position_demo_z,
        valid_from=T0 + timedelta(days=2), valid_to=T0 + timedelta(days=5),
    )
    session.commit()

    item_demo_2 = att_svc.create_attention(
        session, source_domain=domain_demo, source_process_name=process_demo,
        reason="TEST/DEMO: integration demo attention, second case (during coverage)",
        priority=m.ATTENTION_PRIORITY_HIGH, scope=demo_context,
    )
    session.commit()
    att_svc.route_attention(session, item=item_demo_2, now=T0 + timedelta(days=3))
    session.commit()
    result.check(
        "18b. Integration demo: with temporary coverage active, a NEW Attention on the SAME Process routes to Z",
        item_demo_2.resolved_recipient_acting_identity_id == occupant_demo_z.id,
    )
    result.check(
        "18c. Integration demo: the FIRST Attention item (routed before coverage started) is unaffected",
        item_demo.resolved_recipient_acting_identity_id == occupant_demo_x.id,
    )
