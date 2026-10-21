# C-Bank Prototype

**Status:** first end-to-end prototype (MVP, spec §5). **Experimental, local only, dry run.**
**Authority:** [`C-Bank_Functional_Specification_v1.md`](C-Bank_Functional_Specification_v1.md) — 58 approved decisions.

## What it is

An isolated module (decision 57) that runs ONE new reconciliation engine (decision 53) on the real movements
of the operational Bank, **reading Bank only** and writing its results to a separate experimental store:

```
Bank Transaction → Source owner (payer) → transfer/card matching → WHO → Recognition Profile
  → Beneficiary → WHY → Category RF-One → QB account → Operation type → Reconciled / Exception → Export per LLC
```

## Isolation guarantees

| What | How |
|---|---|
| Bank database | Opened with SQLite `mode=ro` + `PRAGMA query_only=ON` (`cbank/legacy.py`). Any write fails. |
| Bank code | Imported from the live Bank worktree (`rf-one-bank-simple-who-rules`), never modified. |
| Experimental results | `%LOCALAPPDATA%\RF-One\C-Bank\cbank.db` (runs, results, human decisions, AI investigations, conversations) and `exports\`. |
| AWS | Not touched. No deploy. |
| AI | OpenAI only, through Bank's ChatGPT/Codex adapter (`bank_chatgpt.generate_json`). No other provider, no fallback. |

## Run

Double-click **`Avvia C-Bank.cmd`** → http://127.0.0.1:5090/ (uses the Bank venv, installs nothing).

- **Run MVP sample**: ~4 real movements per MVP case (spec §5), selected deterministically (`cbank/sample.py`).
- **Run month**: every movement of a month (same engine — decision 24).
- Exceptions dashboard grouped by type and WHO → **Investigate with AI** (one shared investigation per group,
  individual judgement per movement — decision 45).
- Click a movement → modal: decision trace, Bank comparison, structured fields + free AI conversation (decision 33).
  **Confirm human decision** stores it in the C-Bank store only; it is protected and re-evaluates only unresolved
  movements of the run (decisions 38, 46).
- **Export per LLC (Excel)**: one workbook per LLC + inter-entity workbook, all marked EXPERIMENTAL (decisions 13, 14, 26).

Tests (standard library, real data, read-only):

```
%LOCALAPPDATA%\RF-One\Bank\venv\Scripts\python.exe -I -m unittest discover -s "03 Software/C-Bank Prototype/tests" -v
```

## Engine (cbank/engine.py) — stage order

| Stage | Order of evidence | Decisions |
|---|---|---|
| Source | Bank Source configuration (card → settlement account owner) | 19 |
| Matching | description references the other account's last four → configured card settlement → both hinted; mutual unique best only | 22, 37 |
| WHO | matched counterpart (contextual) → approved text rules (Bank extractors + legacy structured rules) → WHO memory (same Bank precedent key) → AI (WHO must be readable in the description) → exception | 36, 43, 48 |
| Profile | BANK_FLOW_2 profiles + legacy rules for that WHO; different results = `PROFILE_CONFLICT`, no deciding branch = `PROFILE_UNDECIDED` | 4, 42, 44 |
| Fallbacks | transfer WHY from the match → ≥2 concordant **human** precedents → AI with `sufficient=true` and confidence ≥ 0.85 | 5, 11, 50 |
| Beneficiary | human → profile branch → personal WHY ⇒ person → ≥2 concordant human precedents → AI → account owner; business category on a personal instrument ⇒ question | 01–03, 16 |
| Mapping | Category RF-One = Bank WHAT (`accounting_classification_id`); QB account "not mapped" until the QB COA is imported | 09, 20 |
| Operation | match, else category (P&L income/expense, 15xx capital, 26xx financing, 16xx/27xx inter-entity, 3xxx patrimonial) | spec §2 |
| Ledger | payer ≠ beneficiary ⇒ proposed receivable/payable; inter-entity transfer ⇒ advance/repayment to qualify | 01, 07, 14 |
| Status | Reconciled only when WHO, WHY, Category, Beneficiary, Operation are set and no exception is open | 25 |

The Bank **Configuration default WHY of a WHO is never applied automatically**: it is passed to the AI as a hint only.
Operational Bank HUMAN decisions and C-Bank human decisions are protected; the engine shows its own different
result as a *proposal* only.

## Files

| File | Role |
|---|---|
| `cbank/config.py` | paths, port, thresholds |
| `cbank/legacy.py` | read-only gateway to Bank DB and code |
| `cbank/matching.py` | transfer / card-payment legs |
| `cbank/engine.py` | the single orchestrator |
| `cbank/ai.py` | grouped investigation + assisted conversation (OpenAI) |
| `cbank/sample.py` | MVP case sample |
| `cbank/service.py` | runs, re-evaluation of unresolved movements |
| `cbank/store.py` | experimental store |
| `cbank/export.py` | Excel per LLC + inter-entity |
| `cbank/web.py`, `cbank/templates/index.html` | local UI |

## Not in this increment (spec §6)

Retroactive corrections with approval, rule proposals/approval lifecycle, cross-domain evidence (Invoice Intake,
MyRF Projects), QuickBooks import and matching, monthly close, bank feeds, permanent catalog management,
fee/gross reconstruction, multi-model AI tiers (needs an OpenAI API key).
