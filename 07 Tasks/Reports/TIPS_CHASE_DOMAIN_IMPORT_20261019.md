# REPORT

## 1. Requested outcome and implementation

Imported the user-supplied Chase PDF reconstruction into the AWS master as historical paid-tip evidence in the Restaurant Tips domain. The authenticated Tips application now has a dedicated historical-payments view linked from Saved Periods. This is operational source evidence, not another standalone reconstruction file and not a new calculation/finalized payout run.

The existing provenance tables were sufficient: a dedicated `CHASE_PDF` source, one IngestionRun and immutable document/row SourceRecords. No schema migration was required. Source rows use document SHA256 plus physical row ordinal; identical-looking entries remain independently traceable to their PDF positions. Every observation preserves recipient, amount, send date, memo, page, status, interpreted period and review flags.

## 2. Imported result

| Measure | Result |
| --- | ---: |
| AWS import | 116235 |
| Source rows preserved | 700 |
| Completed explicit tip rows wholly inside the scope | 325 |
| People displayed, including zero-payment reference recipients | 23 |
| Recorded paid tips, January 1–October 4 scope | USD 253,490.62 |
| Cross-year tips, separate and not apportioned | USD 5,512.73 |
| Explicit tips with unclear full period | USD 140.37 |
| Extra exact repeated observations, retained for review | USD 269.44 |

One tip recipient lacks a unique exact employee match and remains visibly unresolved. No employee was invented, renamed, classified as a trial or linked through a fuzzy name guess. The literal memo intervals are retained even where not standard Monday–Sunday weeks.

The displayed total establishes what the PDF records as paid, not daily earned amounts, original voluntary-tip/gratuity composition, or an allocation rule. Pay and blank memos do not become tip amounts. Cross-year entries cannot establish the January 1–4 portion. A separate document selector prevents the UI from adding overlapping imported documents together automatically.

## 3. Integrity and tests

- Seven isolated regression tests passed locally, against the exact staged deployed-source candidate, and inside the image build. They cover idempotency, duplicate preservation, exact-name restaurant scope, unresolved/ambiguous identity, source mutation rejection, invalid money/status exclusion, transaction rollback, HTTP rendering, authentication requirement, unknown document rejection and absence of a POST action.
- The first HTTP test fixture lacked module registration and then a Location table required by the existing branding processor. Both fixture defects were corrected before the passing runs; no failed test was ignored.
- A real second AWS import verified idempotency: the same run and observations were reused without writes.
- The first ad-hoc fingerprint selector returned an empty table list. It was corrected to explicit prefix selection with an empty-list failure guard. Verification then covered all 11 protected Tip tables. An independent verifier also compared them against the saved baseline from before this PDF import and confirmed them unchanged.
- Bank bytes matched before/after and against the previous saved baseline. The importer never connected to Bank. SQL write guarding allowed inserts only into SourceSystem, IngestionRun and SourceRecord; it blocked schema changes and updates/deletes or any writes to financial/calculation tables.
- The exact candidate route was rendered using AWS readonly connections: USD 253,490.62, the unresolved recipient, duplicate-review amount, document references and navigation link were verified. This controlled candidate rendering uses a test authentication identity; it is not represented as a live authenticated user session.

## 4. Publication

The release is based on the deployed source archive, with only five changed files: the historical-payments service, isolated tests, new template, new read-only Tips endpoint and Saved Periods link. Unrelated working-tree changes were not included. The image build ran the tests before publication.

Release tag: `tips-history-20261019T124050Z`.

Image digest: `sha256:ac6952338aedf8587948162937d7d669eef4a8132405bb544dc639cc976800f1`.

Only the AWS `rfone-tips` App Runner service was updated. Bank, RF-One Web, the Clover acquisition jobs and correction poller were not deployed or restarted. App Runner operation `c7789215979449a5aad81984d07ae400` completed SUCCEEDED and the service returned RUNNING with the new image. The public link was opened in the browser: the new endpoint correctly redirects an anonymous session to the existing RF-One login with a return URL to document 116235. No live user credentials were entered or impersonated. Final live-publication evidence and source backup are recorded in `tmp/tips_historical_release/release.json`.

## 5. Protected boundaries and remaining review

No TipDistributionCalculationRun, TipEntitlement, TipPaymentCycle or TipPaymentInstruction was created or modified. Historical observations do not become eligible for a new payout or Payroll finalization. Existing immutable consolidated periods and the earlier Clover reconstruction are preserved.

Unresolved identity, uncertain causals/periods, cross-year portions and possible exact duplicate observations remain explicit review items. The PDF has no transaction IDs, so the application neither deletes repeated entries nor declares them independent bank settlements. The full PDF remains at the user's supplied local path; the AWS evidence preserves its hash and parsed observations, not a new copy of the PDF binary.

## 6. Traceability and restore

- Domain contract: `01 Domains/Business Domain/Restaurant/Tips/Historical Tip Payments.md`.
- Source PDF: `C:/Users/servi/Downloads/Payment Activity - chase.com.pdf`.
- PDF SHA256: `e3177df81e178a6780f2db4290a144fc44253dc8ff6c85c34665615300148e35`.
- AWS provenance: source `CHASE_PDF`, run `116235`, entities `tips_historical_document` and `tips_historical_payment`.
- Domain view: `https://rfone.romesflavours.com/tips/historical-tip-payments?document=116235` (existing RF-One login required).
- Private import evidence and protected-table fingerprints: `output/tips_reconstruction_2026/domain_import.json`.
- Independent prior-baseline proof: `output/tips_reconstruction_2026/verification.json`.
- Readonly rendered candidate: `output/tips_reconstruction_2026/domain_view_rendered.html`.
- Publication/previous source configuration: `tmp/tips_historical_release/release.json`; previous source archive and immutable candidate archive in that directory.
- Import and publication helpers: `tmp/import_chase_tips_domain.py`, `tmp/publish_historical_tip_view.py`, `tmp/check_historical_tip_view.py`.

An application rollback can restore the previous image configuration recorded in the release evidence without deleting the preserved source observations. No financial data restore is needed.
