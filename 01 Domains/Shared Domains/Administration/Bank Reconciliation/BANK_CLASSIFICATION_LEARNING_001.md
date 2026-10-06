# Classification Learning — pattern discovery

**Task:** BANK_CLASSIFICATION_LEARNING_001 (Product Owner decision, 2026-10-05)
**Status:** Implemented on `feature/bank-simple-who-rules` — engine, WHY rules, import step, Classification UI, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** migration `a5d9e3f7b2c4` — `bank_learning_runs`, `bank_pattern_suggestions`, `bank_why_rules` (no data).

---

## One engine above the rule stores

```
OBSERVE -> DISCOVER -> EXPLAIN -> TEST -> HUMAN REVIEW -> HUMAN APPROVE -> DETERMINISTIC RULE
```

`bank_reconciliation/pattern_discovery.py` is the ONE shared engine. It replaces no rule store; approval routes
into the existing one:

| Pattern | Example | Approved into |
|---|---|---|
| STRUCTURAL | text between `ZELLE PAYMENT TO` and `JPM99` names the WHO | General Rule (`bank_general_rules`) |
| WHO | description contains `BAKERY SUPPLY` → Bakery Supply | WHO Rule (`bank_recognition_rules`) |
| WHY | WHO = ADP, description contains `TAX` → Employer Payroll Tax | **WHY Rule** (`bank_why_rules`, new) |

A **WHY Rule** has a required WHO scope and optional AND-ed conditions (description phrase, direction, instrument
type). It never chooses a WHO, so the recognition-rule invariant (a description rule names a WHO, never a
purpose) is untouched. Like a Reconciliation Standard it exists only by human approval. At import it runs right
after WHO recognition, only when the decision names a WHO but no WHY, never over a HUMAN or Standard decision.

## Raw input vs refined truth

Each `Observation` keeps the bank's **raw input** (description, posting date, instrument and type, direction,
amount, source; plus what the automatic parser read — used only as contrary evidence) apart from the **refined
truth** (WHO, WHY, WHAT, provenance, confirmed). Provenance: `HUMAN`, `STANDARD`, `RULE` (WHO / General / WHY
rule), `STRUCTURAL` (the `why-v1` engine), `OTHER`.

* Only HUMAN truth is learning truth. Other truth is *support*: labelled, counted apart, never enough for a
  "Human-verified" evidence level.
* WHY discovery ignores every WHY a rule, a Standard or the structural engine produced (no circular learning).

## Candidates

* **Structural**: field labels (`LABEL:` pairs) and a frequent leading phrase followed by a stable token prefix.
  Accepted only when the values are recurring NAMES (not codes) and, where the WHO is known, the value actually
  names it (canonical name or alias, ≥ 60%). Same markers as an active General Rule → **COVERED**, not new.
* **WHO**: a phrase (format words excluded) that means one WHO wherever a WHO is known, also appears where no WHO
  is decided yet (the gap), and is never read by the parser as another counterparty; existing WHO rules are not
  re-proposed.
* **WHY**: per WHO, from HUMAN WHY only (≥ 3 cases): one universal WHY when proven (and the WHO has no other
  known WHY), else one stable distinguishing feature. Anything weaker is **PROBABILISTIC** ("pattern observed —
  not deterministic"): shown, never approvable.

## Rejection memory

Each suggestion has a fingerprint of its pattern. A rejected fingerprint is not proposed again unless its evidence
grows materially (≥ +50% and ≥ +3); it then comes back marked *Previously rejected — new evidence available*.

## Temporal backtest

For each month from 2025-07: learn only from earlier months, hide the month's decisions, predict from raw input
with the learned deterministic rules, compare. **HUMAN** rows measure accuracy; **SUPPORT** rows measure agreement
with current rule / structural / Standard decisions and are not accuracy. A month with fewer than 30 human
decisions is flagged unreliable.

## UI and runtime

Bank > Classification shows **Classification Learning** (Discover Patterns, Run Backtest, Suggested Patterns with
Review / Test / Approve / Reject, the backtest table) above General Rules and WHO Classification. The page only
reads stored results. Discovery and backtests are explicit actions; approved rules run without any AI call.
`PatternExplainer` is the seam for a future Bank Reconciliation Agent; the default explainer is a deterministic
template.

## Findings on the 2025+ dataset (2026-10-05)

* 5,597 transactions; decisions: structural 701, rule 403, Standard 5, **human 4**. Human truth is not enough for
  any WHY rule or for a reliable accuracy measure.
* Discovery: Chase ORIG CO NAME — covered by the active General Rule; Zelle `ZELLE PAYMENT TO … JPM99` — a new
  structural candidate (705 transactions, 52 names, support evidence only).
* Backtest (support tier, agreement only): WHO coverage 64–91% in 2026 with 0 false positives; manual WHO work
  634 → 169. WHY: nothing learnable.

---

## Actionable suggestions only (BANK_ACTIONABLE_CLASSIFICATION_LEARNING_001)

Product Owner principle: Classification Learning shows ONLY what needs a human decision.
The engine is unchanged in what it discovers; what changed is what counts as known and what is shown.

| Pattern state | Stored | Shown on Classification |
|---|---|---|
| New DETERMINISTIC pattern (`SUGGESTED`) | yes | **yes** — Type, Pattern, Target, Evidence, Exceptions; Review / Test / Approve / Reject |
| Rejected, re-proposed on materially new evidence | yes | **yes**, marked "Previously rejected — new evidence available" |
| Same conditions as an active WHY Rule but a different WHY | yes | **yes**, marked "Conflict" |
| Covered by an ACTIVE General / WHO / WHY Rule (`COVERED`) | yes (audit) | no |
| Approved (`APPROVED`, `routed_to` the rule) | yes | no — it lives in its rule area |
| Rejected (`REJECTED`, fingerprint memory) | yes | no |
| PROBABILISTIC (cannot become a rule) | yes | no |

Coverage is decided by discovery itself (`pattern_discovery.find_candidates`), before anything is stored:

* **General Rule** — identical markers, or an active rule that extracts the same value from every
  transaction the candidate matches (functional equivalence);
* **WHO Rule** — an active rule of the same WHO whose phrase contains, or is contained in, the candidate phrase;
* **WHY Rule** — an active rule of the same WHO and WHY with the same conditions, or with no condition.

`pattern_discovery.actionable_suggestions` is the page's list; `suggestions` (every state) remains for audit and tests.
Discover Patterns reports only `New patterns found: N`, or `No new classification patterns to review.`

The temporal backtest is a development tool: `pattern_discovery.backtest` and `POST /bank/learning/backtest`
are kept (the route for administrators only); its button and results table are no longer on the page.
