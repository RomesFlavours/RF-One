# CV Selection SP on real CVs (SELECTION_SP_REAL_CVS_001), 2 November 2026

**Status: NOT deployed.** Branch `shelbi/sp-cv-reading-fixes`, built on `release/selection-cv-delete`
(`e54dadb`, the release running on AWS as `sel-ef8f32439f0b`). No migration, no new table, no new setting.

## What changes

### Reading the CV (the Friday "not recognized" CVs)
- **Name, email and phone are read with the AI again, in the background.**
  - The SP queue reads the CV with the AI before SP's evaluation (`sp_queue._process`). This fills the name,
    email and phone of the candidate and of the person, which the duplicate checks and the interview
    invitation use.
  - The manager's upload and the public application page stay fast, because the rule-based reader still runs
    at import and no AI call is made while someone waits.
  - Each CV is read by the AI twice: once for identity, once for SP's evaluation, which is sent without
    contacts.
  - When the Job doesn't allow AI résumé reading, nothing is sent, as before.
- **The rule-based reader no longer takes a date range as a phone number.** Before, "2019 - 2021" became
  phone `20192021`, and two different applicants with that job date became "the same person" by phone.
  - A phone now needs 10 to 15 digits on one line and can't be made only of years.
  - This is in the shared Data Store, `deterministic_parser._find_phone`.
- **Identity fixes when the AI reads a CV again** (`cv_reading.apply_profile` and `_refresh_identity`):
  - A person's name or contact is replaced only when it is blank, or still exactly what the first reading of
    this CV put there (for example "RESUME" as the name), or a "phone" that isn't a phone. Anything typed,
    confirmed, or coming from another CV of the same person is never overwritten.
  - A name, email or phone the rule-based reader found and the AI left out is kept.
  - An email or phone that another person already has is not copied. It becomes a "possible duplicate"
    suggestion to confirm.
  - Persons are never merged or split automatically. When a CV is linked to a person with other applications
    and the AI reads a different name, the import note says "Check the person".
- **Scanned PDFs:**
  - A PDF with under 80 characters of text has its first 4 pages read by the AI as images.
  - Each image is at most 1,600 px and under Bedrock's image limit. Phone photos, and anyone uploading a huge
    page, can't use up the server's memory.
  - The call is bounded to 25 s with no retries.
  - The same scan uploaded again is an exact duplicate (hash of the file), with no second AI call needed.
  - A scan that can't be read says so: "Scanned PDF with no text inside: ...".
- **The AI reply parser tolerates null or odd fields** (`llm_parser._dicts`) instead of failing the whole CV.
  There is also one JSON retry at import.
- **"Read again with the AI" on the SP page,** for CVs imported before this release:
  - It runs in the background: the request returns at once, and the page shows the progress on reload.
  - One CV failing never stops the others, and a CV that failed is tried last next time.
  - It doesn't repeat SP's evaluation.
  - The button can't be pressed twice.
- **Upload:** a request stops starting new files after 25 s and lists the rest as "Upload this file again".
  The Upload button shows "Uploading…" and can't be pressed twice.
- **AI answer cap 4,096 → 16,000 tokens** (`ai_client.MAX_OUTPUT_TOKENS`). It's only a ceiling.

### Scoring and fairness
- **Jobs held at the same time:**
  - a gap is measured from the latest end reached so far;
  - a job certainly held inside a longer one (for every reading of year-only dates) is not a job change or a
    short stay;
  - it still counts as experience.
- **The "Short stays" switch now changes the ranking.** With it off, the stability requirement is shown as
  not counted and isn't used for the group. The rule's text says so.
- **Stability:**
  - it starts as **Preferred** in new Jobs;
  - even as a Must-have (Jobs already approved keep their setting), a pattern computed from dates alone
    places a candidate in B (to verify at interview), never in D.
- **The Skills section ends at any usual heading** ("Experience", "Work History", "Education", ...) in any
  case.
- **Short quotes:**
  - A quote under 3 words and under 15 characters supports level 2 (partly shown) at most.
  - The exception is the verified title or employer of a job with verified dates ("Server", "Olive Garden",
    2019 - 2023), which stays real evidence, so a sparse CV is not treated as a weak one.
- **Sensitive words:**
  - added gender, sex, sexual orientation, race, skin colour, citizenship, "US citizen", immigration, visa
    status, national origin, veteran status and military status;
  - the filter now also applies to requirement explanations and job duties;
  - restaurant words ("Visa" cards, "colour-coded", "veteran server") are not filtered.
- **Analyses made before this release are marked "Analyzed before the 2 Nov checks: update recommended".**
  Analyze updates them, so one Job never ranks CVs checked under two sets of rules.

### Other
- **A completed human interview is read-only until Reopen,** which is logged. Autosave and Save are refused
  and say why, and pressing Complete twice is harmless.
- **Queue lease:** 5 → 10 minutes.
- `sp_routes.has_profile` now reuses `sp_queue.has_profile`.

## Tests (offline, SQLite, fake AI)

| Test | Result |
|---|---|
| `test_sp_real_cvs.py` (new: real-shaped CVs, reader, scans, rules) | 35/35 |
| `test_sp_integration_http.py` | 29/29 (2 new: AI identity reading in the queue; Read again end to end) |
| `test_sp_engine.py` | 30/30 |
| `test_cv_delete_http.py` | 30/30 (run from PowerShell; the 3 headless-Edge checks render nothing when started from Git Bash) |
| `test_selection_workspace_http.py` | 89/89 |
| `test_selection_process_http.py` | 30/30 |
| `test_batch_upload.py` | 39/39 |
| preselection, target role, outcome workflow, acting identity, login mode, Aruba bridge, schema startup | all pass |
| Data Store `test_selection_*.py` (engine 659/659, CV structure, coordination, FOH team leader, indicators, transitions) | all pass |

Not tested here:
- a real Bedrock call;
- a real scanned CV through the whole upload;
- Postgres. The code paths are the same; the tests use SQLite.

## To release (Pino)
1. Build `rfone-selection` from this branch, as for `sel-ef8f32439f0b`. There is no migration.
2. On each SP Job that already has CVs, press **Read again with the AI** once.
3. Press **Analyze** to update the analyses marked "Analyzed before the 2 Nov checks".

Existing rankings change on deploy: a candidate who was in D only because of stability moves to B.

## Known and not changed
- **People already merged by a fake phone are not split automatically.** A CV linked to a person with other
  applications whose AI-read name differs gets "Check the person" in its import note. Check those under
  Duplicates.
- **An autosave already in flight at the moment Complete is pressed can still land.** This is an older race,
  and the window is under a second.
