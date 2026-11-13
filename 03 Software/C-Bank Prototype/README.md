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

**Bank unification Phase 3A (2026-10-24): this is THE reconciliation engine of the Bank.** Its records live in the Bank database (`bank_engine_runs`, `bank_engine_results`, `financial_transaction_matches`, `bank_flow_artifacts`; `cbank/store.py`); `cbank.db` is a frozen archive; human decisions go through Bank's manual service. Tests run on a copy of the Bank database (`tests/_isolated.py`). The standalone 5090 server is not an operational application.

**Bank unification Phase 1 (2026-10-24):** this application is now normally served INSIDE the Bank on 5080, as
the Bank tab **Guided Reconciliation** (`/bank/reconcile/`) — see `03 Software/RF-One Web/bank_guided_reconciliation.py`
in the Bank worktree. The page uses its base path (`request.script_root`), so the same code also runs standalone.
The standalone 5090 server below is kept only as rollback; do not run it while the Bank serves the tab.

Double-click **`Avvia C-Bank.cmd`** → http://127.0.0.1:5090/ (uses the Bank venv, installs nothing).

- **Run MVP sample**: ~4 real movements per MVP case (spec §5), selected deterministically (`cbank/sample.py`).
- **Run month**: every movement of a month (same engine — decision 24).
- Exceptions dashboard grouped by type and WHO, one action per row: **Review** (the row click opens the same group
  window). The window shows the WHO, the concrete reason, the group's movements and:
  **Analyse the group and propose a rule** (`cbank/group_analysis.py`, `POST /api/runs/<id>/analyze`, read-only:
  every movement of the group and the WHO's history, through the WHY discovery of `why_patterns` and the WHO WHY rule
  simulation of `why_signals.simulate`; not gated by the general completeness check, group-specific gaps reported) and
  **Define rule**: the WHY rule editor of the window (`cbank/rule_scopes.py`, `templates/_rules_panel.js`; BANK_RULE_SCOPE_AND_WHO_CATEGORY_001):
  scope single WHO / WHO category / general, WHY with its derived WHAT, conditions, exceptions;
  `POST /api/runs/<id>/rules/simulate` compares it with every rule of the other scopes (equivalent — on current data or
  also on the conditions —, complementary, conflict, kept exception) and shows movements before → after, read-only;
  `POST /api/runs/<id>/rules/save` repeats the simulation, refuses a stale token, saves a DRAFT (inactive) or APPLY
  (active, chosen equivalent rules replaced with `who_why_rules.supersede`, restorable, open movements re-evaluated);
  the window reopens on the same group. The same panel holds the WHO category (`who_categories`: AI proposal with
  internet research on the WHO name, used only once confirmed) and contextual declarations (valid on their Sources only).
  The Bank recognition-profile editor stays reachable (embedded, `POST /api/runs/<id>/refresh` after a save); it only
  applies to movements whose WHO an extraction rule reads and that are still to reconcile.
  Every window has a **?** opening its own section of the in-page guide, over the window (state kept).
  **Investigate with AI** (up to 6 selected movements — decision 45) stays in Advanced details and keeps the gate.
- Click a movement → modal: decision trace, Bank comparison, structured fields + free AI conversation (decision 33).
  **Confirm human decision** stores it in the C-Bank store only; it is protected and re-evaluates only unresolved
  movements of the run (decisions 38, 46).
- **Export per LLC (Excel)**: one workbook per LLC + inter-entity workbook, all marked EXPERIMENTAL (decisions 13, 14, 26).

Tests (standard library, real data, read-only):

```
%LOCALAPPDATA%\RF-One\Bank\venv\Scripts\python.exe -I -m unittest discover -s "03 Software/C-Bank Prototype/tests" -v
```

## Three-stage WHO simulation (cbank/three_stages.py, 2026-11-01)

A simulation, not the engine: every movement in scope goes through **Rules → WHO Search Text → internet research**
(no matching first), counted once. Stage 3 researches the movements still without a unique catalog WHO through
the one ChatGPT adapter (web search on) and classifies each as **WHO_IDENTIFIED** (certain, with a public source;
WHY from the registered WHO + Source pair, otherwise proposed from the evidence and labelled so), **GENERIC_WHO**
(nature established, descriptive WHO such as "Parking — unknown merchant", never registered, with an existing
definitive WHY) or **UNRESOLVED**. WHAT only from the WHY; WHOM from the Source owner. Read-only session; writes
only the JSON file given (proposals, sources, reasoning, certainty); amounts are not sent. `--resume` reuses the
internet answers already saved. Test: `tests/test_three_stages.py`.

```
cd "03 Software/C-Bank Prototype"
%LOCALAPPDATA%\RF-One\Bank\venv\Scripts\python.exe -m cbank.three_stages --out <file.json> [--resume] [--no-web] [--limit N] [--ids 1,2]
```

**WHO ≠ WHY (BANK_WHO_WHY_MODE_001, 2026-11-01).** A WHO recognised in stages 1-2 gets its WHY as the engine
determines it (`Engine.determine_why`: WHO + Source pair for a UNIQUE WHO, WHO WHY rules for a MULTIPLE WHO or a
pair without WHY). If the WHY stays open, the movement also goes to stage 3 with its WHO fixed (`recognised_who`):
the research may propose a WHY from evidence, never change the WHO; rules in conflict are not researched. The
summary adds a second quadrature, `quadrature_final`: WHO identified with WHY + WHO identified with WHY open +
generic WHO classified + open without WHO; WHY bases and open reasons are sub-counts. Engine policy
`who-why-mode-v5`; `cbank/why_signals.py` serves the Bank page *WHY Rules* (signals and draft-rule simulation,
read-only). Test: `tests/test_who_why_mode.py`.

## Split of one movement (BANK_SPLIT_ALLOCATION_001, 2026-11-01)

A movement may carry several classification lines (QuickBooks Online Split), stored as Bank allocations whose sum
equals the movement exactly. `Result.split` carries the lines:

- `origin=DOCUMENT` is proposed from the Amazon order matched by Charge Identifier, with amount, date and currency
  checked;
- `origin=BANK` is the split already confirmed in Bank, which is protected.

A complete split resolves the WHY of the movement (method `SPLIT`). Several WHYs without detail amounts give
`WHY_SPLIT_INCOMPLETE` "Ripartizione incompleta" ("Importi di dettaglio mancanti"). The engine never applies an
equal split or the prevailing category.

Read-only Amazon simulation:

```
cd "03 Software/C-Bank Prototype"
%LOCALAPPDATA%\RF-One\Bank\venv\Scripts\python.exe -m cbank.amazon_split --csv <orders.csv> --out <file.json> [--ai] [--resume]
```

`--ai` classifies the linked products with the Bank Amazon prompt. It sends no amounts, bank descriptions or codes.
Test: `tests/test_split_allocation.py`.

## Engine (cbank/engine.py) — stage order

| Stage | Order of evidence | Decisions |
|---|---|---|
| Source | Bank Source configuration (card → settlement account owner) | 19 |
| Matching | description references the other account's last four → configured card settlement → both hinted; mutual unique best only | 22, 37 |
| WHO | matched counterpart (contextual) → approved text rules (Bank extractors + legacy structured rules) → WHO memory (same Bank precedent key) → AI (WHO must be readable in the description) → exception | 36, 43, 48 |
| Profile | BANK_FLOW_2 profiles + legacy rules for that WHO; different results = `PROFILE_CONFLICT`, no deciding branch = `PROFILE_UNDECIDED` | 4, 42, 44 |
| Fallbacks | transfer WHY from the match → ≥2 concordant precedents (human, or the current Bank decision written by an approved rule / Recognition Profile with *apply to future*, provenance kept; Codex WHY sessions never count) → AI, **field by field** (each of WHO, WHY, Category, Beneficiary accepted only with its own `sufficient=true` and confidence ≥ 0.85; partial AI fields are kept in `ai_partial`) | 5, 11, 50 |
| Direction | an income category on money out (e.g. "INTEREST PAYMENT ON LOAN" matched by an interest-income rule) ⇒ `DIRECTION_CONFLICT`, never reconciled silently | E1 |
| Beneficiary | human → profile branch → personal WHY ⇒ person → ≥2 concordant human precedents → AI → account owner; business **cost** category on a personal instrument ⇒ question (income such as interest earned keeps the owner); AI WHY accepted but beneficiary explicitly uncertain ⇒ `AI_PARTIAL` | 01–03, 16 |
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
| `cbank/three_stages.py` | three-stage WHO simulation (read-only, JSON output) |
| `cbank/why_signals.py` | WHY to determine by WHO / Source / reason; WHO WHY rule simulation (read-only) |
| `cbank/amazon_split.py` | Amazon split simulation from an order CSV (read-only, JSON output, QBO preview) |
| `cbank/web.py`, `cbank/templates/index.html` | local UI |

## Not in this increment (spec §6)

Retroactive corrections with approval, rule proposals/approval lifecycle, cross-domain evidence (Invoice Intake,
MyRF Projects), QuickBooks import and matching, monthly close, bank feeds, permanent catalog management,
fee/gross reconstruction, multi-model AI tiers (needs an OpenAI API key).


## Automatic reconciliation policy — 2026-10-25

Automatic reconciliation uses matched transfers/card payments first, then the shared approved WHO rules
and name/alias recogniser, then approved executable WHY rules and Recognition Profiles. WHAT derives
from WHY. WHOM comes from the matched rule/profile, otherwise from the account/card owner (also for
unmatched card payments). Conflicts stay open. Existing human decisions on the same movement remain
protected. History, saved AI investigations and implicit personal-WHY destination shortcuts do not decide automatic proposals. AI conversations remain manual advisory tools.
`CBANK_WHO_EXTRA` cannot reactivate the retired recognition path. The policy revision is part of the
run signature so a restart cannot keep results produced by the preceding policy as current.

The running Bank process must be restarted through Bank Local Environment to load these source changes.
The next watcher run writes refreshed engine proposals and matches, not human classifications.


## Rule-extracted WHO registration and manual classification — 2026-10-25

A full engine run registers previously unknown names extracted by approved WHO rules, through the same
catalog creation service as manual WHO creation. Exact names/aliases reuse the active WHO. Similar saved
names/aliases, inactive held identities, invalid names, and similar new names from the same run stay open;
no automatic merge or alias creation takes place. Similar means added/removed/reordered whole words (at
least four characters in the shorter key), or a normalized-name similarity of at least 0.90 (both keys at
least six characters). This is a conservative review guard, never proof of identity.

Configuration has a POST/CSRF-protected Recalculate WHY / WHAT action using the one full-history engine.
The sole manually approved WHO WHY, or an explicitly configured default among approved WHYs, supplies WHY;
WHAT derives from WHY. Several manual WHYs without a default require a conditional rule/profile or remain
open. A conflict with a profile/rule stays open. Historical associations are excluded, and AI/memory remain
disabled. Saving the selected WHYs in Configuration explicitly marks those associations HUMAN.

Catalog/default/WHY/WHAT edits invalidate the run signature. Existing confirmed movement decisions remain
protected. New WHO catalog records are the only additional automatic writes; movement classifications are
still engine proposals. The database reset remains paused until the Product Owner resumes it.


## WHO + Source replaces global WHO purpose — 2026-10-26

The active policy is `who-source-owner-v3`. Classification uses only the exact WHO + Source pair;
WHO-only defaults/profiles never supply another Source's WHY. WHOM is always the Source owner; WHAT
comes from WHY. Pair rows are unique and generated unclassified for newly recognized combinations.
WHO identities remain unique catalog records. Activity labels, their worker, tables and UI were removed.
See BANK_WHO_SOURCE_CLASSIFICATION_001 in the Bank domain for migration and compatibility details.


## UI language

Guided Reconciliation uses `RFONE_UI_LANGUAGE=it` for the Product Owner’s local Italian interface; the official Bank local launcher sets it. Without that local setting the shared/release interface defaults to English. `index.html` is the English template and `index.it.html` is its Italian presentation counterpart. Preserve both behaviors before Git/AWS publication (UI_DEVELOPMENT_LANGUAGE_001).
