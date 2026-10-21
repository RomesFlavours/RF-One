# BANK_ENGLISH_UI_001 — Bank display language

1. Observed: Bank had mixed English and Italian copy; Account has no existing language preference or translation framework.
2. Decision: use English throughout Bank for now, as authorized. Recognition profiles is the English label for Foto segnaletiche.
3. Implementation: translate navigation, review tables, example choices, chat/editor dialogs, preview, import status, history, rollback, errors and built-in guidance. New AI replies and research summaries are requested in English. Standalone pages use lang=en; browser display formats use en-US. Existing user-authored names, rule instructions, catalog entries, transaction descriptions and stored chats are preserved.
4. Scope: no Account language selector, database migration, reclassification or change to reconciliation behavior. Route keys, policy formats and statuses stay intact.
5. Checks: Python AST structure unchanged apart from text constants; Jinja templates parsed; JavaScript syntax checked. Runtime checks and backup references are in the deployment output.
6. Traceability: source changes and backups listed in deployment.json; database backup bank_before.db in the same output folder. Current schema unchanged.
