# Selection — Resume Screening (MVP)

**Task:** TASK_SELECTION_001, extended by TASK_SELECTION_002 (multi-résumé batch import)
**Canonical documentation:** `01 Domains/Shared Domains/Selection/ResumeScreening/` (Selection Core) and `01 Domains/Business Domain/Restaurant/Selection/` (Restaurant Industry Extension).

A small local web app to screen résumés for Rome's Flavours' Server role: upload one or many PDFs at once, each résumé is parsed independently into a structured Candidate CV Profile, and the candidate detail page shows Facts, Derived Information, Flags/Questions and Indicators as four clearly separate areas — never one combined score.

## How it works

- **Batch upload.** The candidate list page's import form accepts multiple PDF files at once (native multi-file picker, plus drag & drop). Each file is uploaded and processed independently via `/api/upload` (one JSON call per file) — the page shows a live WAITING → PROCESSING → COMPLETED/FAILED/DUPLICATE state per file and an aggregate "x / y processed" count while the batch runs. One file failing (wrong format, unreadable PDF, parsing error) never stops the rest. If JavaScript is unavailable, the same multi-file input still works via a classic form POST to `/upload`, which processes every selected file server-side and shows a results summary inline.
- **Duplicate detection.** Each résumé's extracted text (or, failing that, its filename) is hashed and checked against previously imported résumés for the same client before a new Candidate is created — an exact re-upload is reported as `DUPLICATE` and linked to the existing candidate instead of creating a second one. See `rfone_data_store/selection/parsing/dedup.py`.
- **Source metadata.** Every candidate records where its résumé came from: `source` (`LOCAL_UPLOAD` today), `source_provider` (`manual` today), `source_file` (original filename) and `created_at` (import timestamp) — shown on the candidate list and on each candidate's "Source & Extraction Information" section. The shape already supports a future non-file `ResumeSource` (e.g. an API integration) without changing `CandidateCVProfile` or the parsing pipeline.
- **Parsing.** Every upload's raw text is extracted for real (pdfplumber, same approach as `03 Software/InvoiceIntake/`). Structured extraction then tries a real AI provider first (Anthropic, if `ANTHROPIC_API_KEY` is configured — see `rfone_data_store/selection/parsing/ai_client.py`); with no credentials configured in this environment, it automatically falls back to a **DEMO/MOCK** parser that deterministically selects one of three realistic fixture candidates. The candidate list and detail page always show a clear `DEMO / MOCK` vs `REAL AI` badge — never disguised. `source`/`source_provider` always reflect the true acquisition channel (e.g. `LOCAL_UPLOAD`/`manual`) regardless of which parser ultimately produced the structured content.
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
- Only Rome's Flavours' Server Role Configuration exists; other Restaurant roles have no Role Configuration yet (`01 Domains/Business Domain/Restaurant/Selection/README.md`, "Not decided here").
- Single-client only — `app.py` bootstraps one `Restaurant` row ("Rome's Flavours") in its own local database; no client-selection UI exists.
- Uploaded résumés are real files (once real uploads happen) and are Git-ignored (`uploads/`, `.gitignore`), consistent with InvoiceIntake's handling of supplier documents.
- Duplicate detection is a best-effort content/filename hash, not candidate identity resolution — it catches "the same résumé file uploaded twice," not "this candidate applied before under a different résumé."
- The batch UI processes files sequentially, one HTTP request at a time (not in parallel), to stay safe with this deployment's SQLite database, which does not support concurrent writers.
