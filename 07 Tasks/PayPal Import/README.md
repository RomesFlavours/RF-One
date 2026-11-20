# PayPal importer - recover this work on the home PC

Branch: `handoff/paypal-import-2026-11-13` in `RomesFlavours/RF-One`.
This is a source handoff, not a deployment or a change to main.

## Recover without OneDrive

Open this branch on GitHub, then `07 Tasks/PayPal Import/paypal-import.zip`.
Download the ZIP using GitHub's download button and extract it outside the application.
The ZIP contains all new source files, the integration patch and this guide.
Alternatively, in an existing clone:

```powershell
git fetch origin handoff/paypal-import-2026-11-13
git archive --format=zip --output=paypal-handoff.zip origin/handoff/paypal-import-2026-11-13 "07 Tasks/PayPal Import"
```

Read this README in the extracted package before applying changes. Do not replace
the home application's whole source tree with this branch or overwrite its database.

## Integrate in the actual home application

1. Identify the code directory serving the home Bank application and its Python
   environment. Preserve existing edits and use the normal code/data backup process.
2. From that application's code root, run `git apply --ignore-space-change --check` with the absolute
   path to `integration.patch`. If contexts do not match, adapt the four integration
   changes manually; do not force the patch or copy full older route/template files.
3. Apply with `git apply --ignore-space-change` and the patch path, then copy the contents of `files/` into that same
   application root, preserving paths. The patch adds CSV/PDF handling to the
   existing `receive()` uploader, result counts, report listing and contextual help.
4. Install the dependency into that application's Python environment:
   `python -m pip install -r requirements-paypal.txt`.
5. Add `03 Software/RF-One Data Store` and `03 Software/RF-One Web` to PYTHONPATH,
   then run `python test_paypal_import.py -v`. Six tests passed at delivery, using
   in-memory SQLite. The optional real-source test skips if the owner's CSV/PDF
   files are not present; these files are deliberately not in Git or the ZIP.
6. Restart through the home application's established launcher. Verify the uploader
   accepts the CSV and March PDF, shows repeated IDs without new transactions, and
   has matching help. Do not remove a read-only gate without understanding the
   actual environment. The recovered office shell was deliberately left read-only.

## Local Italian and shared English

`files/` and `integration.patch` use English for the newly added shared interface.
For the owner's local Italian working environment, use `integration-local-it.patch`
instead and overlay `local-it/` after copying `files/`. Do not apply both patches.
The original Italian office working copy was preserved.

## Implemented and tested

Bank-only PayPal evidence; original files retained; CSV/PDF observations merged by
Transaction ID and currency; state changes retained; exact reuploads skipped;
funding accounts and refund Ref IDs extracted from the provided statement; conflicting
amounts/accounts flagged by the evidence reader. Existing bank movements, WHO,
classifications, Payroll and Registry are unchanged. No automatic reconciliation
consumer was added in this task. Scanned PDFs are not supported.

Real samples: 343 CSV rows and 23 PDF observations yield 282 distinct ID/currency
keys. Six tests and Python/Jinja syntax checks passed. The home runtime and UI
still require verification; nothing was imported into a live database.

## Restore

Use the pre-integration code backup or `git apply -R` on the applied integration
patch. Remove only the new files copied by this handoff if no subsequent work uses
them. No schema migration was introduced. Never restore or delete a database just
to undo this code-only handoff.
