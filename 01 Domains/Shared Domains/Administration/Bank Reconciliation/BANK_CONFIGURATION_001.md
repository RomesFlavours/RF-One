# Bank Configuration

**Task:** BANK_CONFIGURATION_001
**Status:** Implemented on `feature/bank-new-reconciliation` — schema, service, page, tests. Not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Migrations:** `e5b1d7c3a9f2` (revises `d4a8c2e6f1b3`), `f6c2e8a4b1d7` (COUNTERPARTY seed)
**UI specification:** the approved prototype `bank_configuration_prototype.html` (BANK_CONFIGURATION_PROTOTYPE_001)

---

## What it is

One page, `/bank/configuration`, where everything the Bank monthly work
relies on is maintained, in this order:

| # | Block | Canonical model |
|---|---|---|
| 1 | WHAT | `BankAccountingClassification` — P&L posting categories only (D11); P&L groups are the Group column |
| 2 | WHY | `BankTransactionReason` — exactly one WHAT each |
| 3 | WHO | `BankOccurrence` + possible WHYs (`BankOccurrenceReasonAssociation`), default WHY, entities served (`BankOccurrenceReportingEntity`), recognition rules (`BankRecognitionRule`) |
| 4 | Accounts & Cards | `PaymentInstrument` + card configuration |
| – | Support | Entities (`ReportingEntity`), source rules (`BankSourceInstrumentProfile`), control months (`BankReconciliationControlConfig`), card settlement (`BankCardSettlementAccount`), cardholder (`BankCardHolderAssignment`), deduplication recompute (action) |

Every business rule is in `rfone_data_store/bank_reconciliation/configuration.py`,
which calls the existing canonical services wherever one owns the rule.
The page and its routes (`03 Software/RF-One Web/bank_configuration_routes.py`)
only read forms and report the outcome.

## Product Owner decisions implemented

| | Decision |
|---|---|
| D1 | WHO → entities served uses **ReportingEntity** (also the future "For whom"). New table `bank_occurrence_reporting_entities`: one row per pair (unique), `active`, audit timestamps. It starts empty; nothing is inferred. |
| D2 | `bank_recognition_rules.transaction_reason_id` is **nullable**. A rule configured here is WHO-only: description scope, `determines_purpose = false`, no WHY. Existing rules keep their WHY. **WHO never determines WHY.** |
| D3 | Bank Account owning entity = `PaymentInstrument.legal_entity_id`, editable. Credit Card owning entity = **derived** from its settlement account, read-only; the card's own `legal_entity_id` is never used or changed here. To change it, change the settlement account. |
| D4 | No statement-type field: a new WHAT takes statement type and normal balance from its GROUP and is a plain POSTING account. A group that cannot supply them is refused. A WHAT never moves to a group of another statement. |
| D5 | A new WHO is of type `COUNTERPARTY` (not shown on the page). |
| D6 | Settlement and cardholder keep their history: each change opens a new period from its **Valid from** and closes the previous one, through `card_configuration`. |
| D7 | A new WHY gets a unique code generated from its name (existing UPPER_SNAKE convention, `_2`, `_3` on collision). Renaming never changes it. |
| D8 | Entities are shown and chosen by `ReportingEntity.name`. |
| D9 | The WHO block has a Search field: an immediate client-side filter on the WHO name. |
| D10 | `COUNTERPARTY` is system reference data, seeded idempotently by migration `f6c2e8a4b1d7` (by code; an existing row is left unchanged; never duplicated). |
| D11 | **WHAT means the canonical P&L category.** Balance Sheet accounts are never WHAT. The WHAT block and new WHYs use P&L WHAT only. An existing WHY that settles on a Balance Sheet destination keeps it, is shown as "Balance Sheet destination — <name>", and changes only when the operator explicitly chooses a P&L WHAT. Support lists the Balance Sheet destinations read-only (`canonical_catalog.accounting_destinations`, the same list the Classification page shows). |

## Rules worth knowing

* **Nothing is ever deleted.** A withdrawn WHY, entity or rule of a WHO is
  deactivated; the history stays readable.
* **Default WHY** must be one of the WHO's active possible WHYs; a WHO may
  have none at all (BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §20).
* **Recognition rules** match Exact, Contains or Prefix on the normalized
  description. One text cannot recognise two WHOs: a clash is refused.
  Rules are applied to FUTURE imports only — no retroactive or global
  re-application is performed from this page.
* **An account's Active state** is not edited here: opening and closing an
  instrument is recorded in Monthly Sources, as `service.update_payment_instrument` requires.
* **Only an active P&L WHAT** can be given to a WHY on this page; the
  canonical `classification._require_usable_what` still applies on top.
* Every change is BANK-gated, CSRF-protected, transactional, and returns to
  `/bank/configuration` at a section fixed by the route.

## Not in scope

The Reconciliation page is not connected (it remains the mock prototype).
No bulk retroactive application of WHO rules. No mapping of existing data.
