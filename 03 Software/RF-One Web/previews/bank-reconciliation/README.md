# Monthly reconciliation assistant — local interface preview

User-requested replacement design for the AI Rules page, 2026-10-17.

The page preserves RF-One's existing shell, palette and shared stylesheet.
It presents user-authored general policies first, then unresolved movements
grouped by WHO. Clarifications now use a chat, not a WHY-selection form.
The assistant asks follow-up questions, restates the full rule, and requires
explicit confirmation before a preview over the entire database. Known exceptions
remain separate from general rules. Travel has a two-choice, trip-level question.

The approved preview is now available inside the local Bank application at
`http://127.0.0.1:5080/bank/ai-rules`, with the existing Bank access gate.
Its questions are read directly from the working database through a read-only
GET endpoint. The original standalone preview on port 5084 still uses a snapshot.
The previous AI Rules interface remains at `/bank/ai-rules/advanced`.
General-rule edits and conversation history remain in this browser's local storage.
The chat uses Bank's configured AI only after local permission to share the
specified database context is recorded. It sends no monetary amounts or full
account numbers and uses at most three masked descriptions. It does not itself
perform web research or claim to have verified external sources.

The AI returns a proposed complete rule and its executable interpretation. The
existing Bank validator checks it before the confirmation is offered. A signed,
account-bound, expiring token binds the exact rule and interpretation. The preview
requires confirmation, revalidates the structure and uses the canonical Bank
preview engine with scope ALL, including already-classified rows. No second AI
call can silently reinterpret the confirmed rule. The output includes counts,
before/after values, protected/conflicting/unchanged cases and excluded rows.

Only interpretation and preview audit tables may be written. No chat endpoint
applies classifications, creates WHO, changes defaults or writes allocations.
Local consent is stored next to the operational database, not in shared code.
The `/chat` and `/chat/preview` routes use the existing Bank gate and CSRF check.
There is deliberately no application button in this revision.

Integration uses `bank_assistant_preview_routes.py`, the corresponding template
and `static/bank-assistant/` assets in the served Bank worktree. The supported
Bank close/start procedure was used, with no migration or database replacement.
The local data snapshot was prepared as generation 11; OneDrive upload was not
yet confirmed, which does not prevent reopening on the same PC.

`snapshot.json`, copied shared assets and screenshots are local preview data.
The travel dialog is labeled as an example, not a trip detected in the data.
The precedence of an explicit travel answer versus card ownership is still
unresolved and is displayed under the travel rule.

Run a local static server in this directory to view `index.html`.
The standalone static server cannot execute the chat; use the Bank page on 5080.

Validation: `test_chat_flow.py` exercises clarification, unsupported rules,
missing consent, missing CSRF, missing confirmation, tampered tokens, account
binding, exact confirmed interpretation reuse, full-database scope and unchanged
operational tables against a private disposable database. AI output is mocked
only in that test. `test_local_chat_ai.py` is a separate real-provider check and
requires explicit permission to share the specified database context.
