# Interviews TEST fixes, 2026-11-02 (NOT deployed)

Status: committed on branch `shelbi/interviews-fixes`, based on `codex/interviews-aws-test-20261101` (`ac22288`). Nothing was pushed, built, deployed or migrated. No AWS resource or shared database was touched. Pino deploys.

## What changed

1. **AI timeout and web workers.** One interview turn waits at most 75 s for the AI (`interviews/provider.py`, `AI_TIMEOUT_SECONDS`). `ai_client.generate_json` takes an optional `timeout`: Bedrock gets `Config(read_timeout=75, connect_timeout=10, retries max_attempts=1)`, Anthropic gets `timeout=75, max_retries=0`. On expiry the participant sees "The AI took too long to answer. Please try again" (HTTP 503) and the saved conversation is unchanged. Callers that pass no timeout (Selection, Bank, Tips) behave as before. The rfone-web Dockerfile now runs `gunicorn --workers 2 --threads 8 --worker-class gthread --timeout 120`. `interviews.js` shows the same "try again" text when a gateway answers 502/503/504 with an HTML page.
2. **AI answer ceiling.** `ai_client.MAX_OUTPUT_TOKENS = 16000` replaces 4,096 in both provider calls. The change is byte-identical to `3a08239` on `shelbi/selection-position-profiles`, so the two branches merge without a conflict.
3. **Consent.** The Start page has a required "I agree" checkbox: answers are saved in RF-One and used to build the company's know-how, and administrators can delete them. The server refuses "start" without it (HTTP 400, no AI call). `interview_sessions.consent_given` and `consent_at` record it.
4. **Delete.** On the results page, an account with Organization > Interviews can delete an interview with its answers and results (CSRF-protected POST, required confirmation box checked again on the server). Each deletion adds an `INTERVIEW_DELETE` event to the person's directory history (who, when, interview id, status; no content).
5. **Quotations.** Quotations are compared with the answers after normalising case, quote marks, apostrophes, dashes, the ellipsis and whitespace. A candidate whose quotation is still not found is left out instead of failing the whole Complete; the results page shows how many were left out.
6. **Results visibility.** Every account with the Interviews item sees all interviews and their results, not only the requester. The list has a "Requested by" column.

## Database

New additive migration `e1b220261102` (`migrations/versions/e1b220261102_add_interview_consent.py`), `down_revision = e0a120261101`, the revision recorded on AWS on 2026-11-01. It adds `consent_given` (boolean, NOT NULL, server default false) and `consent_at` (timestamp, nullable) to `interview_sessions`. Existing rows read as "no consent recorded". The image running now never names these columns, so it keeps working after the migration.

The chain on this branch has one head, `e1b220261102`. Checked with `check_migration_chain.py` from `origin/fix/shared-migrations` (`1fc0f38`) against this tree: `MIGRATION CHAIN OK head=e1b220261102 contains AWS revision e0a120261101`. When `fix/shared-migrations` and this branch meet, `migrations/aws_applied_revision.json` moves to `e1b220261102` only after the migration has run on AWS.

`tools/apply_interview_consent.py` applies exactly this revision, like `apply_interviews_test.py` did for the first one: PostgreSQL only, advisory lock, accepts only `e0a120261101` (applies) or `e1b220261102` (already applied), refuses anything else.

## Order for the release

1. RDS snapshot.
2. Run `tools/apply_interview_consent.py` once as a short-lived `rfone-jobs` task.
3. Build and roll out the rfone-web image from this branch.

If the image goes out before the migration, Interviews pages answer "Interviews are not available yet" (503) and the rest of RF-One is unaffected. Rollback: restore the previous image identifier; the two new columns can stay.

## Verified offline

- `RF-One Web/tests/test_interviews.py`: 24 passed (13 before these changes). New checks: consent refused without the checkbox (JSON and plain form, no AI call), consent stored on start; delete is permission-gated (participant and non-Interviews account 403), CSRF-checked (400), needs the confirmation box, removes the row and writes the audit event without content, and a delete during an AI turn gives 404 instead of a server error; typography-only quotation differences pass, an unsupported quotation is dropped and counted; a second Interviews admin sees results and the listing; the AI timeout returns a 503 "try again" with state unchanged; Bedrock and Anthropic receive the timeout and `MAX_OUTPUT_TOKENS`; the Dockerfile CMD; the consent migration upgrades and downgrades on top of `e0a120261101` and the chain has a single head.
- Regressions: `test_image_layout_startup.py` passed, `test_employee_directory_http.py` 10 passed, `test_account_item_access_http.py` 92 passed, `test_accounts_and_domains_http.py` 38 passed, `test_startup_no_migration_no_write.py` 4 passed, `test_ai_client_provider_selection.py` 14/14, `test_bank_ai_rules_http.py` 44 passed.

Not exercised: a real AI call, a real 75 s timeout against Bedrock, gthread under real load, and the migration on PostgreSQL (tested on SQLite only).
