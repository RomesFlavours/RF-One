# Indeed résumé acquisition

Approved scope (Product Owner, 2026-11-14): launch from a Selection position,
supply an Indeed employer candidate-list URL, complete login/SMS personally in
the AWS browser, then download each available résumé into that same position.
Notes, candidate classification and automated hiring decisions are outside scope.

## Contract and journey

1. A position manager starts an import in Applications. The server fixes the
   position and requesting RF-One account; neither can be changed by the browser.
2. A separate single-browser worker opens the supplied list in headed Chromium.
   The manager opens its protected remote viewer and performs authentication.
3. Back in Selection, Start/resume scans every list page and each candidate.
   Login/challenge pages pause the run for human intervention. Nothing solves
   verification automatically. Opening candidates can cause Indeed to mark them
   as reviewed, as it does when opened manually.
4. Each downloaded file goes through Selection's existing document store/import
   pipeline with channel INDEED. Production retains originals in private S3;
   PositionCandidate links each application to the originating position.
5. The worker records candidate IDs and import results in durable SQLite, outside
   source control. A failed candidate is retried on resume, a missing résumé is
   reported separately, and successful candidates are not downloaded again.
   Content deduplication also protects a retry after an ambiguous callback result.
6. Stop closes the browser. Restart/timeout requires a new personal login while
   retaining completed checkpoints. One active browser per worker prevents shared
   sessions between requests. Inactive jobs expire after 30 minutes; no cookies,
   password or SMS value is exported to Selection or persisted by the worker.

The worker is disabled until explicitly configured. Its durable job ledger is
technical acquisition state, not a second Selection candidate database. It has
no direct RDS or S3 credentials. Selection rechecks the original operator's
position permissions before accepting every file. No database migration needed.

Deployment instructions: `../Infrastructure/deploy/selection-indeed/README.md`.
Synthetic tests exercise authentication, position binding, pagination,
checkpoints, downloads and recovery. Live Indeed/AWS verification remains a
separate deployment acceptance step, requiring the operator's login.
