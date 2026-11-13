# Clover Data Explorer

Strumento **read-only** di connessione, esportazione e discovery dati verso l'account Clover production di Rome's Flavours. Primo passo di TASK_CLOVER_001, verso:

```text
Clover API → export dati grezzi → data discovery → (task futuri) calcolo tip → funzione web
```

Questo modulo **non** calcola le tip, **non** costruisce una UI/API web, **non** scrive mai su Clover (nessuna chiamata POST/PUT/PATCH/DELETE — il client implementa solo `GET`).

TASK_CLOVER_002 ha aggiunto un layer di ricostruzione/riconciliazione: quattro CSV comparabili agli export ufficiali del dashboard Clover (Payments/Orders/LineItems/Clock), generati dai dati API e confrontati campo per campo con export di riferimento forniti dal Product Owner. Vedi `CLOVER_EXPORT_MAPPING.md` (mapping colonna→sorgente API, con livello di confidenza) e `CLOVER_EXPORT_RECONCILIATION.md` (risultati del confronto, incluse le incongruenze Tip/Service Charge riscontrate — nessuna regola di calcolo tip è ancora stata decisa).

TASK_CLOVER_003 ha chiuso la fase di discovery Clover con un audit empirico completo delle capacità del source system (campi, coverage, relazioni, timestamp, fatti atomici vs derivati vs artefatti vendor). Vedi `CLOVER_DATA_CAPABILITY_MATRIX.md` (deliverable principale, con il Recommended Canonical Clover Ingestion Set finale), `CLOVER_SOURCE_RELATIONSHIP_MAP.md` (grafo delle relazioni Clover confermate/inferite/irrisolte) e `CLOVER_ATOMIC_DERIVED_FACTS.md` (classificazione in 6 categorie). `CLOVER_RESTAURANT_DATA_MAPPING.md` è stato corretto ed esteso con le nuove evidenze (coverage guest count corretta, tavolo/zona da `Order.title`, refund, sconti ad hoc). Nessun database o KPI è stato implementato da questo task — vedi `07 Tasks/Reports/TASK_CLOVER_003_REPORT.md`.

## Requisiti

- Python 3.10 o superiore
- `pip install -r requirements.txt` (dipendenze: `requests`, `tzdata` — quest'ultima necessaria su Windows perché `zoneinfo` non include il database IANA)
- Un file `.env` nella root del repository (`RF One/.env`, già ignorato da Git) con:

```text
CLOVER_MERCHANT_ID=...
CLOVER_API_TOKEN=...
```

Il token non viene mai stampato, loggato, scritto nel manifest o nel report.

## Uso

Verifica di connessione (Phase 1 — una sola chiamata GET a `/v3/merchants/{mId}`):

```text
python check_connection.py
```

Export completo + report di discovery (Phase 2):

```text
python run_export.py
```

L'export scrive in `data/raw/<timestamp>/` (directory locale, ignorata da Git — vedi `.gitignore` alla root del repository) i payload JSON grezzi di ogni collection raggiungibile, più `manifest.json`. Rigenera poi `CLOVER_DATA_DISCOVERY.md` in questa cartella.

## Struttura del modulo

| File | Responsabilità |
|---|---|
| `clover_explorer/config.py` | Lettura `CLOVER_MERCHANT_ID`/`CLOVER_API_TOKEN` da env o `.env`; mai hard-coded. |
| `clover_explorer/client.py` | Client HTTP read-only (solo `GET`), retry/backoff conservativo su 429/5xx/errori di rete. |
| `clover_explorer/pagination.py` | Paginazione completa `limit`/`offset` sulle collection Clover. |
| `clover_explorer/raw_store.py` | Persistenza locale dei payload grezzi + manifest. |
| `clover_explorer/orchestrator.py` | Elenco delle collection investigate ed export orchestration. |
| `clover_explorer/discovery.py` | Analisi schema (campi, tipi, relazioni, timestamp) e generazione del report Markdown, senza PII. |
| `check_connection.py` | Entry point Phase 1. |
| `run_export.py` | Entry point Phase 2 (export + discovery report). |
| `clover_explorer/time_money.py` | Conversione centralizzata data/ora (epoch ms → Eastern, DST-aware) e valuta (minor units → decimale). |
| `clover_explorer/export_models.py` | Caricamento delle collection raw + lookup per ID (mai per nome). |
| `clover_explorer/api_cache.py` | Cache locale su disco per le chiamate GET supplementari (cardTransaction, modifications, devices, taxRates) non incluse nell'export TASK_CLOVER_001. |
| `clover_explorer/export_payments.py`, `export_orders.py`, `export_line_items.py`, `export_clock.py` | Ricostruzione dei quattro export dashboard-style da dati API. |
| `clover_explorer/export_compare.py` | Motore di confronto (per ID/composite key) fra export generati e export di riferimento. |
| `build_dashboard_exports.py` | Entry point TASK_CLOVER_002: genera i 4 CSV in `data/generated_exports/<start>_to_<end>/`. |
| `compare_dashboard_exports.py` | Confronta i CSV generati con quelli di riferimento in `data/reference_exports/`. |
| `fetch_profile_bootstrap_snapshot.py` | TASK_RESTAURANT_003: refresh read-only (solo `GET`) di `employees?expand=role` e `roles?expand=employees`, salvato in `data/generated_exports/_api_cache/restaurant_profile_bootstrap/<timestamp>/` (mai in `data/raw/`), usato dal bootstrap del Restaurant Profile in RF-One Data Store per il controllo di congruenza con i dati già ingeriti. |

## Cosa investiga

Merchant, Employees, Shifts, Roles, Customers, Inventory (items, categories, modifier groups/modifiers, item stocks, discounts, tax rates, tags, order types), Orders (con `expand` su lineItems/payments/discounts/customer) e Payments come collection di primo livello — con attenzione a `tipAmount`, `taxAmount`, `employee`, `tender`, `refunds`, stato void/result, in vista del calcolo tip di un task futuro (non eseguito qui).

Le collection nidificate via `expand` (es. `lineItems` sugli ordini) possono essere troncate indipendentemente dalla pagina padre: per un campione limitato di ordini viene eseguito anche un confronto diretto con l'endpoint dedicato `line_items` (vedi `orders_line_item_completeness_sample.json` nell'export e la sezione dedicata in `CLOVER_DATA_DISCOVERY.md`).

## Limiti noti di questo prototipo

- Nessun database: solo file JSON locali (fase di discovery).
- Nessun filtro per intervallo di date: viene tentata la storia completa accessibile; eventuali limiti imposti da Clover vengono registrati per collection nel manifest.
- Il confronto di completezza dei `lineItems` è limitato a un campione di ordini, non all'intera storia (per evitare una scansione N+1 completa in questa prima fase).
- Un solo export alla volta (nessuna gestione di export concorrenti).
