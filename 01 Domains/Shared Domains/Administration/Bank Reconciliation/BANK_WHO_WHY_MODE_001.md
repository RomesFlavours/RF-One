# WHO recognition ≠ WHY determination — WHO WHY mode and WHO WHY rules (2026-11-01)

Product Owner request, 2026-11-01. Recognising the WHO and determining the WHY are two distinct steps.
This document extends `BANK_WHO_SOURCE_CLASSIFICATION_001` (WHO + Source) and reuses the rule language of
`BANK_WHY_PATTERNS_001`; it does not replace either.

## 1. WHO WHY mode

| Mode | Meaning | Where the WHY comes from |
|---|---|---|
| **UNIQUE** (default) | One WHY per WHO + Source | The exact WHO + Source classification. When the pair has no WHY, an applicable WHO WHY rule may determine it; otherwise the movement stays open |
| **MULTIPLE** | The WHY depends on the single movement | Only a WHO WHY rule. A WHY registered on the pair is kept but never used for that WHO (no generic bypass) |

- Stored in `bank_who_why_modes` (one row per MULTIPLE WHO). **No row = UNIQUE**, so every existing WHO keeps
  the behaviour it had; nothing is marked MULTIPLE automatically.
- A WHO with different WHYs on different Sources is **not** MULTIPLE: each WHO + Source pair already resolves it.
- Only a person sets the mode (page *WHY Rules*). Changing it changes the engine's knowledge signature.

## 2. WHO WHY rules

A WHO WHY rule determines the WHY of a WHO **already recognised**. It never identifies a WHO — that is the job
of the WHO recognition rules and WHO Search Text (`BANK_WHO_SEARCH_TEXT_001`).

| Element | Content |
|---|---|
| Storage | `BankAiRule` + immutable `BankAiRuleVersion` (method CODE), spec `engine = BANK_WHY_PATTERN`, `scope = WHO`, `who_ids` |
| Conditions | The `BANK_WHY_PATTERNS_001` vocabulary: Source, Source type, accounting subject at the movement date (Personal / Company, from the Source owner on that date), direction, amount, description, Source information (import columns), RF-One evidence. Each condition is True, False or MISSING; at least one condition is required |
| Result | One active, non-provisional WHY of the catalog, **or** a document the WHY is read from (`amazon_order`) |
| State | ACTIVE / INACTIVE. Saved INACTIVE unless the person activates it |
| Simulation | Before saving, the draft is simulated on the WHO's movements (new WHY, different WHY, unchanged, still open, protected) |
| Isolation | Excluded from WHO recognition (`flow.entries`), from the old AI-rules executor and from WHY-pattern discovery |

WHAT always derives from the WHY. WHOM stays the Source owner (decision 86). Human decisions stay protected.

## 3. Determination and open reasons

For a recognised WHO the engine (`Engine.determine_why` → `who_why_rules.Resolver`) gives one result:

| Result | When |
|---|---|
| WHY from WHO + Source | UNIQUE WHO with a WHY on its pair |
| WHY from a WHO WHY rule | Exactly one WHY among the rules that apply, and no applicable rule is incomplete |
| **Serve una classificazione WHO + Source** (`WHO_SOURCE_CLASSIFICATION_MISSING`) | UNIQUE WHO, no WHY on the pair, no applicable rule |
| **Serve una regola per il WHY** (`WHY_RULE_MISSING`) | MULTIPLE WHO, no applicable rule |
| **Serve un documento o un chiarimento** (`WHY_DOCUMENT_MISSING`) | A rule applies but a condition cannot be evaluated or its document is missing / unclear. Also when one rule matches and another is incomplete: the incomplete one could give a different WHY |
| **Regole in conflitto** (`WHY_RULES_CONFLICT`) | The applicable rules give different WHYs |

## 4. Amazon order evidence

The `amazon_order` document reads the Amazon order reports already kept by `bank_amazon` (one shared grouping
and matching: `who_why_rules.charge_groups` / `charge_matches`):

1. The movement must contain, as a whole word, the Charge Identifier of a report order, matched to that movement
   alone (no substring, amount, date or card fallback). Otherwise: document missing.
2. Product WHYs come from the latest completed Amazon analysis of exactly those products, HIGH confidence only.
3. One WHY for all products → that WHY. Products with different WHYs (mixed purchase) → a split is needed. A
   product without a HIGH-confidence WHY → clarification needed.

No blanket WHY ("Direct Restaurant Consumables", "Owner Personal — Other") is ever applied to Amazon.

## 5. Examples supported (rules are created by a person, none is created automatically)

| WHO | Rule(s) |
|---|---|
| Restaurants, bars, coffee shops | `subject is Personal → Owner Personal — Restaurant`; `subject is Company → Business Meals & Entertainment`. Ownership at the movement date; owner unknown → *Serve un documento o un chiarimento*. No proof of purpose or exact branch required |
| Amazon | `direction is money out → WHY from the Amazon order report` |
| Chase | Rules on the nature of the movement (e.g. description contains a fee wording → the fee WHY); the name CHASE alone never decides. Matched card payments and transfers keep their own path ahead of WHO |

## 6. Processing path (engine and three-stage simulation)

Rules → WHO Search Text → (WHO known) WHY by mode → if the WHY is still open, research with the **WHO fixed**:
the AI may propose a WHY from evidence (kept apart as *PROPOSED FROM EVIDENCE*), never change a recognised WHO.
Rules in conflict are never resolved by the research. Insufficient evidence keeps the movement open with its
reason. The simulation counts each movement once in four final states: WHO identified with WHY determined,
WHO identified with WHY open, generic WHO classified, open without WHO (`cbank/three_stages.py`).

## 7. Interface

Bank menu **WHY Rules** (`/bank/why-signals`): the movements with a recognised WHO and an open WHY, grouped by
WHO, Source and reason, with count, amount, the movements, and the action (*Classify WHO + Source* →
Configuration; *Define rule*; *Amazon order report* / *Review rules*). The same page lists the WHO WHY rules
(Activate / Deactivate) and the MULTIPLE WHO (set / back to UNIQUE). The list and the simulation are read-only
evaluations; nothing on the page writes a movement classification or starts an engine run.

## 8. Data and migration

Migration `a5c220261101` adds `bank_who_why_modes` only. No existing row is changed or reinterpreted; code
running on a database not yet migrated treats every WHO as UNIQUE. Engine policy `who-why-mode-v5`; the
knowledge signature includes modes and Amazon evidence.

## 9. Code and tests

`rfone_data_store/bank_reconciliation/who_why_rules.py`; `why_patterns.check_conditions`; `RF-One Web/bank_why_signals.py`,
`templates/bank_why_signals.html`, `static/bank-assistant/why_signals.js`; C-Bank `cbank/engine.py`
(`determine_why`), `cbank/why_signals.py`, `cbank/three_stages.py`. Tests: C-Bank `tests/test_who_why_mode.py`,
`tests/test_three_stages.py`; Web `tests/test_bank_why_signals_http.py` (isolated, migrated copies).

## Approved analysis extension (2026-11-03)

See [BANK_RULE_SCOPE_AND_WHO_CATEGORY_001.md](BANK_RULE_SCOPE_AND_WHO_CATEGORY_001.md) for the approved design of general/category/single-WHO rule coexistence, approved consolidation and contextual user declarations. It is a design extension to this implemented baseline, not a claim that all new behavior is implemented.
