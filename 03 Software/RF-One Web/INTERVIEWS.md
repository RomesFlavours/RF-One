# Common interviews first workflow

Status: implementation of the Product Owner workflow specified on 2026-11-01. Architectural reference: `01 Domains/Shared Domains/INTERVIEW_SERVICE_001.md`.

## Approved workflow

An administrator selects an existing person with an active RF-One login and describes the purpose to the AI. The recipient finds the requested interview in MyRFOne on their next visit. The administrator's interview list links to a separate results page after completion. Use generic Interview labels, without a new product name. Both speech and text are required.

## Implementation scope

The recipient is selected from the unified People directory, which reuses existing person identities and includes employees and external people. A linked active RF-One account delivers the task to MyRFOne; the account is not another person record. People without login cannot receive a home task. The requester and recipient are recorded separately. Initially only the creating administrator can inspect their requests/results; the assigned account alone can conduct or complete the interview. Authentication and CSRF reuse the shell. No email/SMS, cross-company sharing, automatic validation, background scheduling or AI-initiated contact is introduced.

The common service persists purpose, specialization, person reference, delivery account, requester, revision, status, transcript and candidate results. Know-How supplies the initial specialization. States are REQUESTED, IN_PROGRESS and COMPLETED. Explicit start generates the first question; each submitted answer generates an adaptive follow-up. The person explicitly completes the interview, producing a summary, candidate knowledge with verified answer references, and unresolved questions. Closing is not approval of the knowledge. Refreshes do not invoke AI or change state. Revision checks prevent duplicate turns and stale completion.

The AI adapter reuses RF-One's existing provider-neutral JSON transport, with no silent simulated fallback. A failed or malformed call does not commit a partial turn. Tests inject a fake provider and use disposable data only. The default implementation calls the configured provider only on participant POST actions; it does not send the account registry, passwords or email addresses.

Browser speech recognition and speech synthesis provide microphone input and spoken questions, with explicit user controls and cancellation. Recognized text can be corrected before sending. Microphone input does not submit automatically. The browser may use its own external speech service; the voice UI explains this before microphone activation. RF-One does not store raw audio in this version. Unsupported browsers and permission/service failures produce explicit messages; speech capability is not claimed universally. Choosing a server-side speech provider and audio retention remains open.

## Delivery and verification

Apply the additive Alembic migrations explicitly before use; application import never migrates or creates schema. Until the migration is applied, the existing home remains usable and interview endpoints report unavailable. Use `/admin/interviews` to request an interview and `/interviews/<id>` to conduct it. The results page is `/admin/interviews/<id>`.

Do not apply migrations to a shared database or deploy automatically as part of development. Run `python "03 Software/RF-One Web/tests/test_interviews.py"` from the repository root. Checks cover account isolation, revoked sessions, CSRF, stale and competing revisions, provider failure, evidence provenance, completion, migration upgrade/downgrade and home integration. Fresh shell import was checked against an absent disposable database and creates no database. A browser workflow was checked with a fake provider and mocked speech recognition/synthesis, including correction before submission and a mobile layout. Speech behavior still needs a real microphone/browser acceptance check; automated mocks do not establish transcription quality.

After review, an operator can apply the new revision with `python -m alembic upgrade f9e220261101` from `03 Software/RF-One Data Store`, using the intended `RFONE_DATABASE_URL`. The interview migration follows `f7c320261027` and the explicit person links follow `f8d120261101`; this checkout also has earlier local changes, so review all pending migration revisions before operating on a shared database. No migration, deployment, real provider call or outgoing notification was performed during development.

The entire local Alembic chain through `f8d120261101` was also applied successfully to a new disposable SQLite database. The no-migration statement above refers to shared/operational databases; temporary test databases were explicitly migrated.

Speech implementation references, consulted 2026-11-01: [SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition) documents limited browser availability and possible server-side recognition; [SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis) documents speech output and cancellation. These are browser capabilities, not a claim that RF-One owns the browser's speech service.

## Interface language

Product Owner decision, 2026-11-01: the interview interface is in English. This includes home tasks, administration, participant pages, results, errors and voice controls. The AI is instructed to generate English questions and results; browser recognition and synthesis use en-US. User-entered purposes and answers are preserved as entered, not silently translated.

## Interview workspace

The participant page shows the requesting administrator, purpose and session status. Before starting it explains the flow. Once started, the current question is separate from the expandable conversation history. A visible preference enables reading new questions aloud; the participant can replay or stop the question. Microphone input and typed text share an editable answer field and explicit submission. Dictation never submits automatically.

The page distinguishes pending text from submitted answers and displays a waiting state during AI requests. The answer field is read-only while a request is pending so a new draft cannot be cleared by the response to an earlier submission. Completion is enabled after at least one saved answer; the backend independently enforces that rule. Pause returns to MyRFOne and preserves submitted turns. The existing unsent-answer guard remains active. Mobile layout and mocked speech controls were checked in a browser; the preview is still explicitly simulated.

The earlier engine comparison is recorded in `01 Domains/Shared Domains/INTERVIEW_SERVICE_001.md`, under "Ricerca e proposta di realizzazione". It is a historical architecture comparison, not a new framework selection for this page.

## Results and unified person linkage

The results workspace includes participant, requester, purpose, dates, AI summary, candidate knowledge, open questions and the original conversation. Evidence links expand the conversation and focus the cited answer. Completion does not validate the knowledge. A person link returns to the single directory record; that record lists only interviews requested by the acting administrator.

The request page selects a person rather than a login alias, the participant workspace identifies the same person, and results retain that stable reference. Login settings link back to the person record. Legacy interviews without a stored person ID resolve only through a confirmed account link. No matching by name or email is performed. See [One people directory](PEOPLE_DIRECTORY.md) for source reconciliation and limits.

Fifteen offline checks cover the original workflow and explicit employee/account links, an external person without login, three-page identity consistency, conflicts, directory permissions and preservation of legacy interview rows through the additive link migration and downgrade. Browser checks include result-to-evidence navigation and the person profile interview history.
