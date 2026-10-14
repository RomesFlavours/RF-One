# Bank > AI Rules — natural-language rules, previewed on a whole period

**Tasks:** BANK_AI_RULES_001 (first version), BANK_AI_RULES_002 (flow redesigned by the Product Owner),
BANK_AI_RULES_003 (deterministic rules, "Crea WHO mancanti"), … BANK_AI_RULES_008 (structured-v3: default WHY,
"Da confermare", only-if-different, replacement, mandatory coverage, no automatic AI fallback)
**Status:** Implemented on `feature/bank-simple-who-rules`. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** migrations `c5e1a7d3b9f2` (001), `d8b2f6c4a1e7` (002) — new tables —, `e4a9c1f7d3b5` (003) —
columns on the AI Rules tables —, `f7c3a9e1b5d8` (005) — two new tables — and `a8e4c2f6d0b3` (006) — operative
rules, versions, applications — and `b2f8d4a6c1e9` (007) — Personal classification, branches. Nothing outside the
AI Rules tables altered by a migration; classifications are
written only by an explicit application or by the import for a rule enabled "Per il futuro".

---

## The flow (BANK_AI_RULES_002)

A Bank tab, **AI Rules**, next to **Rules**.

1. **Movements of a period.** From / To; every in-scope movement of the period (the Review/Export scope:
   no confirmed or suppressed duplicate), classified or not, with date, description, amount, Source and current
   WHO/WHY. Each row has an **AI Rules** button.
2. **The AI Rule window.** Opened from a movement: the movement and its current classification (the
   *starting transaction*, the rule's example and context), a field for a rule in natural language,
   **Preview**, **Save Draft**.
3. **Preview.** The rule is evaluated on **every** movement of the period — and on the starting transaction too
   when it lies outside the period. The window shows the movements examined, the matches and, separately, the
   doubtful cases; per movement: date, description, amount, current WHO/WHY, a short reason and the WHO/WHY the
   rule proposes, when it names them. The starting transaction is marked, and the window says whether the rule
   matches it. Changing the rule text marks the preview **Superseded**; Preview runs again.
4. **Drafts.** A rule is saved as a draft with its starting transaction (link and snapshot); drafts are listed
   on the page and reopen in the window.

| Question | Answer |
|---|---|
| Several AI calls? | One call every 40 movements, 4 at a time. An unreadable answer is split in two and asked again (down to 10). |
| Truncation? | Never silent. If any call fails, the whole preview is FAILED with the reason and no partial result. A period of more than 1,500 movements is refused with a message asking for a shorter one. |
| What does the AI receive? | Per movement: date, description (runs of 8+ digits masked to their last four), amount and direction, Source (name, type, owner), current WHO/WHY. Plus the rule, the starting transaction, the WHO catalog (with possible WHY), the WHY catalog and the optional general AI instructions. Never credentials or full account/card numbers. |
| Existing or new WHO/WHY? | Decided by RF-One (exact WHO name; WHY code or name). Anything else is **New — suggestion only**, never created. WHO always in upper case. |
| What is written? | Only drafts, previews and preview items (`bank_ai_rule_drafts`, `bank_ai_rule_previews`, `bank_ai_rule_preview_items`) and the general instructions (`bank_ai_instructions`). No decision, allocation, WHO, WHY, traditional rule or Standard is created or changed; no rule engine is called. |
| Which AI? | The existing RF-One abstraction, `selection.parsing.ai_client.generate_json` (`RFONE_AI_PROVIDER`: Anthropic or AWS Bedrock). Provider and model are shown and recorded. A missing or failing provider is reported; an answer is never simulated. |

## Deterministic rules and "Crea WHO mancanti" (BANK_AI_RULES_003)

**Why.** Judged movement by movement, the AI was unreliable on long batches: with the Zelle rule it declared
"no JPM" on seven descriptions that contain JPM (the text sent was correct — resent unchanged, the same batch
was answered correctly) and, the other way round, "contains JPM" on numeric-only codes.

**How now.** Every preview first asks the AI only to INTERPRET the rule. When the rule is *"the description
starts with A, later contains B; the WHO is the text between"* (WHY not set), RF-One **code** applies it to
every movement (`method` CODE, one AI call in all):

| Check | Behaviour |
|---|---|
| Starts with A | At the start of the description, upper or lower case alike. |
| Contains B | The first occurrence after A, as written — also attached to a code (`JPM99cy6r3de`). |
| WHO | The text between A and B, spaces normalized, upper case. |
| WHY | Unchanged. |
| No B (e.g. numeric code only) | **Not matching** — never a doubtful case. Counted and stated in the window. |
| Nothing between A and B | Doubtful case. |

The interpretation is trusted only when A and B appear literally in the rule's own text; otherwise, and for any
other kind of rule, the AI evaluates movement by movement as before. The window says which way was used.

**"Crea WHO mancanti"** — an option of the single rule (saved with the draft). A WHO extracted correctly but
absent from the WHO list is shown as **"Nuovo WHO da creare"**, never as a doubt. **"Inserisci nuovi WHO in
elenco"** — usable only after a completed preview that is still current (same text, same option) — creates the
missing WHO of the certain matches: each distinct name once, an existing WHO reused (`who_rules.check_new_who`:
same name with case and spaces aside, or the same registry identity), so pressing again creates nothing. A new
WHO is created by the existing WHO service (`configuration.save_who`): active Counterparty, no WHY — nothing
invented. It changes the WHO list only: movements, classifications, traditional rules and Standards are untouched.

A name that is already another WHO by registry identity — e.g. the name of a WHO a person merged into another,
kept as its alias — proposes that WHO and the row says so; it is never re-created (the existing rule:
a merged name is neither recreated nor reactivated). Example: `GIOVANNA WINE REP` → `GIOVANNA`.

## "Personal" and if / otherwise branches (BANK_AI_RULES_007)

**What "Personal" means.** Bank records no separate "Personal" flag on a Source: the distinction is the Source's
OWNER, as recorded in the Source configuration — `PaymentInstrument.owner_reporting_entity_id` (a person, a
`ReportingEntity` of type PERSONAL) or `PaymentInstrument.legal_entity_id` (a company). A card's owner is the owner
of the account it settles to on the movement's date (`card_configuration.accounting_account_for`). This is the same
derivation the Monthly Export uses (`export.OwnerIndex`). The AI Rules engine reuses it, three-valued:

| Source owner (card: via its settlement account on the date) | Classification |
|---|---|
| a PERSONAL reporting entity | Personal |
| a company (Legal Entity, or a LEGAL / VIRTUAL reporting entity) | not Personal |
| no owner recorded, or a card with no settlement account on that date | **missing → Da verificare** (never "not Personal") |

`economic_allocation.resolve_payer` (the payer of a For Whom allocation) would call an account with no Legal Entity
"personal" even with no owner recorded; that inference is deliberately NOT reused.

"Carta Personal" = Source is a card AND classified Personal; "non Personal" = classified not Personal. The previous
reading ("Personal" = "owner is a Person", `source_owner_kind`) is gone: interpretations are keyed by a new engine
version (`structured-v2`), migration `b2f8d4a6c1e9` cleared the structure of saved interpretations that used it
(their text and raw answer are kept), and an operative version still carrying it is never executed (apply refuses it,
the import skips it) until saved again.

**Branches.** A rule may have conditions and assignments for every match plus branches checked in order — the first
whose conditions hold assigns its WHO / WHY; a last branch without conditions is "otherwise"; an assignment may be
"Da verificare". If a branch cannot be decided because the classification is missing, the fields it — and any later
branch — would set are "Da verificare" and never assigned; if no branch applies, they stay unchanged. A movement
whose every field is "Da verificare" is a doubtful case. The window shows each branch's conditions and assignments
and the data checked. A part of a rule the engine cannot express is declared (the AI answers OTHER, naming it) —
no simplified version is ever executed.

## Structured-v3: default WHY, "Da confermare", only if different, coverage (BANK_AI_RULES_008)

**Why.** A rule such as *"if the description contains A followed by B (any case), the WHO is the text between,
upper case; if the current WHO is missing or different, assign it, set the WHO's default WHY (empty if it has
none) and mark the movement 'Da confermare'; if the WHO is the same, change nothing"* could not be represented:
v2 had no default WHY, no empty WHY, no status, no "only if different", required A at the start and matched B as
written. Any such rule fell back to the movement-by-movement AI, which could not carry these instructions either.

**New, general elements** (engine version `structured-v3`; saved v2 structures keep executing unchanged):

| Element | Meaning |
|---|---|
| WHO `between` + `start_at` | `beginning` (v2 behaviour) or `anywhere`: A found anywhere in the description, any case. |
| WHO `between` + `end_case` | `as_written` (v2 behaviour) or `ignore`: B matched in any case. B must follow A; the WHO is the text up to the FIRST following B, trimmed, spaces collapsed, upper case. A or B missing or in the wrong order → not changed; nothing between → doubtful, never applied. |
| WHY `who_default` + `if_missing` | The default WHY registered on the WHO the rule assigns (`BankOccurrence.default_transaction_reason_id`), never deduced. If that WHO has none — or is a new WHO — `clear` empties the WHY, `unchanged` leaves it. A default WHY that is not active is UNRESOLVED. |
| `status: to_confirm` | A movement the rule changes gets a decision in status `NEEDS_HUMAN_REVIEW` — **"Da confermare"**. |
| `only_if_who_differs` | When the movement already has the WHO the rule assigns (case and spaces aside, same registry identity), NOTHING changes: no WHO, WHY or status change (UNCHANGED). |
| `replace_existing` | A different WHO / WHY decided by another rule or an earlier automatic decision is replaced instead of being a conflict. Without it, the v2 behaviour (conflict) stays. This answers, per rule and only when the rule says so, the open point below. |
| `coverage` + `unsupported` | **Mandatory.** The interpretation lists every instruction of the rule and the element that carries it out; an instruction no element can carry out is listed as unsupported. |

**"Da confermare" against the existing statuses.** Bank has two notions, both checked:

| Notion | Where | Effect of "Da confermare" |
|---|---|---|
| Decision status (stored) | `BankTransactionExplanation.decision_status`; resolved = `AUTO_APPLIED`, `HUMAN_CONFIRMED`, `HUMAN_OVERRIDDEN`, `HUMAN_RECLASSIFIED` (`recognition.RESOLVED_DECISION_STATUSES`) | `NEEDS_HUMAN_REVIEW`: not resolved — shown as such in Review and it blocks the Monthly Export until a person confirms. |
| Reconciliation status (derived) | `reconciliation_status.status_of`: Confirmed / Automatic / Needs review | A changed movement has no human or Standard allocation (otherwise it is protected, below), so it is **Needs review**. |

A movement whose For Whom a person already recorded ("confirmed") is PROTECTED when the rule would mark it
"Da confermare": undoing a person's confirmation is a manual act, kept protected like a manual decision.

**Protections — unchanged.** Manual decisions, Reconciliation Standards, own-account movements and movements whose
For Whom is recorded are always PROTECTED: shown in the preview, never executed, whatever the rule says. An
instruction to override them is represented by `replace_existing`, and the window states the protection.

**Blocked, never simplified, never an automatic fallback.** An interpretation that is OTHER, lacks the coverage, or
lists an unsupported instruction is **blocked**: the preview is FAILED with the reason, no simplified version runs,
and no movement is sent to the AI. The movement-by-movement AI evaluation runs only when asked explicitly
(`allow_ai_batches`; no control on the page yet — see Open points).

**Who interpreted the rule.** A preview executed by code records and shows the provider and model of the
interpretation it used — also a saved one reused with no AI call, whatever produced it (e.g. an interpretation
written by a Claude Code session into the cache of a test copy is shown as `CLAUDE_CODE_SESSION`).

**AI mode** (`RFONE_BANK_AI_MODE`, BANK_LOCAL_ENVIRONMENT_001). `PROVIDER` (default when unset): the RF-One
provider abstraction, as before. `SESSION` (the default of the local Bank environment): Bank never calls a provider —
a rule text with a saved interpretation runs by code; one without makes the preview FAILED with "In attesa della
sessione Claude Code (Preview #N)…", 0 AI calls, and the Claude Code session interprets it
(`03 Software/Infrastructure/Bank Local Environment/SESSION_INTERPRETATION.md`), saving it with provider
`CLAUDE_CODE_SESSION`. The page shows the mode in force.

**The window** lists, besides conditions and assignments: the extraction options, the default WHY and what happens
without one, the status, "only if the WHO differs", the replacement, the protections, and one line per instruction
of the rule with the element that represents it.

> **Superseded by structured-v4 (below):** the two paragraphs above on a recorded For Whom. A For Whom no longer
> protects a movement merely because it exists; its provenance decides.

## Structured-v4: For Whom assigned by a rule, protected by provenance (BANK_AI_RULES_010)

**Why.** A rule such as *"after 'IND NAME:' (spaces skipped), if the text begins with 'ANGELI E DEMONI LLC' For Whom
= RFWP; if it begins with 'RF GELATI LLC' For Whom = RFCo; otherwise For Whom unchanged; 'Da confermare' if WHO,
WHY or For Whom changes"* could not be represented: v3 had no For Whom element, and it protected every movement
with a recorded For Whom — so such a rule was blocked as a whole (no partial execution).

**New, general element** (engine version `structured-v4`, spec version 4; v2 / v3 structures keep executing):

| Element | Meaning |
|---|---|
| `for_whom: {mode: fixed, entity}` | For Whom = that entity. |
| `for_whom: {mode: after_text, marker, names: [{name, entity}, …]}` | Decided **on its own, never from the WHO**: the marker's first occurrence (any case), the spaces after it skipped, then the first listed name the text begins with — the COMPLETE name (any case, any run of spaces between its words) followed by the end, a space or other data, never by more letters or digits (`ALFA LLCX` is not `ALFA LLC`). Marker missing or no listed name → For Whom unchanged (the reason is shown). |
| in `branches` | A branch may carry its own `for_whom`; an undecidable branch makes it "Da verificare", never assigned. |

Marker, names and entities must be written in the rule; each entity must be an existing **ACTIVE** reporting entity
(code or name, case and spaces aside) — otherwise the interpretation is **invalid** (an entity is never created).
An interpretation that cannot represent every instruction stays OTHER / unsupported and blocked.

**Writing For Whom.** ONE allocation for the whole amount, status `NEEDS_OPERATOR`, decision source `RULE`, notes
starting with `AI Rule #<id> ` — the same shape as the For Whom chosen on Review Transactions, but with its
provenance recorded. The row's Confirm completes it. When only For Whom changes and the rule says "Da confermare",
a new decision row keeps WHO and WHY and only becomes `NEEDS_HUMAN_REVIEW`; when nothing changes, nothing is
written and the status is kept.

**Provenance instead of presence** (`ai_rules.ForWhomState`):

| Current For Whom | Effect |
|---|---|
| none | assigned |
| chosen by a person (HUMAN, not complete) | kept; WHO / WHY may still change (said in the note); if only For Whom would change → PROTECTED |
| written by a Standard | movement PROTECTED |
| accounting-complete (COMPLETE: confirmed or automatic) | movement PROTECTED |
| written by a rule (RULE, one line, no document evidence) | automatic: replaced by the rule's own earlier output or with `replace_existing`; otherwise CONFLICT |
| uncertain — a split, a line with no decision source (e.g. pending evidence), a line from document evidence | kept, with the reason; if only For Whom would change → PROTECTED |

Manual decisions, Standard decisions and own-account movements stay PROTECTED as before.

**Preview and application** show For Whom current and proposed (preview items: `current_for_whom_name`,
`proposed_for_whom_name`, `proposed_for_whom_id`; application items: `for_whom_before`, `for_whom_after` —
migration `c6d1e9a4f2b7`, additive). The import applies a rule's For Whom to new movements; two rules assigning
different For Whom to one movement are a conflict.

## Structured-v7: cleaning the extracted WHO, exact formats (BANK_AI_RULES_021)

General engine capabilities, written by the interpretation and executed by RF-One code
(`INTERPRETATION_VERSION = "structured-v7"`, spec version 7; v3–v6 interpretations stay reusable):

* **`strip_digits`** (option of every WHO extraction — `between`, `to_end`, `before_final_number`): every digit
  0-9 is removed from the extracted text; letters and punctuation are kept and spaces collapsed
  (`WIX 1259622963` → `WIX`).
* **`require_letter`**: when the extracted (and cleaned) text has no letter, no WHO is assigned and the movement
  is a doubt "Da verificare" — never applied.
* **`after_adjacent`** (`to_end` only): only spaces may stand between the start text and the marker
  (`PAYPAL *TEMU`, `PAYPAL   *TEMU` match; `PAYPAL INST *X` does not). Refused on any other extraction.
* Conditions **`starts_with_word` / `not_starts_with_word`**: the description (leading spaces and case ignored)
  starts — or not — with the text followed by a space or by its end, so `ORIG CO NAME:PAYPAL` is not
  `ORIG CO NAME:PAYPALSI…`.
* **Branches with no "otherwise"** and nothing assigned outside them: a movement where no branch holds is not
  matched by the rule ("apply only to these formats"); such a rule needs no rule-level condition.

Missing delimiters (or nothing between them) still leave the movement unchanged. Applied to the operative rules:
rule #6 (PayPal) recognizes exactly `ORIG CO NAME:PAYPAL` (WHO between `IND ID:` and `IND NAME:`) and
`PAYPAL` + spaces + `*` (WHO to the end); rule #2 (generic `ORIG CO NAME`) excludes descriptions starting with
`ORIG CO NAME:PAYPAL`, which removes the overlap between the two. Test:
`RF-One Web/tests/test_bank_ai_rules_paypal_formats_http.py`.

## "Classificazione" filter of the list (BANK_AI_RULES_019)

Next to the period: **Tutte** / **Senza WHO** / **Con WHO ma senza WHY**, on the WHO and WHY CURRENTLY on each
movement (its current decision; a movement with no decision has no WHO), never a WHO's default WHY
(`ai_rules.classification_filter`). It combines with the period, updates the list and its count, lives in the URL
(`cls`) so it survives the modal, Salva e Applica (the reload drops the rows that no longer match), Disable / Delete
and the instructions; changing it reloads the list with a spinner. With a filter, the select-all reads "Seleziona
tutte le transazioni filtrate" and selects only those; the movements of the period it excludes leave the selection.
It is a filter of the list only: the modal's scopes ("Tutte le transazioni esistenti", the period) are unchanged.

## "Solo WHO" run mode (BANK_AI_RULES_018)

A checkbox of the AI Rule window, off by default, for Preview and for Salva e Applica: only the WHO part of the rule
is executed (`ai_rules.who_only_exec`). The rule's WHY, the WHO's default WHY, WHY "to verify" and For Whom are not
applied (they stay in the rule's text and interpretation for a later phase); a rule that names no WHO for a
movement contributes nothing; a conflict is a different WHO only (a difference in WHY or For Whom is not one).
"Crea WHO mancanti", conditions, protections and doubts are as usual. The mode is part of what a preview authorizes
(`scope_key`, `preview_problem`) and is recorded on previews and applications (`who_only`, migration
`c3d9e1f5a7b2`). It is a run mode, not a rule option: the rule's versions are not changed by it.

## Reusing existing WHO; a clean WHO text (BANK_AI_RULES_016)

For every rule that names a WHO (fixed or extracted), before comparing, creating or saving: line breaks and tabs
become spaces, spaces are collapsed, outer spaces trimmed, upper case (`normalize_who`; `check_new_who` stores the
same form) — no WHO is stored with a line break. Then (`ai_rules._WhoStatus`):

1. an existing WHO by exact name, registry identity or alias, as before;
2. otherwise an existing ACTIVE WHO that identifies the SAME SUBJECT (`ai_rules.same_subject`): its name is the
   start of the extracted text word by word — its last word may continue glued into a longer word (an
   abbreviation) — and every following word is only a suffix or a code (a word with a digit, a word of at most 3
   letters, a legal form such as LLC / INC / SPA). At least 5 letters or digits when the last word continues glued,
   3 when matched by whole words. "KATOMRESTAU PAY" → KATOM; "TEMU 123456" → TEMU; but "GIOVANNA WINE REP" is NOT
   GIOVANNA (further descriptive words), "TEMUCO SA" is not TEMU;
3. two or more such WHO → a DOUBT in Preview ("Dubbio sul WHO"), none chosen, never applied.

A reused WHO brings its default WHY (when the rule assigns it). Preview shows the extracted text and the final WHO
("estratto: … · WHO esistente riutilizzato"; `bank_ai_rule_preview_items.extracted_who_name`, migration
`a1b5c3d7e9f2`) and counts the reuses. Applying assigns the existing WHO — none is created for it.

## Structured-v6: the WHO up to the end of the description (BANK_AI_RULES_015)

WHO `to_end` — `{"starts": ["A1", "A2", …], "start_at": "anywhere" | "beginning", "after": "M" | null}`: the
earliest occurrence of ANY start text (alternatives, any case), then — with `after` — the first following marker M
(any case); the WHO is everything after it up to the END of the description: nothing removed (codes, numbers stay),
outer spaces trimmed, spaces collapsed, upper case. No start text or no marker → not matching; nothing after →
doubtful. The extraction is itself the condition (no `contains` needed for the alternatives). Example: starts
`PAYPAL`, `PYPAL`, after `*`: "PAYPAL *AIRBNB HMSSZ842DA" → AIRBNB HMSSZ842DA; "PAYPAL *TEMU" → TEMU.

**Settled by AI rules = WHO and WHY.** `ai_rules.ai_settled` now counts a movement only when the AI rule's
decision names BOTH a WHO and a WHY. A WHO whose default WHY is missing (`who_default` + `clear`: the WHY is left
empty, to be completed, never invented) is NOT settled: "Solo movimenti non ancora sistemati da regole AI" keeps
offering it. A WHO missing from the list is created only with "Crea WHO mancanti" (otherwise UNRESOLVED).

## One click: Preview interprets a new rule through the local Claude Code CLI (BANK_AI_RULES_012)

In SESSION mode, when the local environment enables it (`RFONE_BANK_CLAUDE_CODE_CLI`, set by Avvia Bank from
`environment.json` `claude_code_cli`), a rule text with no saved interpretation is interpreted in the SAME Preview
request by the Claude Code CLI of this PC (`bank_reconciliation.claude_code_cli`: print mode, no tools, no session
kept, neutral folder; same login as the VS Code session; no AWS). The answer goes through
`validate_interpretation` like any other — partial means blocked — and is saved with provider `CLAUDE_CODE_CLI`.
One interpretation at a time per server process; the database read is released while the CLI thinks. Disabled
(unset / `off`): the preview waits for the session as before. Details and failure messages:
`03 Software/Infrastructure/Bank Local Environment/SESSION_INTERPRETATION.md`.

## Structured-v5: the final number, and an explicit override option (BANK_AI_RULES_011)

**Why.** A rule such as *"the description starts with 'Zelle payment to' and ends with a space and a block of only
digits; the WHO is the text in between; replace WHO / WHY also when manual, Standard or confirmed"* could not be
represented: no condition "ends with a number", no extraction up to it, and the protections could not be lifted.

| Element | Meaning |
|---|---|
| condition `description ends_with_number` | Once trimmed, the description ends with a space and a block made ONLY of digits ("… Cleaning 30541248046"). A final code mixing letters and digits ("JPM99cxov680") is not a final number. No value. |
| WHO `before_final_number` (`start`, `start_at`) | The text after the start text (any case; at the beginning — leading spaces ignored — or anywhere) and before that final number; trimmed, spaces collapsed, upper case; numbers inside the name are kept. No start text or no final number → not changed; nothing between → doubtful. |

**Option "Sostituisci anche WHO/WHY manuali, Standard o confermati"** (`override_protected`) — a **rule option**
like "Crea WHO mancanti", not an element of the interpretation: a checkbox in the AI Rule window, **off by default**,
recorded on the draft, on every preview (part of what the preview authorizes: a preview made with the option off
cannot authorize applying with it on, and the reverse) and on the rule's version (a change makes a new version).
Only for that rule, and only for WHO / WHY (never For Whom, never own-account movements):

* a manual decision, a Standard decision or a confirmed movement is planned as UPDATED instead of PROTECTED — the
  note says "OVERRIDES …";
* the decision written is always "Da confermare", its notes name the override;
* a confirmed movement's single COMPLETE allocation becomes pending for the SAME For Whom (the same
  `_withdraw_acceptance` Review uses); a confirmed split is left protected (its For Whom could not be kept);
* a movement already as the rule says stays UNCHANGED (still confirmed).

Every other rule keeps the protections. At import, protected values are overridden only when every matching rule
has the option.

**Overlaps.** Each planned movement lists the other rules involved: another active AI rule that also matches it
(with "same WHO" when it agrees), the AI rule or the traditional WHO rule (`BankRecognitionRule`) that wrote its
current WHO / WHY. The preview summary counts them per rule. A different value from another active AI rule
stays a CONFLICT.

**Interpretations of previous engines** (`structured-v3`, `structured-v4`; `REUSABLE_PREVIOUS_VERSIONS`). Keys
carry the engine version. A VALID earlier interpretation
is still reused (`ai_rules.saved_interpretation`: it represented its whole rule, with no For Whom); a BLOCKED one is
not — the rule is interpreted again, so a rule blocked only for lack of For Whom gets a new, complete interpretation.

## Save Draft, Salva, Salva e Applica — operative AI rules (BANK_AI_RULES_006)

| Button | Effect |
|---|---|
| **Save Draft** | A draft only: never active, no movement changed. On an operative rule it is a draft of a change (`ai_rule_id`): the rule's current version is unchanged. |
| **Salva** | An OPERATIVE rule (`bank_ai_rules`, ACTIVE) with a new version (`bank_ai_rule_versions`) when the text or option changed — carrying the validated interpretation, so a rule the code can execute needs no AI call to be applied. No existing movement is changed. With **Per il futuro**, enabled for new imports. |
| **Salva e Applica** | Disabled while no scope is chosen. With only *Per il futuro*: saved and enabled, history untouched. With *Tutte le transazioni esistenti* (the whole database) or *Solo le transazioni selezionate* (exactly the selected movements): applied — only on the strength of a COMPLETED preview of the same text, scope, selection and option; without one, the window runs the preview, says why one was needed, and the next press applies **that** preview as long as text, option and scope are unchanged (BANK_AI_RULES_010). |

**Applying after a preview (BANK_AI_RULES_010).** The window compares the rule text in one form — the browser sends a
multi-line field with CRLF line ends while the field holds LF — so a multi-line rule is recognized as the text of its
own preview. When a preview cannot authorize the application, the refusal names the precise reason
(`ai_rules.preview_problem`: no preview; preview not completed, with its message; text changed; scope changed; *Crea
WHO mancanti* changed; selection changed) and nothing is written. A preview authorizes **one** complete application
(`ai_rule_operations.already_applied`): the same request again is refused before anything is saved — never applied
twice, never a duplicate rule; an application left incomplete may be completed with the same preview.

**Scopes.** *Tutte* and *Solo selezionate* are alternatives; *Per il futuro* combines with either; none is
preselected. Rows have checkboxes and *Seleziona tutte nel periodo*; the selection is a set of precise movements,
kept across period changes in the browser tab, never extended by a period change. The preview refers to the chosen
scope (the period shown when none) and any change of text, option, scope or selection supersedes it. A rule the code
can execute is previewed and applied on the whole scope with no size limit.

**What applying does to each match** (`ai_rules.Planner`, shown by the preview and recomputed when applying):

| Outcome | When |
|---|---|
| Protected | a manual (HUMAN) classification, a Standard, an own-account movement for a WHO, a WHY change on a movement whose For Whom is recorded — the existing protections |
| Not applied (unresolved) | a WHO that cannot be one, a new WHO without *Crea WHO mancanti*, a WHY not in the WHY list (never created); doubtful cases are never applied |
| Conflict | a field the rule sets holds a different value decided elsewhere (another rule or an earlier decision), or another active AI rule assigns a different value — reported, never settled by execution order |
| Unchanged | already as the rule says |
| Updated | otherwise: one new RULE decision (`recognition._create_decision_row`, append-only) changing **only** the fields the rule names; a WHO-only rule keeps the WHY, its WHAT and status. With *Crea WHO mancanti*, the WHO is created by the WHO service once per name (names and aliases reused) |

A later application of the same rule may replace its own earlier output; repeating an application changes nothing.

**Per il futuro** — the import runs every ACTIVE rule enabled for the future (code-executable only); since
BANK_RULES_RESET_001 it is the only automatic classification at import (the General Rules, WHY rules and Standards it
once ran between were removed). Rules that match one new movement with incompatible values are all logged as
conflicts and none is applied. A rule the code cannot execute cannot be enabled for the future.

**Log.** Each application (`bank_ai_rule_applications`: rule, version, mode EXISTING_ALL / SELECTED / IMPORT,
preview, import batch, counts, WHO created) and each movement it matched (`bank_ai_rule_application_items`: outcome,
WHO/WHY before and after, the decision written, the reason).

**Operative AI Rules** — listed with version, status, *Per il futuro*, executed by code or AI, last applied;
*Open* (reopen and edit), *Disable* / *Activate*. Existing drafts are kept and never activated automatically.

## General structured rules, saved interpretations, throttling (BANK_AI_RULES_005)

**Why.** A movement-by-movement preview of 809 movements needed 21 AI calls and failed on
`ThrottlingException` at call 10. Most rules do not need the AI to look at each movement at all.

**Interpret once, execute by code — as a general capability.** The AI turns the rule into a verifiable
structure; nothing rule-specific is coded:

| Element | Supported |
|---|---|
| Conditions (all must hold) | the description contains / does not contain / starts with a text (case ignored); the Source name or the Source owner's name contains / does not contain a text; the Source owner is / is not a Person or a Company (a card's owner is the owner of the account it settles to on that date); the Source is / is not a card or a bank account; the movement is / is not money in or money out |
| Assignments | WHO fixed, WHO taken between two texts of the description, WHY fixed; absent = unchanged |

RF-One **validates** the structure — only these elements, at least one condition, at least one assignment, and
every text, WHO and WHY copied literally from the rule (dash style, quotes, spaces and case aside) — then
**resolves** WHO and WHY in the catalogs (the WHO service's identity check; a WHY by code or name) and
**executes** it on every movement of the period. The window shows the interpretation line by line (e.g. *IF the
description contains “BONNE VIE SALON” · WHO: BONNE VIE SALON (existing) · WHY: Owner Personal — Other
(existing, OWNER_PERSONAL_OTHER)*), so it can be checked. A structure that fails validation is not executed:
its reason is shown and the AI judges each movement.

**Saved interpretation.** Kept in `bank_ai_rule_interpretations` (raw AI answer + validated structure), keyed by
the rule text and the general AI instructions: while both are unchanged, later previews reuse it with **no AI
call**; a change of either asks again.

**Movement-by-movement AI evaluation** (rules with no executable form): at most 3 calls at once; a throttling
answer is retried up to 5 times with progressive waits (2, 4, 8, 16, 32 s) and lowers the concurrency by one
(never below 1). Every batch that succeeded is kept in `bank_ai_rule_batch_results` (keyed by the exact prompt):
a preview that still fails is FAILED with *k of n completed and kept* and no partial result; Preview again asks
only the batches missing. Any change of the rule, the catalog or the movements changes the prompt and therefore
the key.

## WHO / WHY pick lists in the AI Rule window (BANK_AI_RULES_004)

Right under the rule field, two lists side by side (one under the other on small screens): **WHO** — the active
WHO by canonical name (upper case) — and **WHY** — every available WHY — both alphabetical, each with its own
search. A click writes `WHO "NAME"` or `WHY "name"` (exact catalog names) into the rule at the last cursor
position of the field — at the end when none is known — never replacing the text, then puts the cursor back in
the field. Like any change of the rule, it marks the previous preview Superseded. The lists only compose text:
no catalog or classification changes.

## What became of the first version (BANK_AI_RULES_001)

Its *Run AI Test on a sample of up to 20* is replaced by the flow above. The general AI instructions stay (an
optional section of the page, sent with every preview). The `bank_ai_test_runs` / `bank_ai_test_results`
tables and their rows are kept for history; nothing writes to them any more.

## Open points

* A field already set by a traditional rule is a conflict for an AI rule (e.g. the Zelle rule against the WHO
  Rule "PAYMENT"), unless the rule itself says to replace it (`replace_existing`, BANK_AI_RULES_008). The same
  plan is used everywhere, so a rule saved "Per il futuro" with that option also replaces at import.
* BANK_AI_RULES_008 removed the automatic fallback to the movement-by-movement AI evaluation: it runs only when
  asked (`allow_ai_batches`). The page has no control to ask for it yet; whether to add one is a Product Owner
  decision.
* Manual and Standard decisions stay protected even when a rule says to replace them (Product Owner decision of
  2026-10-11, "for now").
* Turning an AI rule into a traditional rule is not part of this version.
