#!/usr/bin/env python
"""Economic Allocation foundation — BANK_ECONOMIC_ALLOCATION_FOUNDATION_001.

Proves, on a throwaway database, the distinction the whole task exists to
establish:

    BANK TRANSACTION    = the movement of money
    ECONOMIC ALLOCATION = what that movement means economically

Covered end to end: one transaction to one allocation and to three; the
exact-sum invariant and its refusal; the P&L reading allocations and never
the bank parent; WHY -> WHAT and WHY -> Balance Sheet destination;
allocations across several reporting entities; payer versus economic owner
and the intercompany Due From / Due To derived from them; personal
instruments that must never become fake LLCs; virtual reporting entities
that must never become real ones; and the consolidated P&L counting an
external cost exactly once.

Never touches AWS, RDS, the operational database, or a real bank file. No
historical data is imported and no invoice is read.
"""

from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import card_configuration
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import economic_allocation as alloc
from rfone_data_store.bank_reconciliation import economic_reporting as reporting
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import reporting_entity as entities
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

POSTING_DATE = date(2026, 3, 15)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    def raises(description: str, fn, expected_fragment: str) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — the point is that SOMETHING refused
            check(description, expected_fragment.lower() in str(exc).lower(), detail=str(exc))
        else:
            check(description, False, detail="nothing was raised")

    url = resolve_test_database_url("bank_economic_allocation")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            # =============================================================
            # Fixture — legal entities, instruments, catalog, entities
            # =============================================================
            wp = m.LegalEntity(legal_name="RF Winter Park, LLC", status="ACTIVE")
            md = m.LegalEntity(legal_name="RF Mount Dora, LLC", status="ACTIVE")
            gelati = m.LegalEntity(legal_name="RF Gelati, LLC", status="ACTIVE")
            aed = m.LegalEntity(legal_name="Angeli E Demoni, LLC", status="ACTIVE")
            s.add_all([wp, md, gelati, aed])
            s.flush()
            legal_entity_count_after_fixture = s.scalar(
                select(func.count(m.LegalEntity.id))
            )

            bank_wp = m.PaymentInstrument(
                instrument_type="BANK_ACCOUNT", display_name="WP Checking",
                legal_entity_id=wp.id, status="ACTIVE",
            )
            bank_gelati = m.PaymentInstrument(
                instrument_type="BANK_ACCOUNT", display_name="Gelati Checking",
                legal_entity_id=gelati.id, status="ACTIVE",
            )
            bank_personal = m.PaymentInstrument(
                instrument_type="BANK_ACCOUNT", display_name="Owner Personal Checking",
                legal_entity_id=None, status="ACTIVE",
            )
            s.add_all([bank_wp, bank_gelati, bank_personal])
            s.flush()

            card_gelati = m.PaymentInstrument(
                instrument_type="CREDIT_CARD", display_name="Gelati Card",
                legal_entity_id=gelati.id, last_four="1111", status="ACTIVE",
            )
            card_personal = m.PaymentInstrument(
                instrument_type="CREDIT_CARD", display_name="Personal Card",
                legal_entity_id=None, last_four="2222", status="ACTIVE",
            )
            card_unconfigured = m.PaymentInstrument(
                instrument_type="CREDIT_CARD", display_name="Unconfigured Card",
                legal_entity_id=wp.id, last_four="3333", status="ACTIVE",
            )
            s.add_all([card_gelati, card_personal, card_unconfigured])
            s.flush()

            card_configuration.assign_settlement_account(
                s, credit_card_payment_instrument_id=card_gelati.id,
                settlement_bank_account_id=bank_gelati.id, valid_from=date(2026, 1, 1),
            )
            card_configuration.assign_settlement_account(
                s, credit_card_payment_instrument_id=card_personal.id,
                settlement_bank_account_id=bank_personal.id, valid_from=date(2026, 1, 1),
            )
            # `card_unconfigured` deliberately gets no settlement account.

            # The canonical accounting catalog and the canonical WHY
            # vocabulary are already seeded by migrations b8d3f1a72c64 and
            # c4a9e7d21b56. This test READS them rather than inventing a
            # parallel chart of accounts — the codes below are exactly the
            # ones the task's own worked examples use.
            food_what = _what(s, "5100")
            togo_what = _what(s, "5300")
            supplies_what = _what(s, "7830")
            cc_payable = _what(s, "2500")
            due_from = _what(s, m.DUE_FROM_RELATED_PARTIES_CODE)
            due_to = _what(s, m.DUE_TO_RELATED_PARTIES_CODE)
            check(
                "the intercompany control accounts already exist in the canonical catalog",
                due_from is not None
                and due_to is not None
                and due_from.statement_type == due_to.statement_type == "BALANCE_SHEET",
            )

            why_food = _why(s, "FOOD_PURCHASES")
            why_togo = _why(s, "TO_GO_PACKAGING")
            why_supplies = _why(s, "RESTAURANT_OPERATING_SUPPLIES")
            why_cc_settlement = _why(s, "CREDIT_CARD_SETTLEMENT")
            check(
                "the canonical WHY vocabulary already resolves to the expected accounts",
                why_food.accounting_classification_id == food_what.id
                and why_togo.accounting_classification_id == togo_what.id
                and why_supplies.accounting_classification_id == supplies_what.id
                and why_cc_settlement.accounting_classification_id == cc_payable.id,
            )

            # =============================================================
            # A. Reporting perimeter and reporting entities
            # =============================================================
            group = entities.create_reporting_group(
                s, code="RF_GROUP", name="RF Corporate Perimeter",
            )
            re_wp = entities.create_legal_entity_reporting_entity(
                s, code="RE_WP", name="RF Winter Park", legal_entity_id=wp.id,
                reporting_group_id=group.id,
            )
            re_md = entities.create_legal_entity_reporting_entity(
                s, code="RE_MD", name="RF Mount Dora", legal_entity_id=md.id,
                reporting_group_id=group.id,
            )
            re_gelati = entities.create_legal_entity_reporting_entity(
                s, code="RE_GELATI", name="RF Gelati", legal_entity_id=gelati.id,
                reporting_group_id=group.id,
            )
            re_aed = entities.create_legal_entity_reporting_entity(
                s, code="RE_AED", name="Angeli E Demoni", legal_entity_id=aed.id,
                reporting_group_id=group.id,
            )
            legal_entities_before_virtual = s.scalar(select(func.count(m.LegalEntity.id)))
            re_virtual = entities.create_virtual_entity(
                s, code="RE_BRAND_LINE", name="Gelato Brand Line",
                reporting_group_id=group.id,
                description="A management reporting entity. Not an LLC.",
            )
            legal_entities_after_virtual = s.scalar(select(func.count(m.LegalEntity.id)))

            # [16] a virtual entity creates no LegalEntity
            check(
                "[16] creating a VIRTUAL reporting entity creates no LegalEntity",
                legal_entities_after_virtual == legal_entities_before_virtual
                == legal_entity_count_after_fixture,
                detail=f"{legal_entities_before_virtual} -> {legal_entities_after_virtual}",
            )
            check(
                "[16] a VIRTUAL reporting entity has no legal entity reference at all",
                re_virtual.legal_entity_id is None and re_virtual.is_virtual,
            )

            # [17] a perimeter contains N reporting entities
            members = entities.entities_in_group(s, reporting_group_id=group.id)
            check(
                "[17] one reporting perimeter contains N reporting entities",
                len(members) == 5,
                detail=f"{len(members)} members",
            )
            check(
                "[17] the perimeter mixes LEGAL and VIRTUAL entities",
                sum(1 for e in members if e.is_legal) == 4
                and sum(1 for e in members if e.is_virtual) == 1,
            )

            # [18] a LEGAL reporting entity points at a real LegalEntity
            check(
                "[18] a LEGAL reporting entity resolves to a real LegalEntity",
                re_md.is_legal
                and re_md.legal_entity is not None
                and re_md.legal_entity.legal_name == "RF Mount Dora, LLC",
            )

            # [19] zero or two LegalEntity behind a LEGAL reporting entity
            raises(
                "[19] a LEGAL reporting entity with no LegalEntity is refused",
                lambda: entities.create_legal_entity_reporting_entity(
                    s, code="RE_NOWHERE", name="Nowhere", legal_entity_id=None,
                ),
                "must name exactly one real Legal Entity",
            )
            raises(
                "[19] a second LEGAL reporting entity for the same LegalEntity is refused",
                lambda: entities.create_legal_entity_reporting_entity(
                    s, code="RE_MD_AGAIN", name="Mount Dora again", legal_entity_id=md.id,
                ),
                "already represented",
            )
            raises(
                "[19] a LEGAL reporting entity naming a non-existent LegalEntity is refused",
                lambda: entities.create_legal_entity_reporting_entity(
                    s, code="RE_GHOST", name="Ghost", legal_entity_id=987654,
                ),
                "does not exist",
            )
            # And the database refuses it too, not merely the service.
            savepoint = s.begin_nested()
            try:
                s.add(
                    m.ReportingEntity(
                        code="RE_RAW_BAD", name="Raw bad", entity_type="LEGAL",
                        legal_entity_id=None, status="ACTIVE",
                    )
                )
                s.flush()
                db_refused_legal_without_entity = False
            except Exception:
                db_refused_legal_without_entity = True
            finally:
                # The SAVEPOINT, not the whole transaction — rolling back
                # the session here would discard the entire fixture.
                savepoint.rollback()
            check(
                "[19] the database itself refuses a LEGAL reporting entity with no LegalEntity",
                db_refused_legal_without_entity,
            )

            savepoint = s.begin_nested()
            try:
                s.add(
                    m.ReportingEntity(
                        code="RE_RAW_VIRTUAL_LLC", name="Virtual wearing an LLC",
                        entity_type="VIRTUAL", legal_entity_id=md.id, status="ACTIVE",
                    )
                )
                s.flush()
                db_refused_virtual_with_entity = False
            except Exception:
                db_refused_virtual_with_entity = True
            finally:
                savepoint.rollback()
            check(
                "[16] the database itself refuses a VIRTUAL entity pointing at a LegalEntity",
                db_refused_virtual_with_entity,
            )

            # =============================================================
            # B. One transaction -> one allocation
            # =============================================================
            gordon = _transaction(s, bank_wp, -100_000, "GORDON FOOD SERVICE")
            single = alloc.set_allocations(
                s,
                financial_transaction_id=gordon.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-100_000,
                        reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_food.id,
                    )
                ],
            )
            check("[1] a single-category transaction is one allocation", len(single) == 1)
            check(
                "[1] the single allocation carries the full parent amount",
                single[0].amount_minor == gordon.amount_minor == -100_000,
            )
            # [6] WHY -> WHAT
            check(
                "[6] the allocation's WHAT is derived from its WHY",
                single[0].accounting_classification_code_snapshot == "5100"
                and single[0].accounting_statement_type_snapshot == "PROFIT_LOSS"
                and single[0].is_profit_loss,
            )
            # [8] one WP allocation
            check(
                "[8] one allocation belongs to RF Winter Park",
                single[0].reporting_entity_id == re_wp.id
                and single[0].reporting_entity_name_snapshot == "RF Winter Park",
            )
            # [11] payer == economic owner
            check(
                "[11] payer equal to economic owner produces no intercompany position",
                single[0].intercompany_outcome == m.INTERCOMPANY_NONE
                and single[0].intercompany_due_from_code_snapshot is None
                and single[0].intercompany_due_to_code_snapshot is None,
                detail=str(single[0].intercompany_outcome),
            )

            # =============================================================
            # C. One transaction -> three allocations
            # =============================================================
            cheney = _transaction(s, card_gelati, -200_000, "CHENEY BROTHERS")
            split = alloc.set_allocations(
                s,
                financial_transaction_id=cheney.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-150_000, reporting_entity_id=re_gelati.id,
                        transaction_reason_id=why_food.id,
                    ),
                    alloc.AllocationSpec(
                        amount_minor=-30_000, reporting_entity_id=re_gelati.id,
                        transaction_reason_id=why_togo.id,
                    ),
                    alloc.AllocationSpec(
                        amount_minor=-20_000, reporting_entity_id=re_gelati.id,
                        transaction_reason_id=why_supplies.id,
                    ),
                ],
            )
            check("[2] a multi-category transaction is three allocations", len(split) == 3)
            check(
                "[2] the parent stays exactly one bank transaction",
                s.scalar(
                    select(func.count(m.FinancialTransaction.id)).where(
                        m.FinancialTransaction.payment_instrument_id == card_gelati.id
                    )
                )
                == 1,
            )
            check(
                "[2] the three allocations resolve to three different accounts",
                {a.accounting_classification_code_snapshot for a in split}
                == {"5100", "5300", "7830"},
            )

            # [3] sum equals parent
            state = alloc.allocation_state(s, financial_transaction_id=cheney.id)
            check(
                "[3] the allocations sum exactly to the parent transaction",
                state.allocated_amount_minor == cheney.amount_minor == -200_000
                and state.is_balanced
                and state.difference_minor == 0,
            )

            # [4] a different sum is refused
            raises(
                "[4] an allocation set that does not sum to the parent is refused",
                lambda: alloc.set_allocations(
                    s,
                    financial_transaction_id=cheney.id,
                    specs=[
                        alloc.AllocationSpec(
                            amount_minor=-150_000, reporting_entity_id=re_gelati.id,
                            transaction_reason_id=why_food.id,
                        ),
                        alloc.AllocationSpec(
                            amount_minor=-30_000, reporting_entity_id=re_gelati.id,
                            transaction_reason_id=why_togo.id,
                        ),
                    ],
                ),
                "not absorbed",
            )
            check(
                "[4] the refusal left the existing balanced allocations untouched",
                len(alloc.get_allocations(s, financial_transaction_id=cheney.id)) == 3,
            )
            raises(
                "[4] one cent short is refused exactly like a large difference",
                lambda: alloc.set_allocations(
                    s,
                    financial_transaction_id=gordon.id,
                    specs=[
                        alloc.AllocationSpec(
                            amount_minor=-99_999, reporting_entity_id=re_wp.id,
                            transaction_reason_id=why_food.id,
                        )
                    ],
                ),
                "must match its bank transaction exactly",
            )

            # =============================================================
            # D. Multi-entity allocation and the derived intercompany
            # =============================================================
            multi_entity = _transaction(s, card_gelati, -200_000, "MIXED SUPPLIER")
            multi = alloc.set_allocations(
                s,
                financial_transaction_id=multi_entity.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-120_000, reporting_entity_id=re_aed.id,
                        transaction_reason_id=why_food.id,
                    ),
                    alloc.AllocationSpec(
                        amount_minor=-50_000, reporting_entity_id=re_md.id,
                        transaction_reason_id=why_food.id,
                    ),
                    alloc.AllocationSpec(
                        amount_minor=-30_000, reporting_entity_id=re_md.id,
                        transaction_reason_id=why_supplies.id,
                    ),
                ],
            )
            # [9] an MD allocation, [10] WP + MD on one transaction
            check(
                "[9] an allocation belongs to RF Mount Dora",
                any(a.reporting_entity_id == re_md.id for a in multi),
            )
            check(
                "[10] one transaction carries allocations for two different entities",
                len({a.reporting_entity_id for a in multi}) == 2,
            )

            wp_md_transaction = _transaction(s, bank_wp, -80_000, "SHARED SUPPLIER")
            wp_md = alloc.set_allocations(
                s,
                financial_transaction_id=wp_md_transaction.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-50_000, reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_food.id,
                    ),
                    alloc.AllocationSpec(
                        amount_minor=-30_000, reporting_entity_id=re_md.id,
                        transaction_reason_id=why_food.id,
                    ),
                ],
            )
            check(
                "[10] a Winter Park and a Mount Dora allocation share one bank transaction",
                {a.reporting_entity_id for a in wp_md} == {re_wp.id, re_md.id},
            )

            # [12] payer != economic owner -> Due From / Due To derived
            gelati_pays_md = _transaction(s, bank_gelati, -50_000, "MATERIAL FOR MOUNT DORA")
            cross = alloc.set_allocations(
                s,
                financial_transaction_id=gelati_pays_md.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-50_000, reporting_entity_id=re_md.id,
                        transaction_reason_id=why_food.id,
                    )
                ],
            )[0]
            check(
                "[12] a cross-entity allocation is recognized as intercompany",
                cross.intercompany_outcome == m.INTERCOMPANY_CROSS_ENTITY and cross.is_cross_entity,
            )
            check(
                "[12] the payer is RF Gelati and the economic owner is RF Mount Dora",
                cross.payer_legal_entity_id == gelati.id
                and cross.economic_owner_legal_entity_id == md.id
                and cross.payer_kind == m.PAYER_KIND_LEGAL_ENTITY,
            )
            check(
                "[12] Due From / Due To are derived, not chosen by an operator",
                cross.intercompany_due_from_code_snapshot == due_from.code == "1610"
                and cross.intercompany_due_to_code_snapshot == due_to.code == "2710",
            )
            check(
                "[12] the derivation is a pure function of payer and economic owner",
                alloc.derive_intercompany(
                    payer=alloc.PayerResolution(
                        kind=m.PAYER_KIND_LEGAL_ENTITY, legal_entity_id=gelati.id,
                        legal_entity_name="RF Gelati, LLC", explanation="",
                    ),
                    economic_owner_legal_entity_id=md.id,
                    economic_owner_is_virtual=False,
                ).outcome
                == m.INTERCOMPANY_CROSS_ENTITY,
            )

            # A card paying for its own entity is NOT intercompany, even
            # though the card and the settlement account are different rows.
            check(
                "[11] a card settling to its own entity's account is not intercompany",
                all(a.intercompany_outcome == m.INTERCOMPANY_NONE for a in split),
            )

            # =============================================================
            # E. Personal instruments and virtual entities
            # =============================================================
            # [22] a personal instrument never fabricates an LLC intercompany
            personal_txn = _transaction(s, card_personal, -30_000, "PERSONAL CARD BUYS SUPPLIES")
            personal = alloc.set_allocations(
                s,
                financial_transaction_id=personal_txn.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-30_000, reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_supplies.id,
                    )
                ],
            )[0]
            # BANK_INVOICE_EVIDENCE_COLLABORATION_001 §19 answered what this
            # foundation had left explicitly open: the business side of a
            # personal payer's business expense is 2710 Due To Related
            # Parties by default. What has NOT changed, and is what this
            # check is really about, is that no LLC-to-LLC intercompany
            # position is fabricated where there is no second LLC.
            check(
                "[22] a personal instrument produces no LLC-to-LLC intercompany",
                personal.intercompany_outcome == m.INTERCOMPANY_PERSONAL_PAYER_DUE_TO
                and personal.intercompany_due_from_code_snapshot is None
                and personal.intercompany_due_to_code_snapshot
                == m.DUE_TO_RELATED_PARTIES_CODE,
                detail=str(personal.intercompany_outcome),
            )
            check(
                "[22] the personal payer is named as personal, not as an invented entity",
                personal.payer_kind == m.PAYER_KIND_PERSONAL
                and personal.payer_legal_entity_id is None,
            )
            check(
                "[22] the economic allocation itself is still correct and complete",
                personal.reporting_entity_id == re_wp.id
                and personal.accounting_classification_code_snapshot == "7830"
                and personal.is_complete,
            )
            check(
                "[22] the business records that it owes the individual back",
                "owes the individual back" in (personal.intercompany_notes or ""),
                detail=str(personal.intercompany_notes),
            )
            check(
                "[22] no LegalEntity was created to represent the personal instrument",
                s.scalar(select(func.count(m.LegalEntity.id))) == legal_entity_count_after_fixture,
            )

            # An unconfigured card is reported, never guessed.
            unconfigured_txn = _transaction(s, card_unconfigured, -10_000, "UNCONFIGURED CARD")
            unresolved = alloc.set_allocations(
                s,
                financial_transaction_id=unconfigured_txn.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-10_000, reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_supplies.id,
                    )
                ],
            )[0]
            check(
                "an unconfigured card's payer is reported as unknown, not guessed from the card",
                unresolved.payer_kind == m.PAYER_KIND_UNRESOLVED
                and unresolved.intercompany_outcome == m.INTERCOMPANY_NOT_DERIVABLE
                and unresolved.payer_legal_entity_id is None,
            )

            # [15] a virtual entity can receive an allocation
            virtual_txn = _transaction(s, bank_gelati, -45_000, "BRAND LINE MARKETING")
            virtual_alloc = alloc.set_allocations(
                s,
                financial_transaction_id=virtual_txn.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-45_000, reporting_entity_id=re_virtual.id,
                        transaction_reason_id=why_supplies.id,
                    )
                ],
            )[0]
            check(
                "[15] a VIRTUAL reporting entity receives an allocation",
                virtual_alloc.reporting_entity_id == re_virtual.id and virtual_alloc.is_complete,
            )
            check(
                "[15] a virtual owner creates no intercompany position — it is not a person",
                virtual_alloc.intercompany_outcome == m.INTERCOMPANY_NONE
                and virtual_alloc.economic_owner_legal_entity_id is None,
            )

            # =============================================================
            # F. Non-P&L WHY, incomplete allocations, and status separation
            # =============================================================
            # [7] a non-P&L WHY resolves to a Balance Sheet destination
            cc_payment = _transaction(s, bank_wp, -500_000, "CHASE CARD PAYMENT")
            bs_alloc = alloc.set_allocations(
                s,
                financial_transaction_id=cc_payment.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-500_000, reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_cc_settlement.id,
                    )
                ],
            )[0]
            check(
                "[7] a non-P&L WHY resolves to a Balance Sheet destination",
                bs_alloc.accounting_statement_type_snapshot == "BALANCE_SHEET"
                and bs_alloc.accounting_classification_code_snapshot == "2500",
            )
            check(
                "[7] a Balance Sheet allocation has no WHAT and is not a P&L line",
                not bs_alloc.is_profit_loss,
            )

            # [20] an incomplete allocation is not accounting-closed
            pending_txn = _transaction(s, bank_wp, -40_000, "AWAITING INVOICE")
            pending = alloc.set_allocations(
                s,
                financial_transaction_id=pending_txn.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-40_000, reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_food.id,
                        status=alloc.PENDING_EVIDENCE,
                    )
                ],
            )[0]
            pending_state = alloc.allocation_state(
                s, financial_transaction_id=pending_txn.id
            )
            check(
                "[20] an allocation awaiting evidence is not accounting-closed",
                not pending.is_complete
                and pending_state.status == alloc.PENDING_EVIDENCE
                and not pending_state.is_accounting_closed,
            )
            check(
                "[20] the pending allocation still balances its parent exactly",
                pending_state.is_balanced,
            )
            check(
                "[20] a refused restatement leaves the previous allocations in place",
                len(alloc.get_allocations(s, financial_transaction_id=pending_txn.id)) == 1,
            )
            raises(
                "[20] a COMPLETE allocation with no reporting entity is refused",
                lambda: alloc.set_allocations(
                    s,
                    financial_transaction_id=pending_txn.id,
                    specs=[
                        alloc.AllocationSpec(
                            amount_minor=-40_000, reporting_entity_id=None,
                            transaction_reason_id=why_food.id, status=alloc.COMPLETE,
                        )
                    ],
                ),
                "must say who it is for",
            )
            raises(
                "[20] a COMPLETE allocation with no WHY is refused",
                lambda: alloc.set_allocations(
                    s,
                    financial_transaction_id=pending_txn.id,
                    specs=[
                        alloc.AllocationSpec(
                            amount_minor=-40_000, reporting_entity_id=re_wp.id,
                            transaction_reason_id=None, status=alloc.COMPLETE,
                        )
                    ],
                ),
                "must have a WHY",
            )

            check(
                "[20] the pending allocation survived both refused restatements intact",
                len(alloc.get_allocations(s, financial_transaction_id=pending_txn.id)) == 1
                and alloc.get_allocations(s, financial_transaction_id=pending_txn.id)[0].status
                == alloc.PENDING_EVIDENCE,
            )

            # [21] a canonical transaction with a still-pending allocation
            pending_txn.accounting_status = "CANONICAL"
            s.flush()
            check(
                "[21] a transaction is financially CANONICAL while its allocation stays pending",
                pending_txn.accounting_status == "CANONICAL"
                and alloc.allocation_state(
                    s, financial_transaction_id=pending_txn.id
                ).status
                == alloc.PENDING_EVIDENCE,
            )
            unallocated_txn = _transaction(s, bank_wp, -12_000, "NOT YET DECIDED")
            unallocated_txn.accounting_status = "CANONICAL"
            s.flush()
            unallocated_state = alloc.allocation_state(
                s, financial_transaction_id=unallocated_txn.id
            )
            check(
                "[21] a canonical transaction with no allocation at all is UNALLOCATED, not broken",
                unallocated_state.status == alloc.UNALLOCATED
                and unallocated_state.is_balanced
                and not unallocated_state.is_accounting_closed,
            )

            # =============================================================
            # G. The P&L is driven by allocations, never by bank parents
            # =============================================================
            # [5] a parent carrying its own P&L classification is still
            # never counted: give one an explicit explanation snapshot.
            parent_classified = _transaction(s, bank_wp, -70_000, "PARENT WITH OWN WHAT")
            explanation = m.BankTransactionExplanation(
                financial_transaction_id=parent_classified.id,
                transaction_reason_id=why_food.id,
                decision_source="HUMAN",
                decision_status="HUMAN_CONFIRMED",
                accounting_classification_id=food_what.id,
                accounting_classification_code_snapshot="5100",
                accounting_classification_name_snapshot="Food Purchases",
                accounting_statement_type_snapshot="PROFIT_LOSS",
                what_label_snapshot="5100 — Food Purchases",
            )
            s.add(explanation)
            s.flush()
            parent_classified.explanation_id = explanation.id
            s.flush()
            alloc.set_allocations(
                s,
                financial_transaction_id=parent_classified.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-70_000, reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_food.id,
                    )
                ],
            )

            wp_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=re_wp.id)
            # WP allocations: gordon -100,000 (5100), wp_md -50,000 (5100),
            # personal -30,000 (7830), unconfigured -10,000 (7830),
            # parent_classified -70,000 (5100). The 2500 Balance Sheet line
            # and the PENDING one must not appear.
            check(
                "[5] the bank parent's own P&L classification is not counted",
                wp_pl.line_for("5100") is not None
                and wp_pl.line_for("5100").amount_minor == -220_000,
                detail=str(wp_pl.line_for("5100")),
            )
            check(
                "[5] the parent row would have doubled 5100 had it been read",
                wp_pl.line_for("5100").amount_minor != -290_000,
            )
            check(
                "[5] the report knows which transactions carry a competing parent decision",
                parent_classified.id
                in reporting.transactions_with_competing_parent_classification(s),
            )
            check(
                "[7] a Balance Sheet allocation never appears in the P&L",
                wp_pl.line_for("2500") is None,
            )
            check(
                "[20] a pending allocation is absent from the P&L rather than half-counted",
                wp_pl.line_for("5100").amount_minor == -220_000
                and pending.amount_minor == -40_000,
            )
            check(
                "[8] the Winter Park P&L totals only what Winter Park economically bore",
                wp_pl.total_minor == -260_000,
                detail=str(wp_pl.total_minor),
            )

            md_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=re_md.id)
            # MD: multi -50,000 (5100) -30,000 (7830), wp_md -30,000 (5100),
            # cross-entity -50,000 (5100). Total -160,000.
            check(
                "[9] the Mount Dora P&L contains what Mount Dora bore, whoever paid",
                md_pl.total_minor == -160_000,
                detail=str(md_pl.total_minor),
            )

            gelati_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=re_gelati.id)
            # Gelati bore only the Cheney split: -200,000. The $500 it paid
            # for Mount Dora is NOT its expense, and the brand-line marketing
            # it paid belongs to the virtual entity.
            check(
                "[13] paying for another entity does not put the cost in the payer's P&L",
                gelati_pl.total_minor == -200_000,
                detail=str(gelati_pl.total_minor),
            )
            check(
                "[13] the cross-entity cost appears once, on the economic owner",
                any(
                    line.code == "5100" for line in md_pl.lines
                )
                and gelati_pl.line_for("5100").amount_minor == -150_000,
            )

            virtual_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=re_virtual.id)
            check(
                "[15] a VIRTUAL reporting entity has its own management P&L",
                virtual_pl.total_minor == -45_000 and virtual_pl.scope_kind == "REPORTING_ENTITY",
                detail=str(virtual_pl.total_minor),
            )

            # [14] consolidated counts each external cost exactly once
            consolidated = reporting.consolidated_profit_and_loss(
                s, reporting_group_id=group.id,
            )
            aed_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=re_aed.id)
            sum_of_entities = (
                wp_pl.total_minor
                + md_pl.total_minor
                + gelati_pl.total_minor
                + aed_pl.total_minor
                + virtual_pl.total_minor
            )
            check(
                "[14] the consolidated P&L equals the sum of its entities, with no double count",
                consolidated.total_minor == sum_of_entities,
                detail=f"{consolidated.total_minor} vs {sum_of_entities}",
            )
            check(
                "[14] the cross-entity cost appears exactly once in the consolidated P&L",
                consolidated.allocation_count
                == s.scalar(
                    select(func.count(m.BankTransactionAllocation.id)).where(
                        m.BankTransactionAllocation.status == m.ALLOCATION_COMPLETE,
                        m.BankTransactionAllocation.accounting_statement_type_snapshot
                        == "PROFIT_LOSS",
                    )
                ),
                detail=str(consolidated.allocation_count),
            )

            # [13] the intercompany position is Balance Sheet, not a second expense
            positions = reporting.intercompany_positions(s)
            by_pair = {
                (p.payer_legal_entity_id, p.owner_legal_entity_id): p for p in positions
            }
            check(
                "[13] a Due From / Due To position exists for every cross-entity payer/owner pair",
                set(by_pair) == {(gelati.id, md.id), (gelati.id, aed.id), (wp.id, md.id)},
                detail=str(sorted(by_pair)),
            )
            check(
                "[13] the Gelati -> Mount Dora position aggregates all three of its allocations",
                by_pair[(gelati.id, md.id)].amount_minor == -130_000
                and by_pair[(gelati.id, md.id)].allocation_count == 3,
                detail=str(by_pair[(gelati.id, md.id)]),
            )
            check(
                "[13] Winter Park paying for Mount Dora creates its own separate position",
                by_pair[(wp.id, md.id)].amount_minor == -30_000,
            )
            check(
                "[13] the intercompany positions use Balance Sheet accounts only",
                all(p.due_from_code == "1610" and p.due_to_code == "2710" for p in positions),
            )
            check(
                "[13] every intercompany amount is mirrored by an allocation, never doubled",
                sum(p.amount_minor for p in positions)
                == s.scalar(
                    select(func.sum(m.BankTransactionAllocation.amount_minor)).where(
                        m.BankTransactionAllocation.intercompany_outcome
                        == m.INTERCOMPANY_CROSS_ENTITY,
                        m.BankTransactionAllocation.status == m.ALLOCATION_COMPLETE,
                    )
                ),
            )
            check(
                "[13] the intercompany position is absent from every P&L",
                all(
                    line.code not in ("1610", "2710")
                    for report in (wp_pl, md_pl, gelati_pl, consolidated)
                    for line in report.lines
                ),
            )

            # =============================================================
            # H. No regression in the existing WHO / WHY / WHAT model
            # =============================================================
            # [23] the existing reconciliation decision is untouched by
            # everything above.
            current = recognition.get_current_explanation(
                s, financial_transaction_id=parent_classified.id,
            )
            check(
                "[23] the existing WHO/WHY/WHAT decision row is unchanged by allocation work",
                current is not None
                and current.id == explanation.id
                and current.transaction_reason_id == why_food.id
                and current.accounting_classification_code_snapshot == "5100"
                and current.decision_status == "HUMAN_CONFIRMED",
            )
            check(
                "[23] allocations add no column to, and no row in, the explanation table",
                s.scalar(select(func.count(m.BankTransactionExplanation.id))) == 1,
            )
            check(
                "[23] the WHY -> WHAT catalog resolution is unchanged",
                why_food.is_profit_loss
                and why_food.what is not None
                and why_food.what.code == "5100"
                and why_cc_settlement.accounting_destination is not None
                and why_cc_settlement.accounting_destination.code == "2500",
            )

            # Restating a transaction's allocations replaces them cleanly.
            restated = alloc.set_allocations(
                s,
                financial_transaction_id=gordon.id,
                specs=[
                    alloc.AllocationSpec(
                        amount_minor=-60_000, reporting_entity_id=re_wp.id,
                        transaction_reason_id=why_food.id,
                    ),
                    alloc.AllocationSpec(
                        amount_minor=-40_000, reporting_entity_id=re_md.id,
                        transaction_reason_id=why_food.id,
                    ),
                ],
            )
            check(
                "restating a transaction's allocations replaces the whole set atomically",
                len(restated) == 2
                and len(alloc.get_allocations(s, financial_transaction_id=gordon.id)) == 2,
            )
            cleared = alloc.clear_allocations(s, financial_transaction_id=gordon.id)
            check(
                "clearing allocations returns a transaction to UNALLOCATED",
                cleared == 2
                and alloc.allocation_state(
                    s, financial_transaction_id=gordon.id
                ).status
                == alloc.UNALLOCATED,
            )
            check(
                "clearing allocations leaves the bank transaction itself untouched",
                s.get(m.FinancialTransaction, gordon.id).amount_minor == -100_000,
            )

            exceptions = reporting.allocation_exceptions(s)
            check(
                "unsettled transactions are reported rather than silently missing",
                any(e.financial_transaction_id == unallocated_txn.id for e in exceptions)
                and any(e.financial_transaction_id == pending_txn.id for e in exceptions),
            )

            s.rollback()

    finally:
        engine.dispose()

    print()
    print(f"Checks passed: {len(checks_passed)}")
    print(f"Checks failed: {len(checks_failed)}")
    if checks_failed:
        print()
        for description in checks_failed:
            print(f"  FAILED  {description}")
        return 1
    for description in checks_passed:
        print(f"  ok  {description}")
    return 0


def _what(session, code: str) -> "m.BankAccountingClassification":
    """One canonical account, read from the seeded catalog by its stable
    code. Absence is a failure of the fixture, never a licence to create a
    replacement account."""
    row = session.scalar(
        select(m.BankAccountingClassification).where(
            m.BankAccountingClassification.code == code
        )
    )
    if row is None:
        raise AssertionError(f"Canonical account {code} is missing from the seeded catalog.")
    return row


def _why(session, code: str) -> "m.BankTransactionReason":
    """One canonical WHY, read from the seeded vocabulary by its code."""
    row = session.scalar(
        select(m.BankTransactionReason).where(m.BankTransactionReason.code == code)
    )
    if row is None:
        raise AssertionError(f"Canonical WHY {code} is missing from the seeded vocabulary.")
    return row


def _transaction(
    session, instrument: "m.PaymentInstrument", amount_minor: int, description: str,
) -> "m.FinancialTransaction":
    """A bank movement, in the canonical sign convention: money out is
    negative, exactly as `parsers.to_minor_units` produces it."""
    transaction = m.FinancialTransaction(
        payment_instrument_id=instrument.id,
        posting_date=POSTING_DATE,
        transaction_date=POSTING_DATE,
        description_original=description,
        amount_minor=amount_minor,
        status="COMPLETED",
        classification="UNKNOWN",
    )
    session.add(transaction)
    session.flush()
    return transaction


if __name__ == "__main__":
    sys.exit(main())
