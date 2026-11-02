# CV Selection SP on real CVs (SELECTION_SP_REAL_CVS_001), 2 November 2026

**Status: NOT deployed.** Branch `shelbi/sp-cv-reading-fixes`, built on `release/selection-cv-delete`
(`e54dadb`, the release running on AWS as `sel-ef8f32439f0b`). No migration, no new table, no new setting.

## What changes

### Reading the CV (the Friday "not recognized" CVs)
- **AI reading at import for Server and Line Cook again.** `sp_upload` no longer passes `ai_reading=False`.
  When the Job allows AI résumé reading, the import reads the CV with the AI and fills the name, email and
  phone of the candidate and the person, so the duplicate check and the interview invitation work.
  SP's evaluation is unchanged and still runs once, and the Selection evaluation is still not run for SP Jobs.
  Each CV is now read by the AI twice: once at import, for identity, and once by SP, for the evaluation,
  which is sent without contacts.
- **Scanned PDFs.** A PDF with under 80 characters of text has its first 4 pages read by the AI as images
  (`cv_reading.transcribe_pdf`, through Bedrock Converse, only when AI résumé reading is allowed).
  Before, they stopped at "No extractable text".
- **JSON retry at import.** One broken AI reply is asked once more instead of falling back to the
  rule-based reader. This is the same rule SP already uses.
- **"Read again with the AI"** on the SP page, for CVs imported without the AI (everything uploaded to SP
  before this release). It reads the stored text again, fills a blank name, email or phone, and redoes the
  duplicate suggestions. It doesn't repeat SP's evaluation. It has a time budget per click.
- **AI answer cap 4,096 → 16,000 tokens** (`ai_client.MAX_OUTPUT_TOKENS`). It's only a ceiling.

### Scoring and fairness
- **Jobs held at the same time:**
  - a gap is measured from the latest end reached so far;
  - a short job held inside a longer one doesn't count as a job change or a short stay.
- **The "Short stays" switch now changes the ranking.** With it off, stability is shown as "not counted" and
  isn't used for the group. Before, only the flag disappeared.
- **Stability:**
  - it starts as **Preferred**, not Must-have;
  - even as a Must-have, a pattern computed from dates alone places the candidate in B (to verify at
    interview), never in D.
- **The Skills section ends at any usual heading** ("Experience", "Work History", "Education", ...) in any
  case, not only at headings in capitals. Before, duties under a Title Case "Experience" counted as mere
  claims.
- **Quotes too short to document work** ("Server", "POS": under 4 words and under 20 characters) support a
  claim at most (level 1, or competence "claimed").
- **Sensitive words:**
  - added gender, sex, sexual orientation, race, colour, citizenship, visa, immigration, national origin
    and veteran status;
  - the filter now also applies to requirement explanations and job duties shown to the manager.

### Other
- **A completed human interview can't be changed by autosave.** Changes need Reopen, which is logged. The
  page says so.
- **Queue lease:** 5 → 10 minutes, so a slow reading with throttling waits and the JSON retry isn't run
  twice.
- `sp_routes.has_profile` now reuses `sp_queue.has_profile`.

## Tests (offline, SQLite, fake AI)

| Test | Result |
|---|---|
| `test_sp_real_cvs.py` (new: real-shaped CVs) | 20/20 |
| `test_sp_engine.py` | 30/30 (2 checks updated to the stability rule, 2 added) |
| `test_sp_integration_http.py` | 27/27 (the call count now includes the AI reading at import) |
| `test_selection_workspace_http.py` | 89/89 |
| `test_selection_process_http.py` | 30/30 |
| `test_batch_upload.py` | 39/39 |
| preselection, target role, outcome workflow, acting identity, login mode, Aruba bridge, schema startup | all pass |
| `test_cv_delete_http.py` | 27/30. The 3 "Edge" browser checks fail the same way on `release/selection-cv-delete` without these changes (they need a local Edge driver). |

Not tested here: a real Bedrock call, a real scanned CV through the whole upload, and the "Read again"
button through HTTP. The first real upload after release should check these.

## To release (Pino)
Build `rfone-selection` from this branch, as for `sel-ef8f32439f0b`. No migration.

After release, open each SP Job that already has CVs and press **Read again with the AI** once (again if the
message says some are left).
