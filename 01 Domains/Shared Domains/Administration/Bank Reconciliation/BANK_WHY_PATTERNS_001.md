# Discover WHY Patterns — deterministic WHY rules discovered by AI

Product Owner authorization, 2026-10-25 ("AI Deterministic Rule Discovery & Consolidation Engine").
The AI discovers, proposes and refines; a person approves; approved rules run as code in the one
reconciliation engine, without AI. Recognition Profiles are kept as they are.

## 1. Principles

| Principle | How it is implemented |
|---|---|
| Independence from Sources | Rules read four layers of information; optional Source information may be absent at any time without errors |
| Missing ≠ false | A condition is True, False or MISSING. A rule with a MISSING condition does not apply and says what is missing |
| No invented functions | The AI combines only conditions RF-One offers; evidence is coded by RF-One (closed list) |
| No accounting tolerance | Amount evidence matches exactly, to the cent |
| Decision 86 | The accounting subject is read from the Source (condition "Accounting subject (Source)") and never set by a rule |
| Human decisions | Never changed; protected by the engine; used as examples and counterexamples |
| Approval | Nothing is active before an explicit, confirmed approval by a person |

## 2. What a rule may read

| Layer | Content | Availability |
|---|---|---|
| Core | Source, Source type, accounting subject (Source owner), direction, amount, weekday, description, description format | every Source |
| Optional Source information | every column of the import file kept unmodified in `bank_import_batches` (e.g. Chase `Category`, `Memo`), the bank's own transaction type, ACH fields (originator, entry description, individual name). Account and card numbers are excluded | depends on the Source |
| RF-One knowledge | the movement's WHO and the WHO's Labels | when WHO is known |
| Evidence | `clover_employee` (WHO is a Clover employee on that date), `tips_payable_match` (amount equals the employee's payable in the latest Tips run already calculated on that date, period ended by then), `payroll_verified` (amount equals a verified Payroll net pay) | other RF-One domains; locally the newest copy of the RF-One database (`RFONE_DOMAIN_DATA`) |

New Sources (Amazon, PayPal, …) need no change in the rule logic: their file columns appear as optional
information, and new evidence is added to the closed list in code.

`payroll_verified` is always MISSING today: RF-One holds no verified Payroll amounts (Payroll and
Compensation results are empty). No Payroll correspondence is ever inferred.

**Identity is not purpose.** Each evidence declares the WHYs it proves: `tips_payable_match` proves Tips
Distribution / Settlement, `payroll_verified` the Payroll WHYs, `clover_employee` none (it says who, not
why). A rule for a WHY that RF-One can prove must contain that evidence — refused otherwise, at discovery,
at "Discuss with AI" and at approval. Being an employee, recurring or paid weekly never decides Tips or
Payroll. (Found in the first real discovery: "WHO is a Clover employee → Tips", 443 movements with no human
counterexample, was proposed until this rule was added.)

## 3. Discovery and consolidation

1. Movements are grouped by **description format** (references, dates, codes and numbers removed; ACH by
   originator and entry description). Matched card settlements and transfers are structural facts and stay
   out of discovery.
2. The AI reads each format once, in batches, and names its WHY — or splits the format using only the
   conditions offered for it. It receives counts, up to three masked descriptions, WHO names, the WHAT of
   human decisions and the conditions; never amounts, dates, account or card numbers (consent scope).
   Readings are cached: an unchanged format is not asked again.
3. Examples: a human decision (its WHAT; it names a WHY when exactly one active WHY has that WHAT), else the
   AI reading of the format. Counterexamples: every movement labelled with another WHY/WHAT.
4. **Consolidation** (code, deterministic): for each WHY, the smallest set of up to three conditions that
   covers its examples **across the most formats**, touches no counterexample, prefers general conditions
   (Labels, evidence, Source information) over specific ones (WHO, format) and core information over
   optional information. A few counterexamples inside an otherwise general rule become **named exceptions**
   (a WHO or a format), never a silent loss. A rule may not classify more unlabeled movements than the
   examples it rests on; it needs two examples unless it rests on RF-One evidence.
5. **Verification** of each proposal on the whole history: human counterexamples, conflicts with the
   existing rules and profiles (last engine run), overlaps with approved rules and with the other proposals,
   before/after (new WHY, unchanged, different WHY today, protected human decisions), a later-period check
   (the same consolidation built only on data up to two months before the end), and the dependence on
   optional information (movements left undecided if it disappears).

## 4. Approval, execution, rollback

| Step | Effect |
|---|---|
| Approve (with confirmation) | A `BankAiRule` with an immutable version, spec `engine = BANK_WHY_PATTERN`, method CODE |
| Execution | The single engine evaluates approved WHY rules next to profiles and text rules. Same WHY: confirmed. Different WHY: `PROFILE_CONFLICT` for a person. Information missing: anomaly `WHY_RULE_INFORMATION_MISSING`. Structural facts (card settlements, transfers) come first |
| Engine re-run | Approving, deactivating or reactivating a rule changes the knowledge signature: the engine re-runs |
| Deactivate | The rule stays (versions, history) and stops acting |
| Reject / Discuss with AI | Reject keeps the proposal as rejected. Discuss: one AI revision using only offered conditions, verified again |

The old AI Rules executor, the import path and the Recognition Profiles list ignore WHY pattern rules.

## 5. Interface

Rules and Profiles page (`/bank/ai-rules`): the former "Find standard formats" button is **Discover WHY
Patterns**, in a new "WHY patterns" section above the unchanged AI rules and Recognition profiles. Each
proposal shows, in plain language: conditions and exceptions, formats joined, movements and amount covered,
what approving changes, counterexamples, conflicts, overlaps, later-period result and optional-information
dependence, with Approve…, Discuss with AI, Reject. Approved rules are listed with Deactivate / Activate.

## 6. Labels

Labels are now also **deterministic conditions** of WHY rules (Product Owner, 2026-10-25), never an
absolute proof: a rule on a Label is verified against counterexamples like any other condition. In the
engine's WHO/profile stages Labels remain context, as in BANK_AI_PROFILE_PROPOSAL_001.

## 7. Code

`rfone_data_store/bank_reconciliation/why_patterns.py` (language, information, evidence, discovery,
consolidation, verification, approval); `RF-One Web/bank_why_pattern_routes.py` (routes);
`static/bank-assistant/why_patterns.js`; C-Bank `cbank/engine.py` (execution) and `cbank/service.py`
(signature). Test: `RF-One Web/tests/test_bank_why_patterns_http.py` (isolated copy of the local database).
