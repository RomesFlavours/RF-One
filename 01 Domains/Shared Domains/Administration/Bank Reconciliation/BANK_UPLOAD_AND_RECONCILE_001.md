# BANK_UPLOAD_AND_RECONCILE_001 — Upload and Reconcile, with no month to choose

**Status:** implemented in the worktree `rf-one-bank-simple-who-rules` (not released). Product Owner instructions
2026-11-02 and 2026-11-03. Supersedes, for the daily work, the month-by-month path of Import and Review and any
possibility of proceeding with missing files.

## 1. The path

```
UPLOAD FILES -> CHECK COMPLETENESS -> RECONCILE AUTOMATICALLY -> COMPLETE BY HAND -> QBO
```

`/bank/work` (tab **Upload and Reconcile**, first Bank tab and Bank entry) and `/bank/work/qbo`. No month, period or
session is chosen. Code: `bank_reconciliation/intake.py` (integration, completeness, the gate),
`bank_reconciliation/qbo_books.py` (QBO), `RF-One Web/bank_work_routes.py`, `bank_work_research.py`,
`bank_work_gate.py`. Help: `templates/bank_how_it_works.html` (#upload-and-reconcile, #quickbooks-online).
Migration: `c8f420261103` (additive).

## 2. Upload and integration

Type from the content, Source from the account digits in the file name; Bank asks only what it cannot settle.
Integration reuses the existing import; rows already stored on the same Source (date + normalized description +
signed amount) are left out counted occurrence by occurrence — the same file adds nothing, a fuller file adds only
what is missing, identical purchases stay separate. Nothing stored is changed. Every file is an `INTAKE_FILE`
record. Uploading never starts any processing.

## 3. Completeness criteria (exact)

| Case | Result |
|---|---|
| File waiting for an answer (Source, incomplete Source, unreadable rows, Source to confirm, unknown layout, failed) | blocking |
| Work start | control start if configured, else the first day any bank file covers |
| Period a file proves | DECLARED (two YYYYMMDD dates in its name, ≤ 400 days apart, containing its movements), CONFIRMED (a person's fact, must contain its movements), else MOVEMENTS (first–last movement, labelled as such) |
| Required range of a Source | from the work start (or its stated start) to the last day **its own** files cover (or its recorded end): no later day is ever asked |
| Source with no file, not closed, not stated unused | blocking question: upload / not in use / no movements / closed |
| Files begin after the work start, no stated start: up to 10 days | normal |
| — 11–31 days, no whole calendar month | uncertainty (not blocking) |
| — more than 31 days or a whole calendar month | blocking question: upload / in use only since then / no movements |
| Hole between two DECLARED/CONFIRMED periods | missing statement (blocking) |
| Hole between inferred periods > 31 days or containing a whole calendar month | blocking question: upload / no movements |
| — 11–31 days | uncertainty (not blocking) |
| — up to 10 days | normal |
| Source whose data end > 3 days before the latest file of any Source | listed ("reconciled up to"), not blocking |
| Amazon reports loaded, Amazon movement of a Source already paid through a report, outside every report's period, not decided | blocking |
| No Amazon report loaded | note only |
| Classification of single movements | never blocking |

Answers are `COVERAGE_FACT` records (who, when, Source, dates, note). "In use since" also writes the Source's
start date; "Closed" uses the existing lifecycle. Earlier month resolutions NO_ACTIVITY / NOT_EXPECTED count for
their months. A recorded start date counts only when earlier than the first movement (a derived birth proves
nothing). Multi-Source files (no single Source) are not used for the per-Source coverage.

## 4. The one gate

`intake.require_ready` (server side) for: Upload and Reconcile's start, Configuration → recalculate, the Amazon
page's analysis, Guided Reconciliation's new runs (`api/runs`) and AI investigations (`api/runs/<id>/investigate`),
the legacy runs (`/bank/flow/runs`). Not gated: reading, configuration, simulations that apply nothing, decisions,
approvals and chat on single movements.

## 5. Automatic reconciliation

Background run: Amazon product proposals (existing consent) → single engine → internet research
(`cbank/three_stages.py` reused: adapter, prompt, validation, dining policy). Researched: WHO unknown; WHO known
with WHY open (WHO fixed). Not researched (kept for a person): WHY rules in conflict, incomplete split, missing
document, card payments, owners' relationship, personal Source with business WHAT, missing category. Identical
descriptions (pattern, direction, Source type, owner kind, recognised WHO, and the reuse context below) are
researched once, three per request. Answers are kept by the fingerprint of what was sent (facts, WHY catalog, known
WHO names, instructions) and of the local context that decides their use (`bank_work_research._context`: the Source
owner at the movement date — an answer for a person's Source is never reused for a company's —, the WHO mode, the
state of the applicable WHY rules): reused when all are unchanged, asked again when any changes; validation always
runs with the current rules. Provider errors are recorded as such (PROVIDER_ERROR, distinct from UNRESOLVED and
NOT_AUTHORIZED), not cached, retried by the next run; after 3 consecutive errors the run stops calling. The stage
needs its own authorization (date, direction, Source type, owner kind and web search exceed the 2026-10-17
consent), asked on the page with the exact list, kept in `bank-chat-provider-consent.json` (`web_research`).
Nothing is written to decisions by the run; confirming the same proposal twice records it once.

Verified with a local fake provider only (`test_bank_upload_and_reconcile_http`, sections F–H). Still to verify with
the real provider (ChatGPT through Codex): shape and quality of real answers, latency of a batch of three, real
error modes (timeouts, refusals, partial JSON), cost per request.

## 6. Results

Final state (disjoint, sums to the total): Decided (HUMAN decision in Bank) · Applied automatically (matched own
transfers / card payments) · Resolved automatically = complete PROPOSAL (catalog WHO + WHY, or complete split) ·
To confirm (internet proposals) · To reconcile by hand (with reason). WHO origin (disjoint, sums to the total):
person · WHO Rule · name/alias · context (no WHO by design) · internet identified · internet generic · none.
WHO without WHY and incomplete splits are never reconciled. Confirmation (all automatic proposals, or one group of
internet proposals) writes HUMAN decisions, WHAT from WHY, one allocation to the configured WHOM, no WHO → WHY
association; a WHO identified on the internet and absent from the catalog is created; generic WHOs are not
confirmable as such; anything decided meanwhile is skipped. The 2026-11-02 report's "1,599 reconciled, 1,391
confirmable" meant: 1,599 engine RECONCILED, of which 208 matched transfers/card payments (now "Applied
automatically") and 1,391 complete proposals (now "Resolved automatically").

## 7. QuickBooks Online

**Per company** (migration `d3a520261103`). Each LEGAL reporting entity is its own QBO company: its chart
(`bank_qbo_accounts.reporting_entity_id`, imported from that company's Account List export: names, types, no Ids; a
new import deactivates accounts no longer listed), its correspondences (`bank_qbo_account_maps`, unique per
company/kind/local id, status VERIFIED / PROPOSED / GLOBAL_LEGACY) and its files (`bank_qbo_export_batches`). A
correspondence is VERIFIED only against the same company's chart; an account of another company is refused. "Copy
as proposals" copies another company's verified WHAT correspondences as PROPOSED (Source accounts are never copied),
used for nothing until a person verifies each in the destination chart. Correspondences that existed before
(global) are migrated as GLOBAL_LEGACY with no company: never used, only shown as suggestions. A movement whose
company cannot be determined is blocked (NO_OWNER) with the concrete reason (`qbo_books.owner_reason`).

Entities: Purchase (money out; card refund with Credit = true), Deposit (money in on a bank account), Transfer
(matched own transfer or card payment, once for both legs; blocked between companies or with the relationship to
decide). Personal-owner Sources excluded.

States, kept apart: **Preview** (JSON, writes nothing) → **File generated** (one company, batch GENERATED,
movements recorded FILE_EXPORTED with batch and company) → **File downloaded** (same stored content, counted,
creates nothing) → **Import confirmed** (by a person after importing in QBO; needs at least one download) or
**Withdrawn** (by a person, with reason, only before confirmation: the movements become exportable again with the
same journal number `RFB-<movement>`) → **API accepted** (not implemented; `qbo_books.SEND_PREREQUISITES`). A
movement changed after export — lines, accounts or company — is CHANGED_AFTER_EXPORT and never re-exported
silently. Duplicate protection: one export row per movement (`uq_bank_qbo_export_transaction`), with its company.

### 7.1 Export format, checked against Intuit's official documentation (2026-11-03)

| Question | Official answer | Consequence in Bank |
|---|---|---|
| Journal-entry import | Settings → Import data → Journal entries; required Journal No., Journal Date, Account Name, Description, Debits, Credits; Name required only on A/R and A/P lines; sub-accounts as "Parent:Sub"; all plans, Simple Start to Advanced [1] | Only those six columns; no A/R or A/P lines; account names = Account List full names |
| File size | Imports accept spreadsheets with fewer than 1,000 rows [2] | At most 990 lines per file, whole entries only |
| Purchase with split vs journal entry | Purchase = an expense with a payment account and lines; Credit = true is a card refund [3] | The CSV keeps ONE line on the bank/card account and one per category: one payment stays one register line. A JE has no payee (not in vendor/1099 reports) |
| Bank-feed duplicates | A downloaded transaction can be matched to invoices, bills, checks, receipts, transfers, credit card payments and refunds [4] — journal entries are not listed | A file is generated only after the person confirms the feed items of those accounts will be excluded, not added |
| Card payment | "Pay down credit card" / Credit Card Payment [5] | CSV: Dr card / Cr bank, one entry, never an expense; API: Transfer |
| Own-account transfer | One transaction affecting both accounts; the other feed leg is matched to it [6] | One entry for both legs |
| Subscription | Class and Location: Plus/Advanced; multicurrency: not Simple Start; bill import: Advanced (US) [7] | None of these is used by the file |

Not confirmed in official documentation (to verify with a test import): the date format (MM/DD/YYYY is written),
the behaviour of a repeated Journal No. ("Warn if duplicate journal number"), line grouping rules, a
CreditCardPayment API entity, the Accounting API `requestid` maximum length.

Sample: `03 Software/RF-One Web/tests/build_qbo_sample.py` builds one company's six cases (simple expense, expense
with two categories, card refund, deposit, own transfer, card payment) into `tests/qbo_sample/` (file, preview,
Account List, `CHECKS.md`, `VERIFY_IN_QBO.md`). **QBO import not yet verified.**

[1] https://quickbooks.intuit.com/learn-support/en-us/help-article/import-export-data-files/import-journal-entries-quickbooks-online/L4tQBwbs7_US_en_US
[2] https://quickbooks.intuit.com/learn-support/en-us/help-article/import-export-data-files/common-questions-importing-data-quickbooks-online/L4OYJRFdj_US_en_US
[3] https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/purchase
[4] https://quickbooks.intuit.com/learn-support/en-us/help-article/bank-feeds/match-online-bank-transactions-quickbooks-online/L6qyw0PvP_US_en_US
[5] https://quickbooks.intuit.com/learn-support/en-us/help-article/pay-bills/record-payments-credit-cards/L7IjpiWLZ_US_en_US
[6] https://quickbooks.intuit.com/learn-support/en-us/help-article/banking/transfer-funds-accounts/L9E8Kvsoy_US_en_US
[7] https://quickbooks.intuit.com/learn-support/en-us/help-article/class-list/turn-class-tracking-quickbooks-online/L1uqOta7C_US_en_US ;
https://quickbooks.intuit.com/learn-support/en-us/help-article/track-location/set-use-location-tracking/L2raFkEBC_US_en_US ;
https://quickbooks.intuit.com/learn-support/en-us/help-article/multicurrency/learn-multicurrency-quickbooks-online/L5krkKQi8_US_en_US

## 8. Open points

1. Where a company's accounts are on QBO bank feeds, the journal-entry file needs the feed items excluded by hand;
   the matching-compatible path (Purchase / Deposit / Transfer through the API) needs the QBO connection.
2. The vendor (payee) is not carried by a journal entry.
3. Multi-currency movements are not handled (all Sources are USD today).
