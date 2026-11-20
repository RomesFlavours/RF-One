# Indeed position-bound résumé acquisition — implementation report

Date: 2026-11-14. Scope: the Product Owner supplies an Indeed employer candidate
list; personally completes login/SMS in an AWS browser; starts sequential CV
downloads into the Selection position from which the request was launched.

## Result and implementation

Implemented in the primary `03 Software/Selection` source. No AWS resource,
deployment, production data, real candidate import or existing local database
was changed. Notes/classification remain outside this task.

New files:

- `03 Software/Selection/INDEED_IMPORT.md`: approved journey and wire/data contract.
- `03 Software/Selection/indeed_protocol.py`: URL validation and authenticated transport.
- `03 Software/Selection/workspace/indeed.py`: RF-One-authorized launch/control,
  machine callback, current-grant checks and immutable originating position.
- `03 Software/Selection/indeed_worker/{__init__,store,runner,service}.py`:
  durable job checkpoints, visible-UI pagination/downloads, headed browser,
  protected noVNC/WebSocket transport and interruption recovery.
- `03 Software/Selection/templates/workspace/_indeed.html`: inline Applications
  workflow, Italian locally and English for the shared interface.
- `03 Software/Selection/test_indeed_{import,browser,viewer}.py`: synthetic tests.
- `03 Software/Infrastructure/deploy/selection-indeed/`: Dockerfile, pinned
  requirements, startup, privilege-dropping browser launcher, Gunicorn lifecycle
  configuration and AWS deployment/rollback instructions.

Modified: Selection workspace registration/routes/channels/import engine,
`app.py` (machine endpoint authentication boundary only), position template,
workspace layout/help, Selection README and Data Store's import pipeline (optional
source-provider metadata, preserving default manual imports). Previously modified
files and the untracked `AWSSelection` local snapshot were preserved.

CVs use the existing archive (private S3 in production), RawResume/Candidate and
PositionCandidate records. Acquisition channel is INDEED and new documents record
INDEED_BROWSER/indeed provenance. Temporary S3 parsing files and discarded
duplicate S3 uploads are cleaned up. No schema addition is required.

Browser/worker secrets are separate from viewer tickets. The browser receives a
minimal environment and the Linux container drops Chromium to a different uid
from the API service, protecting the service environment and durable ledger.
Only one browser request runs at a time; start revokes the human viewer; stop,
timeout and restart preserve completed checkpoints and require a fresh login.

## Verification

All tests used disposable data, guarded AI and synthetic websites/storage:

| Criterion | Observed result |
|---|---|
| HTTP access, CSRF and position binding | Passed |
| Recheck original operator's current grants on every file | Passed |
| Real Selection import and callback retry deduplication | Passed |
| Private S3 adapter, stored original bytes, position association and temporary/duplicate cleanup | Passed with synthetic S3 client |
| Restart keeps checkpoints and requires new browser/login | Passed |
| Actual offline browser visits two list pages, downloads each file, records missing CV and retries only failure | Passed, ephemeral headless Edge via Playwright |
| Password verification page pauses without scanning | Passed |
| Actual loopback WebSocket/TCP bytes, unauthenticated refusal, Origin check, revocation and expiry | Passed |

Combined command: `python -m unittest test_indeed_import.py
test_indeed_browser.py test_indeed_viewer.py -v`: **9 tests passed**.

Existing `test_selection_workspace_http.py`: **ALL PASSED**, using the same
disposable model-schema fixture described below. No test contacted Indeed,
Bedrock, email, RDS or S3.

How Works: `check_how_works.py --app Selection`: **0 errors** (38 pre-existing
legacy pages remain without Help). Updated the exact position Help, preserved
the modal close X and moved position Help below the title/navigation divider,
right aligned. Targeted diff whitespace check and Python syntax checks passed.
The whole-worktree whitespace check also reports pre-existing CRCRLF in
`Avvia Selection.cmd`; this task did not change that launcher.

## Remaining release checks and limits

- Docker is unavailable on this Windows host. The complete Linux image, Xvfb,
  noVNC frontend and uid-dropping Chromium launch still need container acceptance.
  The WebSocket transport itself was tested with real sockets, not just mocks.
- No AWS deployment or live Indeed/SMS acceptance occurred. The service stays
  disabled until its HTTPS worker URL and secret are configured. Deployment
  instructions list the exact resources, environment and acceptance steps.
- The repository already has multiple Alembic heads. Normal application startup
  against a fresh test DB failed at `upgrade head`; tests therefore explicitly
  built disposable schemas from current model metadata. Migration files and
  production history were not modified. Resolve the existing heads through the
  normal release process before deployment from this checkout.
- The current local launcher uses the separate `AWSSelection` snapshot. This
  change targets primary source and does not silently replace that snapshot.
- Automatic command review rejected removal of the two task-created temporary
  directories `C:/Users/servi/AppData/Local/Temp/rfone-indeed-test-deps` (test
  dependencies) and `C:/Users/servi/AppData/Local/Temp/rfone-indeed-test-gumdndd0`
  (one failed run's synthetic database). The tool supplied only “blocked by
  policy”; they remain in Temp. No deletion workaround was attempted.
- Unsupported/unreadable CVs are failed imports for manual verification/retry,
  not successful candidate records. Indeed UI changes, a challenge or an
  inconsistent page count pause/fail rather than silently claim all files saved.
- A timeout/restart requires login again; cookies/passwords/SMS are not exported
  or stored in the durable ledger. Run `/tmp` and the browser home as tmpfs.

## Traceability and rollback

- Contract: `03 Software/Selection/INDEED_IMPORT.md`.
- AWS instructions: `03 Software/Infrastructure/deploy/selection-indeed/README.md`.
- Rollback: remove Selection's two Indeed environment variables and stop the
  separate worker. Already imported originals and position links remain valid.
  No database migration or data restore is involved.
