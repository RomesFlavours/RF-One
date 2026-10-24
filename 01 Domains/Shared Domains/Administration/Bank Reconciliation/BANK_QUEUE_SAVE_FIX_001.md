# BANK_QUEUE_SAVE_FIX_001

1. Observed failure: applying an extractor to all existing transactions without complete recognition profiles attempted to autoflush a newly queued bank_import_reconciliations row with a NULL input_state. The rule and queued rows were rolled back; the conversation remained available.
2. Fix: obtain eligible rule versions and the transaction snapshot before adding a new queue job. Initialize mandatory fields in its constructor. Preserve existing requeue behavior and transaction boundaries.
3. User messages: unexpected exceptions remain fully logged on the server; the UI shows a short message without raw SQL/database details.
4. Validation: regression test saves an extractor against multiple existing transactions with no matching profiles, checks complete queue rows and unchanged classifications, and repeats against existing jobs. Existing future/archive and rollback tests are also checked.
5. No schema changes, historical applications or financial edits are part of this repair. Resume with a fresh preview from the preserved conversation.
6. Restore: deployment output contains bank_before.db, source backups and deployment.json.
