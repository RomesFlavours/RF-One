# General (structural) WHO rules

**Task:** BANK_GENERAL_RULES_001 (Product Owner decision, 2026-10-05)
**Status:** Implemented on `feature/bank-simple-who-rules` — model, migration, service, import step, Classification UI, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** migration `f4a8c2d6e9b3` — new table `bank_general_rules`, seeded with the Chase ACH rule.
**Amended by:** BANK_GENERAL_RULE_END_001 (2026-10-08 — `END` as end marker; an explained Apply) and
BANK_GENERAL_RULES_CREATE_WHO_001 (Product Owner decision, 2026-10-08 — **a General Rule creates the WHO it
extracts when it does not exist**; this supersedes the original "no WHO is ever created" constraint below).

---

## Two levels of WHO recognition

| Level | Concept | Model | Example |
|---|---|---|---|
| 1 — **General Rule** | WHERE a family of descriptions carries the WHO: the text between two markers. One rule, many WHO candidates. | `BankGeneralRule` (new) | between `ORIG CO NAME:` and `ORIG ID:` |
| 2 — **WHO Rule** | A fixed phrase names one fixed WHO. | `BankRecognitionRule` (unchanged) | description contains `TABLE TOP LINEN` → Table Top Linen |

A General Rule is deliberately a separate model: overloading `BankRecognitionRule` would mix "fixed phrase →
fixed WHO" with "structure → dynamic candidate".

## Semantics

* **Extraction** (`general_rules.extract`, the ONE function used by Preview, Apply, the import and the page
  counts): the text strictly between the start marker and the first end marker after it; markers matched
  case-insensitively, literally (an `*` is a character); result trimmed, inner whitespace collapsed; nothing
  when a marker is missing or the value is empty. No regex, no expression language.
  **`END`** as end marker (any case, outer spaces ignored, stored as `END`): from after the start marker to the
  end of the field, with only leading / trailing spaces removed (`PAYPAL *` … `END` on `PAYPAL *TRUTHFINDER`
  → `TRUTHFINDER`).
* **Resolution and creation** (BANK_GENERAL_RULES_CREATE_WHO_001): the candidate is first resolved through
  `CanonicalWhoResolver.resolve` — an approved description rule, then the active canonical name, then an active
  alias. A name that resolves to nothing is **created as an active Counterparty WHO** through the Configuration
  service (`configuration.save_who`: no WHY, no default WHY, no Entity, no rule), after the WHO registry's
  identity checks (`who_rules.check_new_who`): the same name, identity key (case / spacing) or alias IS the
  existing WHO and is reused — never a duplicate; a too-short / too-long name or the name of a merged
  (inactive) WHO is refused and reported. Names that are only similar are **never merged**. No fuzzy
  matching. A WHO is created **only for a transaction that can receive it** (none of the protections below
  applies), in the same database transaction as its assignment; one pass creates each name once.
* **Assignment**: a resolved candidate is recorded as a RULE decision naming the WHO, carrying the current
  WHY / WHAT unchanged (the same way the simple WHO rule records a WHO). The transaction moves to Reconciled even
  while its WHY is open. **A General Rule never chooses a WHY.**
* **Never overwritten**: a HUMAN decision; a decision from a Reconciliation Standard; a decision that already
  names a different WHO (reported as protected conflicts). **Own-account movements are skipped** (STRUCTURAL
  recognition, a confirmed internal-transfer match, or a candidate that is one of RF-One's own legal entities).

## Save, Preview, Apply

* **Save** — available to future imports.
* **Preview** — what Apply would do now, including the WHO it would create (names and transactions); writes
  nothing.
* **Apply to Existing Transactions** — scans every transaction (all periods, all Sources, no page filter) and
  assigns the WHO — existing or created — in one database transaction. Idempotent: a second Apply creates no
  WHO and changes nothing. Result: scope, transactions examined, matches, transactions updated, WHO created,
  existing WHO reused, unchanged / skipped with each reason actually found (no extraction, a name that cannot
  become a WHO, WHO already present, protected by a person / a Standard / another WHO, own-account), and
  "Nothing changed" with its reason when nothing changed. The page keeps its search arguments and shows the
  global wait cursor / spinner.

## Future imports

In the one import pipeline (`service._normalize_rows`): automatic decision (`recognition.deduce_for_transaction`,
level-2 rules + structural WHY) → **General Rules** (only when that decision names no WHO; the existing WHO
or a WHO created exactly as Apply does — the same `general_rules._who_for`) → Reconciliation Standards →
accounting dedup. The resolver is built once per import pass.

## Classification page

GENERAL RULES (name, source, extraction, status, matches, Edit / Disable / Preview / Apply, *+ New General
Rule*) above WHO CLASSIFICATION, which is unchanged. The page computes only the text matches per rule; the full
resolution is the explicit Preview, so the page stays fast.

## Open points (Product Owner)

* **Decided (BANK_FINAL_CLEANUP_001), amended by BANK_GENERAL_RULES_CREATE_WHO_001:** the `who-v1`
  recognizer (`apply_who_recognition.py`, a manual CLI, not run at import) still never creates a WHO: it holds
  a name that is not a known WHO as PROPOSED. The General Rule — the one import-time structural WHO path —
  now DOES create the WHO of a valid extracted name (see Semantics). In the current 2025+ data every ORIG CO NAME already exists
  as a WHO (created by earlier `who-v1` runs); those WHO are kept — they are identities a person can merge or
  deactivate, and nothing is deleted.
* The `who-v1` text parser (including its ORIG CO NAME pattern) remains, read-only: it no longer creates
  anything, and its stored STRUCTURAL results still mark own-account movements for the review queues.
* Reprocessing (`redecide_for_transaction`) does not run General Rules; only import and Apply do.
