# WHO format review under Find standard formats

Product Owner, 2026-10-25: WHO first. The sequence to verify is
Description → standard format → WHO → existing WHO → WHY/WHAT associations → unresolved movements → AI.
This document covers only the first steps (format → WHO). WHY and WHAT are not touched.

## 1. What is restored

- **Find standard formats** on the Rules and Profiles page (`/bank/ai-rules`) with its original algorithm
  (`bank_flow_routes.discovery`): every movement is read, recurring description structures not yet read by
  an approved WHO rule are grouped and sent to ChatGPT, which proposes WHO extraction rules only
  (FLOW_2 `EXTRACTOR`: literal start/end delimiters, exclusions, suffix policy). One fix: an invalid proposal
  no longer discards the other proposals of its batch; it is skipped and reported.
- **Discover WHY Patterns** (`BANK_WHY_PATTERNS_001`) stays in the code, hidden and off; `RFONE_BANK_WHY_PATTERNS=1`
  turns it back on.

### Structures, not identical texts (Product Owner, 2026-10-25)

| Before | Now |
|---|---|
| Only structures seen at least twice were sent to the AI | No frequency threshold: a structure seen once is sent too, as a **candidate**; a rule selecting one movement is shown as "observed once: candidate, not recurring" |
| One pass | Up to three passes: after each, the movements still read by no approved or proposed rule are grouped and examined again |
| The WHO had to follow a literal text | Delimiters may contain the placeholders `{date}`, `{number}`, `{code}` for the parts that vary (e.g. `PURCHASE {date} `, `VISA #{number} `), and `from_beginning` reads a WHO that opens the description (`PUBLIX #1661`, `SEASONS 52 0074503`). Existing rules are unchanged; the engine reads the new ones as it reads the old |
| Movements without a name were simply "uncovered" | The AI may report structures whose description names no counterparty (own-account transfers, checks without payee, interest, fees): counted apart, as a proposal, never as verified |

## 2. Review of each proposed rule

| Element | Behaviour |
|---|---|
| Movements under the rule | EVERY movement the rule selects (code, no AI), in a scrolling table: tick, Source, date, original description, amount, extracted WHO |
| Tick | "This WHO is wrong". Several can be ticked. A review note only: no WHO, movement or classification changes |
| Save review | Keeps the ticks and marks the rule reviewed |
| Correct the rule with AI | Sends the current rule, the person's note and at most three masked descriptions (wrong and right examples, with the extracted WHO; never amounts). The corrected rule is validated, run on the whole history and the changes are listed: WHO changed, no longer selected, newly selected, wrong recognitions fixed. It replaces the proposal in the same search; the previous versions are kept |
| Approval | Unchanged: Discuss and preview on real transactions → Save. Nothing is active before |

## 3. WHO coverage

Each movement is counted once, over all bank movements:

| Line | Meaning |
|---|---|
| Standard formats found | recurring description structures examined by the search |
| Proposed WHO rules | proposals of the search |
| Movements selected | movements at least one proposed rule extracts a WHO from |
| Distinct WHO | different extracted names |
| Read differently by two rules | movements two proposals extract different WHOs from (not counted as verified) |
| Marked wrong | ticked movements still selected |
| Verified | movements of reviewed rules not marked wrong |
| Already recognized by approved rules | WHO from the approved WHO extraction rules, as the engine reads them |
| Without a recognized WHO | neither approved nor proposed rules read a WHO |

Proposed recognitions and verified recognitions are always shown apart.

## 4. Code

`RF-One Web/bank_who_format_review.py`, `static/bank-assistant/who_review.js`, the hook in `flow.js`
(`pollScan`); test `tests/test_bank_who_format_review_http.py` (isolated copy of the local database).
