# Bank two-pass reconciliation

## 1. One routine
The AI button on a transaction and Reconcile pending use the same persisted RUN and deterministic planner. Both single and batch select only the existing To Reconcile queue. A current WHO means reconciliation is already resolved, even when accounting allocation or WHAT is incomplete. Such rows are protected at run creation, preview, application and guided save. Accounting completeness never reopens reconciliation. Duplicates and own-account transfers retain the existing eligibility rules.

## 2. Automatic pass
Extract WHO using approved future-active description rules. Apply an unambiguous complete recognition profile. Only if no profile matches, look up WHO in Configuration and use its explicit active default WHY and the WHY-linked accounting destination. Observed WHO/WHY associations are not defaults. Source ownership supplies WHOM; an explicit human transaction override takes precedence. Missing identity, conflicting rules, missing ownership, split allocations, incomplete profiles or destinations go to guided review. No AI or external research runs in this pass.

Planning is read-only for financial data. The automatic preview lists actual assignments and unresolved cases. Applying validates the rules/catalog signature, eligibility and the full snapshot of every examined transaction under a writer lock. Changes are atomic and audited. Stale previews must be restarted.

## 3. Guided pass
After applying a nonempty automatic preview, open the shared recognition profile modal for one remaining transaction. If the automatic pass has no proposed changes, go directly to guided review without an empty Apply step. First show previously reconciled transactions with the same description, ignoring varying Zelle references and ACH references/dates while preserving ACH entry purpose. Use the existing WHO decision as the reconciliation authority; complete accounting allocations are not required for historical evidence. History lookup never creates an extraction rule or assigns classifications. Historical choices remain proposals and conflicting choices need human instructions. If there is no useful history, use the existing shared online research engine, preserving extracted WHO when known. The same Configuration WHY/WHAT lists and chat policy editor remain available on research failure.

The profile preview covers the current row. Save profile and reconcile this transaction publishes the exact previewed definition as a new immutable version under the existing canonical WHO profile ID, applies it to this row, marks it reconciled and advances to the next remaining row. New WHO profiles are created only when none exists. Multiple managed profiles for one identity are blocked for consolidation rather than creating another copy. Normal profile editing outside a run retains future/repository publication choices.

## 4. Stop and resume
Stop is available in the review controls and in the modal header. It terminates the run, retaining approved work. Close/Escape also stops; Skip leaves that transaction for a later run. Backend checks reject research, chat results, previews and saves from a stopped or advanced run. Browser generation checks discard late responses. Reloading exposes Continue for an active run; it does not apply a preview automatically.

## 5. Imports and rollback
Imports and existing queued jobs use the same deterministic planner. Already approved policies can reconcile imported rows; unresolved jobs are parked at GUIDED without unattended AI. The foreground review run handles the remaining human decisions.

Each financial application has immutable before/after snapshots. Profile changes use the existing application audit. Configuration fallback uses RUN snapshots and creates no bookkeeping AI rules or profiles. Reconciliation history can roll back a completed or stopped run. Full snapshot comparison preserves later edits and reports skipped rows. Rollback reverses financial assignments; published profile definitions remain available for future imports. Configuration and profile rollback share the same snapshot restoration helper. No schema migration or Core concept changes are required.

## 6. Validation
Isolated temporary databases cover single/batch operation, profile-first order, explicit Configuration fallback, read-only/stale previews, Source ownership, same-ID profile publication and reopening, Stop with late provider responses, history-first proposals, import parking, canonical status and guarded rollback. Browser verification uses synthetic transactions only. No production run is started during installation.

## 7. Current transaction stays visible
The shared profile editor keeps the current transaction number, posting date, signed amount and currency, account (including its last four digits), Source, owner and full original description above the scrolling chat and preview. Context comes from the selected transaction through an authenticated read-only endpoint. It is refreshed when opening another transaction, including Skip and profile creation from a rule preview; returning to that preview restores its context and scroll position. Opening the editor starts at the top, without scrolling to the composer. Embedded reconciliation uses the full available editor area, with Stop and Skip visible outside it. Profile editing without a transaction shows the profile WHO instead of an unrelated transaction. No reconciliation decision, rule or profile is changed by this display.

## 8. Profile Save beside the composer
WHY and WHAT are adjacent, with their labels above the lists. Profile editing offers a Save button at the right of the composer and mutually exclusive scope choices in the middle: current transaction (default when a transaction is present), or all matching pending repository transactions. A profile without a transaction offers future-only or repository. The extraction-preview child editor keeps its existing future-only save-and-return workflow.

Save incorporates any changed WHO/WHY/WHAT selections and the unsent chat instruction, then opens a preview of that exact definition and scope. Ambiguous instructions stay in the chat for clarification. No publication or transaction update happens until Confirm save and apply. Edit returns to the composer with the scope retained. The server binds the scope to the preview and refuses a different save action.

Both reconciliation scopes protect already reconciled rows. Repository matching uses approved extraction or the current description on the same payment instrument; identical description examples do not become broad extraction rules. Profile creation/update uses the existing canonical WHO identity and versions. Guided repository application records all applications in run history, removes reconciled rows from the remaining queue, then continues. Rollback preserves subsequent edits as before.


### Missing Source owner in profile preview (2026-10-20)
The profile modal keeps a WHOM selector beside the current transaction. A manual
selection applies only to that transaction, never to the Source or future rows.
Preview shows the known WHO/WHY/WHAT even when WHOM is missing and disables
application until the current transaction has a complete choice. Changing WHOM
rebuilds the preview. Nothing financial is written until confirmation; the
allocation is marked HUMAN within the same application and rollback snapshot.
Repository application retains each other transaction's own Source/manual WHOM.
