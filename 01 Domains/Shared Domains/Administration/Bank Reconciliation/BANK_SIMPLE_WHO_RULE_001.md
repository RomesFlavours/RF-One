# Simple WHO Rule

**Task:** BANK_SIMPLE_WHO_RULE_001
**Status:** Implemented on `feature/bank-simple-who-rules` — service, shared modal, Classification page, Review integration, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** no migration. Uses `BankRecognitionRule`, `BankOccurrenceReasonAssociation`, `BankOccurrenceAlias`, `BankWhoRecognition`, `BankTransactionExplanation` as they are.

---

## What it is

The operator teaches RF-One who a counterparty is with one sentence and one button:

| Field | Example |
|---|---|
| WHO | ABC (preselected from the row; searchable) |
| Rule | *Dove nella descrizione trovi ABC il WHO è ABC* |
| Possible WHY | Beer Purchases, Liquor / Cocktail Product Purchases |
| Action | **Apply** |

No match type, pattern, alias or id is ever shown or asked for.

The same modal (`_bank_who_rule_modal.html`, `static/js/bank-who-rule.js`) is used on
**Bank > Classification** and **Bank > Review Transactions**, and posts to one route,
`POST /bank/who-rules/apply`, which calls one service:
`rfone_data_store/bank_reconciliation/who_rules.apply_who_rule`.

## WHO: choose or create, in the same modal

The WHO field is a creatable, searchable combo (fetched lazily from
`GET /bank/who-rules/who-options`; no WHO list is ever rendered into the page):

* **Existing WHO** — active WHO whose name contains the typed text; and the WHO the typed name
  already *is* (same name, same identity key `who_key`, or an active alias), resolved by
  `CanonicalWhoResolver.by_identity`. For such a name no "Create" is offered, so no duplicate can be
  made from the modal.
* **Similar existing WHO** — names that only look alike (one begins with the other, word by word),
  offered for the operator to decide; never chosen automatically and never merged on similarity.
* **Create "<typed name>"** — when the typed name is new. Choosing it marks the WHO
  *NEW WHO TO CREATE*; nothing is written yet.

A new WHO is created by **Apply itself**, through the Configuration service
(`configuration.save_who`: COUNTERPARTY, never GENERIC_OPERATIONAL, no default WHY), only after every
check has passed and in the **same database transaction** as its possible WHY, its rule, the rule's
application and the fragment merges. A refusal or any failure rolls everything back: no WHO without
its rule, no rule without its WHO. A name that turns out to be an existing identity reuses that WHO;
a name held by a merged (INACTIVE) WHO, or shared by several active WHO, is refused.

The result says whether the WHO was **Created** or **Existing**.

## The sentence

`who_rules.parse_rule_instruction` reads the sentence **once, when the rule is saved**,
deterministically (no LLM, at save time or at transaction time):

* "where the description *finds / contains* X (the WHO is Y)" — Italian or English wording;
* X may be quoted (`"Top Linen"`, `“…”`, `«…»`); quotes are required when X itself contains
  words such as *e / o / and / or*, a comma or a slash;
* when the sentence names the WHO, it must be the selected or the new WHO (e.g. *Dove nella descrizione trovi "TABLE TOP LINEN" il WHO è Table Top Linen - WP*);
* the result is the recognition normalization of X (`recognition.normalize_description_for_recognition`),
  at least 3 characters with a letter.

When the sentence does not name exactly one text, nothing is guessed: the operator is asked to
rewrite it (empty, two texts, two places to look, unclosed quotes, too short).

The stored rule is the existing WHO-only shape (BANK_CONFIGURATION_001 D2): `match_field =
DESCRIPTION`, `match_type = CONTAINS_TEXT`, `determines_purpose = false`, no WHY, no instrument or
direction scope, `auto_apply_enabled = true`.

## Apply — one transaction, all or nothing

1. **Validate** — the WHO is ACTIVE; every selected WHY is ACTIVE with a destination; the sentence
   gives one text; no ACTIVE rule gives the same match to another WHO. Any refusal writes nothing.
2. **Rule** — created, or reused (reactivated when it was inactive). Never duplicated.
3. **Possible WHY** — additive upsert of WHO -> WHY associations. An association already active is
   left exactly as it is. A WHY is never applied to a transaction and the WHO's default WHY is never
   set (BANK_WHO_WHY_INVARIANT_001).
4. **Existing transactions** — every transaction whose normalized description matches the rule
   (`recognition._rule_matches`) is judged with the import's own question
   (`recognition.find_candidate_rules`): only when every matching ACTIVE rule names this WHO is
   anything changed.
   * a transaction whose current decision is HUMAN, or came from a Reconciliation Standard, keeps
     that decision. Same WHO -> counted as *already*; different WHO -> **Conflict — human decision
     preserved**;
   * otherwise its current decision, when it does not already name the WHO, gets a NEW RULE decision
     naming the WHO and the rule, with WHY, WHAT, status, confidence and their snapshots carried over
     verbatim (append-only; a transaction whose WHY was open stays `NEEDS_HUMAN_REVIEW`);
   * its WHO recognition (`BankWhoRecognition`, a separate fact from the decision) names the WHO —
     the same result `who_recognition.recognize_transactions` gives through
     `CanonicalWhoResolver` once the rule exists. STRUCTURAL recognitions (RF-One's own accounts) are
     never touched.
5. **Historical fragments** — the ACTIVE WHO records the rule recognises by their own name are
   merged into the WHO only when they are clearly recognizer fragments: recognizer-created
   COUNTERPARTY with the recognizer's upper-case identity name, no merged names of their own, no
   active rule, no Standard, no For Whom entities, never chosen by a person, and every transaction
   they hold moves to the WHO in this same Apply. The merge is the canonical WHO/WHY import's:
   aliases kept and copied onto the WHO, the fragment's name recorded as a `MERGED_WHO_NAME` alias,
   possible WHY and Supplier links carried over, fragment marked INACTIVE with a note — never
   deleted, no decision row rewritten. Any other matching WHO is an ACTIVE different WHO: left as it
   is and listed as *not merged*, with the reason.
6. **Future imports** — the rule stays ACTIVE: `recognition._propose` (import) and
   `CanonicalWhoResolver` (WHO recognition) name the WHO directly; no fragment is created first.

Applying the same rule again makes **zero business changes**.

The result shown to the operator: WHO, rule, existing transactions matched, transactions updated,
already this WHO, human conflicts preserved, fragments merged (and not merged, with the reason),
possible WHY. Never a database id.

## A Rule is not a Standard

| | Rule | Reconciliation Standard |
|---|---|---|
| Knows | description pattern -> WHO (+ the WHO's possible WHY list) | signature -> WHO + WHY + WHAT + For Whom |
| Makes a transaction | known by its WHO; still *Needs review* while its WHY is open | Automatic |

## Classification page

`/bank/classification` is now **only** the place to find WHO that are still separate occurrences
of one counterparty and group them with a Rule. WHAT, WHY and WHO are maintained in
`/bank/configuration`.

* server-side search and pagination (50 per page); a handful of bounded queries;
* per row: WHO, type, transactions, the rules recognising it, **Rule** (preselecting the canonical
  WHO the occurrence most clearly belongs to — its alias owner, or the canonical WHO its name starts
  with);
* merged (INACTIVE) WHO are hidden, and listed on request for audit;
* the initial GET never builds receiver candidates, renders WHO x WHY, or matches anything —
  matching happens only on Apply.

The former all-in-one page survives only as `bank_classification_legacy.html`, rendered by the
What catalog import preview; the receiver-approval and WHAT/WHY/WHO POST routes are unchanged but
no longer linked from Classification.

## Measured (local, SQLite, production-shaped disposable copy)

| | Before | After |
|---|---|---|
| Classification initial GET | 6.2–6.8 s, 18.4 MB HTML (production: worker timeout at 60 s) | 0.14–0.28 s, 63 KB HTML, 21 SQL statements |
| Apply (contains "ABC", 12,678 transactions) | — | ≈1 s, 220 transactions, 9 fragments merged |

## Open points

* The CONTAINS semantics are the existing ones: a substring of the normalized description, so a
  short text can match inside a longer word. The ≥3-character floor limits it; a word-boundary match
  type would be a separate decision.
* Possible WHY are only added by Apply, never removed (removal stays in Configuration).
