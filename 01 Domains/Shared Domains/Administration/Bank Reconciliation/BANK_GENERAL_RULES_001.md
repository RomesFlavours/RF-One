# General (structural) WHO rules

**Task:** BANK_GENERAL_RULES_001 (Product Owner decision, 2026-10-05)
**Status:** Implemented on `feature/bank-simple-who-rules` — model, migration, service, import step, Classification UI, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** migration `f4a8c2d6e9b3` — new table `bank_general_rules`, seeded with the Chase ACH rule.

---

## Two levels of WHO recognition

| Level | Concept | Model | Example |
|---|---|---|---|
| 1 — **General Rule** | WHERE a family of descriptions carries the WHO: the text between two markers. One rule, many WHO candidates. | `BankGeneralRule` (new) | between `ORIG CO NAME:` and `ORIG ID:` |
| 2 — **WHO Rule** | A fixed phrase names one fixed WHO. | `BankRecognitionRule` (unchanged) | description contains `TABLE TOP LINEN` → Table Top Linen |

A General Rule is deliberately a separate model: overloading `BankRecognitionRule` would mix "fixed phrase →
fixed WHO" with "structure → dynamic candidate".

## Semantics

* **Extraction** (`general_rules.extract`): the text strictly between the start marker and the first end marker
  after it; markers matched case-insensitively; result trimmed, inner whitespace collapsed; nothing when a
  marker is missing or the value is empty. No regex, no expression language.
* **Resolution**: a candidate becomes a WHO only through `CanonicalWhoResolver.resolve` — an approved
  description rule, then the active canonical name, then an active alias. No fuzzy matching, **no WHO is ever
  created**. A candidate that resolves to nothing is a *suggested WHO*: the transaction keeps its decision and
  stays To Reconcile.
* **Assignment**: a resolved candidate is recorded as a RULE decision naming the WHO, carrying the current
  WHY / WHAT unchanged (the same way the simple WHO rule records a WHO). The transaction moves to Reconciled even
  while its WHY is open. **A General Rule never chooses a WHY.**
* **Never overwritten**: a HUMAN decision; a decision from a Reconciliation Standard; a decision that already
  names a different WHO (reported as protected conflicts). **Own-account movements are skipped** (STRUCTURAL
  recognition, a confirmed internal-transfer match, or a candidate that is one of RF-One's own legal entities).

## Save, Preview, Apply

* **Save** — available to future imports.
* **Preview** — what Apply would do now (resolved, to assign, unknown with names and counts); writes nothing.
* **Apply to Existing Transactions** — scans every transaction and assigns the resolved WHO. Idempotent. Result:
  scanned, structured matches, distinct candidates, resolved to canonical WHO, newly assigned, already resolved,
  unknown (with the suggested names), protected conflicts, own-account movements skipped.

## Future imports

In the one import pipeline (`service._normalize_rows`): automatic decision (`recognition.deduce_for_transaction`,
level-2 rules + structural WHY) → **General Rules** (only when that decision names no WHO) → Reconciliation
Standards → accounting dedup. The resolver is built once per import pass.

## Classification page

GENERAL RULES (name, source, extraction, status, matches, Edit / Disable / Preview / Apply, *+ New General
Rule*) above WHO CLASSIFICATION, which is unchanged. The page computes only the text matches per rule; the full
resolution is the explicit Preview, so the page stays fast.

## Open points (Product Owner)

* **Decided (BANK_FINAL_CLEANUP_001):** structural extraction never creates a raw WHO. The `who-v1`
  recognizer (`apply_who_recognition.py`, a manual CLI, not run at import) now holds a name that is not a
  known WHO as PROPOSED, exactly like a General Rule's unknown name; a person creates the WHO. The General
  Rule is the one import-time structural WHO path. In the current 2025+ data every ORIG CO NAME already exists
  as a WHO (created by earlier `who-v1` runs); those WHO are kept — they are identities a person can merge or
  deactivate, and nothing is deleted.
* The `who-v1` text parser (including its ORIG CO NAME pattern) remains, read-only: it no longer creates
  anything, and its stored STRUCTURAL results still mark own-account movements for the review queues.
* Reprocessing (`redecide_for_transaction`) does not run General Rules; only import and Apply do.
