# Bank — removal of the old (non-AI) rule system and reset to the post-import state (BANK_RULES_RESET_001)

Product Owner decision, 2026-10-12. Classification in Bank is now done only by **AI Rules** and by a person
(manual reconciliation). Executed on the local working database (5080) with no backup, by explicit instruction.

## Removed (code)

| What | Where |
|---|---|
| The "Rules" page (`GET /bank/classification`) and its menu tab | `bank_routes.py`, `templates/bank_classification.html`, `_bank_classification_learning.html`, `_bank_macros.html` |
| Simple WHO Rule: apply / manual-only / disable, the "Rule" button and modal on Review | `bank_who_rule_routes.py` (only the two read-only WHO lookups remain, used by the "new WHO" dialog), `_bank_who_rule_modal.html`, `_bank_who_rule_result.html`, `static/js/bank-who-rule.js` |
| General Rules routes and script | `bank_general_rule_routes.py`, `static/js/bank-general-rules.js` |
| Classification Learning routes (discover / backtest / approve…) | `bank_learning_routes.py` |
| Reconciliation Standards as a feature: "Standard" row action, "Save as New Standard", `POST /bank/reconciliation/<id>/standard` | `bank_reconciliation_routes.py`, `templates/bank_reconciliation.html` |
| Non-AI execution at import and at reprocess: learned / structural recognition (`recognition.deduce_for_transaction`, `redecide_for_transaction`), General Rules, WHY rules, Standards | `bank_reconciliation/service.py` |

At import, the only automatic classification left is the operative AI rules enabled "Per il futuro". The service
modules (`who_rules`, `general_rules`, `why_rules`, `recognition`, `reconciliation_standards`,
`pattern_discovery`…) remain as libraries — the AI engine and the manual reconciliation use parts of them — but no
page, route or import step executes their rules. Kept by decision: a manual confirmation still records a learned
recognition rule (Configuration > WHO shows them); such rules are no longer applied anywhere.

## Reset (data, one transaction)

Emptied: decisions (`bank_transaction_explanations`), allocations / confirmations, Reconciliation Standards,
learned recognition rules, WHO recognitions, General Rules, WHY rules, learning runs and suggestions, the WHO
catalog (WHO, aliases, WHY associations, For Whom links, suppliers links), the WHY catalog (WHY, export mappings,
WHY groups), the AI rules' provenance ("settled by AI": applications and their items), every AI preview and the
AI batch cache. Every movement: `explanation_id` NULL, `review_status` REQUIRES_REVIEW, `classification` UNKNOWN.
AI interpretations that name a WHO or WHY of the catalog (fixed WHO / WHY) were invalidated (cache key retired):
they are interpreted again on the next Preview.

Kept unchanged: Sources (payment instruments, card settings), import batches, files, raw rows, every original
field of every movement, the chart of accounts (WHAT), reporting entities, WHO types, AI rules, versions, drafts
and instructions.

Verified in the same transaction (rolled back otherwise): same number of movements; every original field
(including `updated_at`) unchanged; no movement with a decision; every movement to classify; WHO and WHY catalogs
empty; no decision, allocation, Standard, old rule or settled-by-AI provenance left; `PRAGMA foreign_key_check`
empty; every other table byte-identical.
