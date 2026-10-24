# Bank unification — Phase 3 technical plan: one Bank, one engine, one operational database

Status: PLAN, not approved, nothing executed (2026-10-24). Prepared after Phases 0-2, the legacy WHY
consolidation (decisions 61-84) and decision 86. Facts below were measured on the local operational
database (read-only) and on isolated copies.

## 1. Starting point (measured)

| Item | Today |
|---|---|
| Interface | One: Bank on 5080, Guided Reconciliation tab = C-Bank (Phase 1) |
| Engines | Two. C-Bank (dry run, writes only `cbank.db`); old Bank paths still WRITE `bank_transaction_explanations` on import (two-pass planner, AI rules, WHO identification worker) |
| Operational DB | 3,299 movements, all CANONICAL, none excluded; 20 import files kept with matching SHA-256 |
| Old decisions | 5,343 explanations (819 HUMAN, 4,524 RULE); since the USAR catalog replacement they carry WHO and WHAT but **no WHY** |
| C-Bank store | 10 runs, 9 active C-Bank human decisions, 127 matched pairs, 6 AI investigations, 2 conversations |
| C-Bank result | 1,106 Reconciled, 2,193 Exceptions; idempotent; 0 human decisions replaced; 0 card payments posted twice |

## 2. Tables

**Reused as they are (no schema change):**

| Need | Table |
|---|---|
| Movements, raw rows, import files | `financial_transactions`, `raw_bank_transactions`, `bank_import_batches` |
| WHO / WHY / WHAT, groups, labels, associations, knowledge | `bank_occurrences`, `bank_transaction_reasons`, `bank_reason_groups`, `bank_accounting_classifications`, `bank_who_labels`, `bank_occurrence_labels`, `bank_occurrence_reason_associations`, `bank_who_knowledge` |
| Rules, profiles, versions, applications, rollback | `bank_ai_rules`, `bank_ai_rule_versions`, `bank_ai_rule_applications`, `bank_ai_rule_application_items` |
| Current decision per movement (WHO/WHY/WHAT, source, status, snapshots) | `bank_transaction_explanations` |
| Accounting subject vs management destination (decision 86), relationships | `bank_transaction_allocations` (`payer_legal_entity_id`, `economic_owner_legal_entity_id`, `intercompany_outcome`) |
| Matched transfers / card settlements | `financial_transaction_matches` (exists, empty) |
| AI investigations, conversations, profile proposals | `bank_flow_artifacts` (JSON payload; kinds INVESTIGATION / CONVERSATION next to CHAT, RUN, PREVIEW) |

**New tables really needed (one migration):**

| Table | Why |
|---|---|
| `bank_engine_runs` | one row per engine run: scope, Bank signature, code version, summary |
| `bank_engine_results` | one row per movement per run: status, exceptions, anomalies, per-field method and trace (JSON). The audit the old explanations do not hold; the Dashboard and Wizard read it |

**Constraint changes to verify in the same migration:** `bank_ai_rules.status` gains `PROPOSED`
(BANK_AI_PROFILE_PROPOSAL_001); `bank_transaction_explanations.decision_source` gains `ENGINE` if its check
constraint lists values (to be confirmed on the schema before writing the migration).

## 3. Migration of the C-Bank data

1. Freeze: stop automatic C-Bank runs; snapshot `rfone.db` and `cbank.db` (online backup API).
2. C-Bank human decisions (9) → a HUMAN explanation (and allocation when they carry a destination), only
   where the movement has no newer human decision in Bank; every conflict listed, none overwritten.
3. Matched pairs (127) → `financial_transaction_matches` (idempotent on the ordered pair).
4. AI investigations and conversations → `bank_flow_artifacts`.
5. Runs: not migrated; the first run of the unified engine is the new baseline (old runs stay in the frozen
   `cbank.db` for audit).
6. Engine results are NOT written to explanations in bulk: a movement's explanation changes only through the
   existing guarded application (preview, apply, rollback), never as a mass reclassification.

## 4. Knowledge, rules, profiles, labels

Nothing to copy: C-Bank already reads them from the operational DB. Versions, applications and rollback stay
in place. The 33 rule versions of the WHY consolidation and the provisional group are already there.

## 5. Retiring the old write paths (no deletion)

Behind one switch each, in this order, each verified on a copy:
1. import → two-pass planner writing explanations (`reconciliation_runner.imported`);
2. WHO identification worker writing WHOs and labels automatically after import (kept as proposals);
3. AI rule "apply to future" at import (rules stay; the engine evaluates them);
4. dead QUEUED import worker (`bank_import_worker`), already unreachable.
Reading pages stay. Old code paths are removed only after a full cycle without use.

## 6. Rollback

- Before the migration: the two snapshots; restore = stop server, put the snapshot back with the Local
  Environment tools, start.
- After: every explanation written by the engine goes through the application audit, so a run can be rolled
  back like an AI rule application; switches of §5 can be turned back on.

## 7. Integrity checks (all automated, before and after)

Row counts and content hashes of movements, raw rows and import files; explanations and allocations changed
only where an application says so; human decisions unchanged; every Reconciled movement has WHO, WHY, WHAT
from its WHY, the Source owner as accounting subject and an operation type; no provisional WHY Reconciled;
card pairs posted once; engine idempotent on two runs; `PRAGMA integrity_check`.

## 8. Prerequisites and decisions before Phase 3

1. Approve this plan and the single migration (§2).
2. WHAT for personal accounting (decision 86): personal Source with business WHAT (155 open movements) and
   Owner Personal WHYs mapped to the LLC equity account 3400 on personal Sources.
3. The pending rule decisions: vehicles (12 rules + EV), Emilia (#75), capitalization rule (#100), tolls (#67),
   WALMART profile (#17/#31), Amazon (#107), personal withdrawal, BANK DEPOSIT association.
4. Profile anomalies: TABLE TOP LINEN (#110, 43 open), CHASE (#89), 120 RPP (#119) without WHY;
   PUBLIX WHO conflict (#4 vs #11, 38 open); COSTCO/INSTACART conflict (#20/#48, 22 open).
5. Test hygiene: update or retire the obsolete tests already classified; switch background workers off in tests.
