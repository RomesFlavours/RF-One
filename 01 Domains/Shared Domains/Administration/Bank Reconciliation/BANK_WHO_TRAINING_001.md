# WHO Pattern Training — WHO rules learned from the person's examples

Product Owner, 2026-10-25: the automatic WHO generator is not reliable enough. First the system learns from
the person's examples, then it builds rules. **The person teaches; RF-One turns what it is taught into
deterministic rules, without arbitrary generalization.**

## 1. Where

Bank › Rules and profiles › **WHO Pattern Training** (`/bank/who-training`), linked from the Rules and
profiles page. The 57 proposals of search 120 were discarded from the approval list and kept as history
(`discarded`, date and reason on each); the approved WHO rules were not touched.

## 2. What the person does

| Step | Detail |
|---|---|
| Find movements | All bank movements, alphabetical by original description; search, Source, amount and date filters, "to examine / confirmed by you / human decision / approved rule"; multiple selection |
| Give the WHO | An existing WHO, or Create WHO (the existing creation: an identical WHO is reused, never duplicated) |
| Show the WHO | On one selected movement, click the pieces of the description that are the WHO |
| Mark what varies | Click the pieces that change from movement to movement (dates, numbers, codes) |
| No WHO in the text | "The WHO is not in the description: it needs external knowledge" |
| Not a rule | "Only for these movements: do not use them to build a rule" |

Examples are training data in their own record (`bank_flow_artifacts`, kind `WHO_TRAINING`): they change no
WHO, WHY, WHAT or classification of any movement.

## 3. From examples to a rule (code, no AI)

From each example with a highlighted WHO RF-One derives the WHO extraction rule (FLOW_2 `EXTRACTOR`) it
implies:

- the text before the WHO is the anchor (its first word as prefix), with the marked variable parts as
  `{date}`, `{number}`, `{code}`; nothing before the WHO = the WHO opens the description;
- the first element after the WHO ends it: a fixed text as marker, a variable number as `{number}`, a final
  variable reference as "final reference code"; nothing after = end of the description;
- a variable part made of letters only is refused (it cannot be described without guessing);
- the rule must read exactly the highlighted text from its own example, otherwise it is refused.

Examples implying the same rule become one proposal. Each proposal is tested on every movement: the
person's examples (read correctly or not) apart from the additional movements, and movements an approved
rule reads differently.

## 4. Correction and approval

- **Exclude:** the person ticks wrong interceptions; RF-One looks for words present in them and absent from
  every kept movement and adds them as exclusions (at most three). Movements no word can separate are
  reported: they cannot be excluded by the description alone.
- **Approve** (with confirmation): a WHO extraction rule, version 1, active; the engine reads it on its next
  run; a more specific approved rule keeps precedence. **Reject** keeps the proposal as rejected.

## 5. Movement-by-movement identifications

Examples marked "external knowledge" or "only for these movements" are listed apart and never become a
rule. Applying them as WHO decisions on those movements is a later, separate step.

## 6. Summary

Bank movements · WHO confirmed by the person here (of which movement-only) · WHO decided by a person
earlier in Bank · read by approved WHO rules · with a known WHO (each counted once) · still to examine ·
rule proposals waiting (never counted as known).

## 7. Code

`RF-One Web/bank_who_training.py`, `templates/bank_who_training.html`, `static/bank-assistant/who_training.js`;
test `tests/test_bank_who_training_http.py` (isolated copy of the local database).
