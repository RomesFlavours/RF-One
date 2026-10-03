# Selection — Resume Screening (MVP)

**Task:** TASK_SELECTION_001, extended by TASK_SELECTION_002 (multi-résumé batch import)
**Canonical documentation:** `01 Domains/Shared Domains/Selection/ResumeScreening/` (Selection Core) and `01 Domains/Business Domain/Restaurant/Selection/` (Restaurant Industry Extension).

A small local web app to screen résumés for Rome's Flavours' Server role: upload one or many PDFs at once, each résumé is parsed independently into a structured Candidate CV Profile, and the candidate detail page shows Facts, Derived Information, Flags/Questions and Indicators as four clearly separate areas — never one combined score.

## How it works

- **Batch upload.** The candidate list page's import form accepts multiple PDF files at once (native multi-file picker, plus drag & drop). Each file is uploaded and processed independently via `/api/upload` (one JSON call per file) — the page shows a live WAITING → PROCESSING → COMPLETED/FAILED/DUPLICATE state per file and an aggregate "x / y processed" count while the batch runs. One file failing (wrong format, unreadable PDF, parsing error) never stops the rest. If JavaScript is unavailable, the same multi-file input still works via a classic form POST to `/upload`, which processes every selected file server-side and shows a results summary inline.
- **Duplicate detection.** Each résumé's extracted text (or, failing that, its filename) is hashed and checked against previously imported résumés for the same client before a new Candidate is created — an exact re-upload **for the same target role** is reported as `DUPLICATE` and creates nothing; for a target role the document has no application for yet, it creates a new application reusing the document and its extracted facts (SELECTION_FOH_TEAM_LEADER_001, verified in `test_target_role_http.py`). See `rfone_data_store/selection/parsing/dedup.py`.
- **Source metadata.** Every candidate records where its résumé came from: `source` (`LOCAL_UPLOAD` today), `source_provider` (`manual` today), `source_file` (original filename) and `created_at` (import timestamp) — shown on the candidate list and on each candidate's "Source & Extraction Information" section. The shape already supports a future non-file `ResumeSource` (e.g. an API integration) without changing `CandidateCVProfile` or the parsing pipeline.
- **Parsing.** Every upload's raw text is extracted for real (pdfplumber, same approach as `03 Software/InvoiceIntake/`). Structured extraction then tries a real AI provider first (Anthropic, if `ANTHROPIC_API_KEY` is configured — see `rfone_data_store/selection/parsing/ai_client.py`); with no credentials configured in this environment, it automatically falls back to a **DEMO/MOCK** parser that deterministically selects one of three realistic fixture candidates. The candidate list and detail page always show a clear `DEMO / MOCK` vs `REAL AI` badge — never disguised. `source`/`source_provider` always reflect the true acquisition channel (e.g. `LOCAL_UPLOAD`/`manual`) regardless of which parser ultimately produced the structured content.
- **Reading the Experience section (rule-based reader, SELECTION_CV_STRUCTURE_READING_001).** Verified with synthetic résumés in `03 Software/RF-One Data Store/test_selection_cv_structure.py`:
  - The same experience gives the same title, employer, location, dates and duties whether it is written as `Title, Employer, City, ST | Mar 2022 - Present`, as `Title, Employer` with the dates on the next line, or as title, employer and dates on separate lines, also when entries are not separated by blank lines (each date range then starts an entry, and the up to two title/employer lines above it move with it).
  - With title and employer on separate lines, the line carrying the location (`City, ST`, on the same line or on its own line below) is the employer. With one line, `Title at Employer` is explicit; `Title, Employer` (or `-`, `|`) is read with that long-standing convention and labelled as such.
  - When nothing shows which line is the job title and which the employer (or there is no title/employer line, or one entry contains several date ranges), neither is recorded: the experience is marked **Reading uncertain — verify** on the candidate page, quoting the original lines; an `EXTRACTION_UNCERTAIN` VERIFY flag asks a person to check the résumé; and the import is reported as `PARTIAL`, never `COMPLETED`.
  - A missing fact (no employer, no dates, no contacts) stays empty and is not, by itself, an uncertain reading.
  - The original file, the full extracted text and each experience's own text (`evidence_snippet`) are kept unchanged.
- **Career transitions need positive evidence (SELECTION_TRANSITION_EVIDENCE_001).** Verified in `03 Software/RF-One Data Store/test_selection_transition_evidence.py`: a missing job title (a "to be clarified" question), an unrecognized one (a question on what the role involved) or an uncertain reading (only "Reading uncertain — verify") never produces "Transition from Non Hospitality". A transition is read only from a role the Restaurant extension positively classifies; no role is classified as outside hospitality yet, so that question does not appear on real résumés today. The rule itself was checked with a synthetic classification inside the test, which is not evidence that other sectors are recognized.
- **Target role per application (SELECTION_FOH_TEAM_LEADER_001).** Verified in `test_target_role_http.py` and `03 Software/RF-One Data Store/test_selection_foh_team_leader.py`: importing (single or batch) requires choosing the target role — Server or FOH Team Leader, no preselection; without it nothing is imported. The choice is saved on each application of the batch; the same person can hold applications for different roles. The candidate list and page analyse each résumé for its application's target role; with none or an unsupported one, the page says the target role is to be clarified and computes only the role-independent part — never Server by default. FOH Team Leader titles (explicit, or generic ones — Team Leader, Shift Lead, any "Supervisor" — with a dining-room context), Chef de rang as Server, and the "declared role, duties not verified" wording are described in `01 Domains/Business Domain/Restaurant/Selection/README.md`.
- **Declared coordination responsibilities (SELECTION_COORDINATION_EVIDENCE_001).** Verified in `03 Software/RF-One Data Store/test_selection_coordination_evidence.py`: the candidate page lists, in a compact section, each duty that declares coordinating, assigning, training, supervising or liaising for other people, with its experience, area, declared number of people and original sentence, plus one neutral interview question per item (or one general question when there is none). It never changes the role, adds months or scores; an uncertain reading asks to verify which experience the duty belongs to. The rule is rule-based wording, mainly English with a few Italian verbs.
- **Business logic.** Lives entirely in `03 Software/RF-One Data Store/rfone_data_store/selection/` (`core/` = industry-agnostic Selection Core, `industry/restaurant.py` = the Restaurant Industry Extension, `parsing/` = the ResumeSource → RawResume → ResumeParser → CandidateCVProfile pipeline, `import_pipeline.py` = the duplicate-checked per-file import orchestration used by both the batch UI and the tests). This app is routing/templates only.
- **Persistence.** Reuses the existing RF-One Data Store mechanism (SQLAlchemy + Alembic) — see `migrations/versions/b8f1c4a2e6d9_add_selection_resume_screening_schema.py` and `migrations/versions/2e9125cf954b_add_selection_batch_import_metadata.py`. By default this app uses its **own** local database, `data/selection.db`, deliberately kept separate from the shared production `data/rfone.db` so demo/mock candidate data never mixes into real Rome's Flavours operational data. Point `RFONE_DATABASE_URL` at the shared store instead if the Product Owner wants Selection unified into it later — the schema is fully compatible.

## Requirements

- Python 3.10+
- The `03 Software/RF-One Data Store/` dependencies (SQLAlchemy, Alembic — see its own `requirements.txt`), since `app.py` imports `rfone_data_store` from there.
- Optional, for real AI parsing instead of the demo fallback: `pip install anthropic` and set `ANTHROPIC_API_KEY` (env var or repo-root `.env`, same convention `rfone_data_store/database.py` uses for `RFONE_DATABASE_URL`).

## Install & run

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r "../RF-One Data Store/requirements.txt"
python app.py
```

Then open **http://127.0.0.1:5050**.

## Testing

- `03 Software/RF-One Data Store/test_selection_engine.py` — Selection Core/persistence validation suite (`rfone_data_store/selection_validation.py`), including duplicate detection and source-metadata persistence at the `import_pipeline`/persistence layer.
- `03 Software/Selection/test_batch_upload.py` — exercises the actual Flask routes (`/upload`, `/api/upload`) with Werkzeug's test client: multi-file batch upload, one unsupported file not blocking the rest, duplicate detection over HTTP, and that imported candidates are visible on revisit. Run with `python test_batch_upload.py`; it always runs against a throwaway temporary SQLite database and cleans up every file it writes into `uploads/`, never touching `data/selection.db`.

## Known limitations of this MVP

- Real AI parsing is implemented (`parsing/llm_parser.py`) but has not been exercised against a live API in this environment — no AI provider credential is configured anywhere in this repository today. The DEMO/MOCK fallback is what actually powers the working flow.
- Only PDF upload is supported (task's stated minimum); DOCX/text are not wired up.
- Two Role Configurations exist: Server and FOH Team Leader (`FOH_SUPERVISOR`); other Restaurant roles have none yet (`01 Domains/Business Domain/Restaurant/Selection/README.md`, "Not decided here").
- Single-client only — `app.py` bootstraps one `Restaurant` row ("Rome's Flavours") in its own local database; no client-selection UI exists.
- Uploaded résumés are real files (once real uploads happen) and are Git-ignored (`uploads/`, `.gitignore`), consistent with InvoiceIntake's handling of supplier documents.
- Duplicate detection is a best-effort content/filename hash, not candidate identity resolution — it catches "the same résumé file uploaded twice," not "this candidate applied before under a different résumé."
- The batch UI processes files sequentially, one HTTP request at a time (not in parallel), to stay safe with this deployment's SQLite database, which does not support concurrent writers.
