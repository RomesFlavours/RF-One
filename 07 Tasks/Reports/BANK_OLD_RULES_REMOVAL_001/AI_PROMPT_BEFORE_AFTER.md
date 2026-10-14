# AI interpretation prompt — removing "Standard" (proposal, NOT applied)

**Status:** proposal for Product Owner approval (2026-10-14). The prompt sent to the AI is **unchanged**: fingerprint
of `ai_rules._interpretation_prompt("RULE", "EXAMPLE", None)` = `b3915c39b9e0e684` (SHA-256, first 16 hex), before and
after this task. `INTERPRETATION_VERSION` stays `structured-v7`.

Only one paragraph of the prompt mentions Reconciliation Standards (the description of `"replace_existing"`, in
`ai_rules._interpretation_prompt`). The operator-facing label of the option has already been changed
(`OVERRIDE_LABEL`); the prompt keeps the former wording through `PROMPT_OVERRIDE_LABEL` until this proposal is
approved.

## Before (in use)

```text
- "replace_existing": true — a different WHO / WHY / For Whom already decided by another rule or an earlier
     automatic decision is replaced. Otherwise false (such a value is a conflict, left as it is). RF-One ALWAYS
     protects, and shows separately: decisions made manually or by a Reconciliation Standard, own-account
     movements (no WHO), a For Whom chosen by a person or by a Standard, a movement whose For Whom is already
     accounting-complete (confirmed), and a For Whom whose origin is uncertain (kept, with the reason). An
     instruction to keep manual / Standard classifications is represented by these protections — say so in the
     coverage. An instruction that EXPLICITLY authorizes replacing WHO / WHY also when manual, Standard or confirmed
     is represented by the rule option "Sostituisci anche WHO/WHY manuali, Standard o confermati" (set by the operator on the rule, off by default,
     recorded) together with "replace_existing" — say so in the coverage; it is not an element of this structure.
```

## After (proposed)

```text
- "replace_existing": true — a different WHO / WHY / For Whom already decided by another rule or an earlier
     automatic decision is replaced. Otherwise false (such a value is a conflict, left as it is). RF-One ALWAYS
     protects, and shows separately: decisions made manually, own-account movements (no WHO), a For Whom chosen
     by a person, a movement whose For Whom is already accounting-complete (confirmed), and a For Whom whose
     origin is uncertain (kept, with the reason). An instruction to keep manual or confirmed classifications is
     represented by these protections — say so in the coverage. An instruction that EXPLICITLY authorizes
     replacing WHO / WHY also when manual or confirmed is represented by the rule option "Sostituisci anche
     WHO/WHY manuali o confermati" (set by the operator on the rule, off by default, recorded) together with
     "replace_existing" — say so in the coverage; it is not an element of this structure.
```

## What changes, and what does not

| Item | Before | After |
|---|---|---|
| Manual decisions protected | yes | yes (unchanged) |
| Own-account movements protected | yes | yes |
| For Whom chosen by a person protected | yes | yes |
| Accounting-complete (confirmed) For Whom protected | yes | yes |
| For Whom of uncertain origin kept | yes | yes |
| Decisions "by a Reconciliation Standard" / For Whom "by a Standard" | named | removed (none can exist) |
| "keep manual / Standard classifications" | named | "keep manual or confirmed classifications" |
| Override option name | "… manuali, Standard o confermati" | "… manuali o confermati" (= the label now shown) |

The protections themselves are enforced by code (`ai_rules.Planner.plan_full`), not by this text: the text only tells
the AI how to describe them in a rule's coverage.

## Effect on the 37 saved interpretations

None, if applied as proposed:

- the cache key is `INTERPRETATION_VERSION + rule text + general instructions`
  (`ai_rules.interpretation_key`); the prompt text is not part of it, so every saved interpretation keeps its key
  and is reused as it is;
- `INTERPRETATION_VERSION` must **not** be bumped for this change (a bump would make every rule be interpreted
  again);
- only a rule interpreted for the first time after the change would be read with the new wording.

## To apply (after approval)

In `ai_rules.py`: replace the paragraph with the "After" text and use `OVERRIDE_LABEL` there; remove
`PROMPT_OVERRIDE_LABEL`. Then verify the new prompt fingerprint and that `INTERPRETATION_VERSION` is still
`structured-v7`, and that `bank_ai_rule_interpretations` is untouched.
