# PayPal evidence import

Scope: Bank-only evidence, uploaded through `/bank/work/upload`. No transaction
classification or accounting writes. The recovered local shell remains read-only.

Accept the English PayPal activity CSV and text-based monthly PayPal statements.
Keep original files and observations, transaction IDs, statuses, currencies,
funding accounts and reference IDs. Store reports in the existing BankFlowArtifact
table. Deduplicate identical files by SHA-256; merge identical observations across
overlapping reports without losing state changes. A statement enriches CSV facts
by transaction ID and currency; it does not create a second payment. Conflicting
amounts or multiple accounts are exposed, never silently resolved. CSV exports
without an account identifier remain unscoped; do not automatically assign a
company or a bank account. Authorization, funding, refund and currency conversion
events are evidence, never automatically counted as expenses.

Reject unreadable/incomplete files atomically, with a useful message. PDF support
requires `pypdf>=6,<7`. Scanned/image-only statements require a text export instead.
This importer does not automatically reconcile bank movements. Ref IDs and funding
account details are available for the reconciliation consumer.

## Validation and activation

Six tests in `test_paypal_import.py` cover repeated files, overlapping status
updates, identical observations, conflicting amounts/accounts, malformed input,
the existing `receive()` function and both user-provided source files. All passed
on 2026-11-13 using an in-memory SQLite database. The supplied CSV contributes 343
rows / 282 transaction-and-currency keys; the March PDF contributes 23 observations
on existing keys, including the KaTom refund reference and Chase funding account.
Python and Jinja syntax checks passed. Contextual help was updated alongside UI.

Install `requirements-paypal.txt` in the target application's Python environment.
Put the data-store and web directories on PYTHONPATH to run the test script.
The recovered `app.py` still blocks POST and opens the live database read-only;
this task did not relax that gate, restart the server, or import into live data.
Activate and verify the uploader in the intended writable home environment.

Changed files: `bank_reconciliation/paypal_reports.py`,
`bank_reconciliation/import_session.py`, `bank_work_routes.py`,
`templates/bank_work.html`, `templates/bank_how_it_works.html`,
`requirements-paypal.txt`, `test_paypal_import.py`, this document.
