# BANK_WHO_SEARCH_TEXT_001 — WHO Search Text

**Status:** implemented (2026-10-25), Product Owner request. **Page:** `/bank/who-search-text`
(Rules and profiles → *WHO Search Text*).

## Purpose

The person manages the text that recognises a WHO in a bank description. This is the simple recognition
the Product Owner validated on the real database (2026-10-25): a WHO is recognised on a movement when its
description contains, as whole words, the WHO's name or one of its aliases (both compared on the WHO
identity key, `who_recognition.who_key`; texts shorter than 4 characters are not used).

## BANK_WHO_RULES_001 — one WHO recognition, page and engine (Product Owner, 2026-10-25)

- The page is **WHO Rules** in the Bank menu (`/bank/who-search-text`), the page where WHO recognition is
  defined and refined. WHO Pattern Training and Discover WHY Patterns are out of the main path (code and data
  kept; WHY Patterns stays off unless `RFONE_BANK_WHY_PATTERNS=1`).
- **One shared path**, `who_search_text.WhoRecogniser`, used by the page and by the reconciliation engine
  (`cbank/engine.py`), on the same rules (`flow.entries(future=True)`):
  1. guided AI rules, by precedence — WHO rules anchored on a text; then the WHO named by older approved text
     rules (made mainly for the WHY); then WHO rules anchored on nothing. Disagreement within the deciding
     level → review (`RULES_DISAGREE`). A name a rule reads is shown under its catalog WHO when it is that WHO's
     name or alias;
  2. WHO name/alias search, only where no rule read a WHO: one WHO → proposed; several (or an alias held by
     several WHO) → review (`TEXT_AMBIGUOUS`); never an invented WHO.
- **No other WHO recognition**: history memory and AI no longer recognise a WHO in the engine (code kept, off;
  `CBANK_WHO_EXTRA=1` restores it). A matched transfer/card-settlement leg keeps its counterparty as WHO
  (CONTEXT): it is the pairing of the two legs, not a recognition from the description.
- Human WHO decisions stay protected (engine decision 38); recognition is a proposal, the history is never
  reclassified. Decision 86 unchanged (Source = accounting subject).

### Both recognitions visible on WHO Rules (2026-11-01)

When the page became *WHO Rules*, the rules section kept its heading, but the second recognition was left as an
unnamed "All bank movements" list, so *WHO Search Text* no longer appeared anywhere in the interface. Restored:
the page introduction names both recognitions, and the second section is headed **WHO Search Text** ("THEN ·
NAMES AND ALIASES") with its explanation; its "By" column and filter say *Search Text (name / alias)*. Only
labels changed: recognition, routes, catalog and data are untouched.

## Recognition order (Product Owner, 2026-10-25)

1. **WHO recognition rules first.** The AI rules that read the WHO in the description (`flow.identity`, the
   rules the reconciliation engine runs first as well). A movement read by a rule is not searched further:
   its WHO is the rule's ("By: Rule"; *not a WHO yet* when the name read is not in the catalog — the rule
   never creates a WHO). Rules that disagree leave the movement unrecognised ("Rules disagree").
2. **Then names and aliases** (below), only for the movements no rule read.

Reason: the plain text search often fails where a rule is needed (e.g. `ORIG CO NAME:PAYPAL … IND
ID:JETBLUEAIRW 081 IND NAME:…` holds PAYPAL, TRANSFER and JETBLUEAIRW at once).

### WHO recognition rules section

Above the movements, the same AI rule editor as Rules and profiles — one markup
(`_bank_flow_rule_dialogs.html`), one script (`flow.js`), one set of routes (`/bank/flow/...`): **+ AI rule**
opens the conversation with the AI; its Preview shows the movements the rule applies to; Save stores it;
each saved rule has **Discuss** (modify), **Rename** and **Delete**. After any change the movements are read
again.

The extraction rule gained one condition, **`require`**: literal texts the description must all contain
("if you find PAYPAL" → `require: ["PAYPAL"]`). A required text makes a rule anchored (never generic) and a
different format family; rules without it keep their key unchanged. Example:
`{require:["PAYPAL"], start:"IND ID:", end_mode:"marker", end_markers:["IND NAME:"], suffix_policy:"numbers"}`
reads `JETBLUEAIRW`; a name made only of digits reads nothing.

## The page

One row per movement: **Source, Date, Description, Amount, WHO recognised** (`null` when none), and a
button that opens the movement's modal.

The modal (close X top right, **Save WHO**, **Cancel**) shows:

- the movement's text as it arrived from the bank file (every field of its raw row);
- **Text to search**;
- **Alias of WHO**: every active WHO in alphabetical order (names only, never their aliases), shown empty.

Save WHO:

| WHO chosen | Result |
|---|---|
| a WHO | the text becomes a HUMAN alias of that WHO (family `WHO_SEARCH_TEXT`) |
| empty | a new WHO with the text as its name, through the one creation path `manual_reconciliation.create_who` (an existing WHO with the same identity is reused, never duplicated) |

A text that is already the name or an alias of **another** active WHO is refused, never taken over.

## WHO-WHY-WHAT association

When the WHO just saved (new or existing) has no active possible WHY, the modal closes and the
association modal opens: possible WHY (each shown with its WHAT) and default WHY. It is saved by
`configuration.save_who`, the same implementation as Configuration → WHO; the WHO's name, state and
entities are kept unchanged.

## What it never does

Nothing here writes a WHO, WHY, WHAT or classification on a movement: recognition is a view; saving writes
only the catalog (WHO, alias, WHO-WHY association).

## Implementation

`rfone_data_store/bank_reconciliation/who_search_text.py`, `RF-One Web/bank_who_search_text.py`,
`templates/bank_who_search_text.html`, `static/bank-assistant/who_search_text.js`; test
`tests/test_bank_who_search_text_http.py` (isolated copy of the local database).
