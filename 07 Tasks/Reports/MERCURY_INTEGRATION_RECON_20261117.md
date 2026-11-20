# Mercury — Ricognizione tecnica dell'integrazione (2026-11-17)

Ricognizione di sola lettura. Nessun codice sviluppato, nessun deploy, nessuna scrittura su database di produzione, nessuna chiamata alle API Mercury (né sandbox né produzione). Nessun segreto riportato: le credenziali sono indicate solo per nome e presenza.

Legenda stato: **VERIFICATO** = implementato e provato (test o evidenza); **SVILUPPATO** = codice presente ma mai provato in esercizio reale; **MANCANTE** = da realizzare.

---

## 1. Stato attuale dell'integrazione Mercury

In sintesi: **Mercury è oggi integrato solo come esecutore di pagamenti delle Tips, solo in sandbox.** Non esiste alcun collegamento tra Mercury e il dominio Bank (importazione movimenti, saldi, riconciliazione).

| Area | Stato | Note |
|---|---|---|
| Connettore tecnico Mercury (client HTTP) | VERIFICATO in sandbox | `technical/connectors/mercury/client.py`; endpoint sandbox fisso, nessun endpoint di produzione nel codice |
| Lettura conti e saldi | VERIFICATO in sandbox (solo per il controllo fondi Tips) | `GET /accounts` → `availableBalance`; non esposto al dominio Bank |
| Importazione movimenti bancari | MANCANTE | il client legge solo una singola transazione per id (`GET /transaction/{id}`); nessun elenco movimenti per conto |
| Sincronizzazione automatica | MANCANTE per Bank; SVILUPPATO per Tips | scheduler Tips (`tips/scheduler.py`) con polling dello stato dei pagamenti; nessun job Mercury su AWS |
| Pagamenti e trasferimenti | VERIFICATO in sandbox, mai in produzione | `POST /account/{id}/transactions` (ACH verso destinatari esistenti), idempotenza RF-One, isolamento per beneficiario, verifica esito |
| Webhook e notifiche | MANCANTE | nessun ricevitore webhook; esito osservato solo per polling (la sandbox non offriva webhook al momento del pilota) |
| Riconciliazione con il database RF-One | MANCANTE | Bank (`financial_transactions`) è alimentato da CSV Chase/First Citizens e da PayPal; nessun adapter Mercury |
| Sicurezza e autorizzazioni | VERIFICATO (lato codice) | rimozione campi sensibili dalle risposte, fail-closed sul connettore, autorità "Approve & Pay" a livello Restaurant |
| Credenziali di produzione | ASSENTI | nessuna variabile, file o secret AWS di produzione trovato |

---

## 2. Lavoro già completato e prove disponibili

### 2.1 Cronologia (Git)

| Data | Commit | Contenuto |
|---|---|---|
| 2026-09-12 | `87d73f7` | *RF-One Tips Core 2.0 process-first pilot* — nascita del connettore Mercury sandbox, Payment Instruction, controllo fondi, verifica esito (branch originale `review/tips-core2-pilot`, oggi non più presente né in locale né su origin) |
| 2026-09-17 | `229cd90` | *integrate canonical Tips workflow and configurable payment connectors* (STEP 12B) — registro neutrale dei connettori `tips/payment_connector.py`, Payment Cycle, scheduler, pagina Payment Control |
| post 12B | `c70b3ef` | chiusura baseline: `TipPaymentInstruction.provider` reso nullable (nessun "Mercury implicito") |
| 2026-11-04 → 11-13 | `18ff9e3`, `76747f0`, `5bc442a`, `9eb8752` | solo copie/snapshot del codice in altri percorsi (es. `03 Software/AWSSelection/`), nessuna modifica funzionale |

Il connettore è presente, identico, su `main`, `origin/main`, `release/bank-reinstall` e nel working copy corrente (`handoff/2026-10-17`). Nessuna differenza locale rispetto a `origin/main` nei file Mercury.

### 2.2 API Mercury effettivamente usate

| Endpoint | Uso | Stato |
|---|---|---|
| `GET /accounts` | saldo disponibile per il controllo fondi; scelta del conto sorgente | VERIFICATO sandbox |
| `GET /recipients` | collegare un dipendente a un destinatario Mercury **già esistente** (per nome) | VERIFICATO sandbox |
| `POST /account/{id}/transactions` | invio pagamento ACH con `idempotencyKey` derivata da RF-One | VERIFICATO sandbox |
| `GET /transaction/{id}` | lettura esito (pending/sent/failed/reversed/…) | VERIFICATO sandbox |

**Non usate:** elenco transazioni di un conto, estratti conto, creazione destinatari, webhook, flusso di approvazione `RequestSendMoney`, endpoint di produzione `api.mercury.com`.

### 2.3 Test sandbox reali

- Script `03 Software/Tips/sandbox_pilot_e2e.py` eseguito contro la **vera sandbox Mercury** durante il pilota: esito **PASS** secondo `07 Tasks/Reports/TASK_TIPS_CORE2_PILOT_REPORT.md` §7 — controllo fondi reale, un pagamento riuscito (`SENT`), un fallimento isolato (destinatario "bannato" della sandbox), retry del solo pagamento fallito fino a `OUTCOME_VERIFIED`.
- Limite della prova: la trascrizione completa dell'esecuzione è rimasta solo nella chat di allora; nel repository c'è l'affermazione del report, non il log.
- Scoperta reale documentata: Mercury restituisce **HTTP 409** se la stessa `idempotencyKey` viene riusata con un destinatario diverso → la chiave è stata ridefinita come `(run, dipendente, destinatario attivo)`.

### 2.4 Test automatici (senza rete, client Mercury finto) — rieseguiti oggi

| Suite | Sorgente | Esito oggi |
|---|---|---|
| `test_tips_payment_connector.py` | `origin/main` @ `9c154f9`, checkout temporaneo | **27/27 PASS** |
| `test_tips_payment_execution.py` | idem | **55/55 PASS** |
| Le stesse suite sul working copy corrente | `handoff/2026-10-17` | **non eseguibili**: Alembic "multiple heads" (vedi §5) |

### 2.5 Dati

Copia locale canonica dei dati AWS (`AWS-Copy/20261025T130037Z`, letta in modalità read-only e richiusa):

| Tabella | Righe |
|---|---|
| `tip_payment_instructions` | 0 |
| `employee_external_payment_accounts` | 0 |
| `tips_payment_schedule_configs` | 0 |
| `tip_payment_cycles` | 0 |
| `payroll_runs` | 0 |
| `financial_transactions` (Bank) | 3.234 (nessuna sorgente Mercury) |

Interpretazione: lo schema per i pagamenti Mercury è in produzione, ma **nessun pagamento, configurazione o collegamento dipendente-destinatario è mai stato creato** fuori dalla sandbox.

---

## 3. Architettura esistente

```
Tips (Restaurant)                                   Bank Reconciliation (Shared/Administration)
 calcolo FINAL ─► TipEntitlement ─► TipPaymentCycle   CSV Chase / First Citizens / PayPal
        │                                │             │
        ▼                                ▼             ▼
 TipPaymentInstruction (neutrale)   payment_readiness  RawBankTransaction ─► FinancialTransaction
        │                                              (modello indipendente dalla banca;
        ▼                                               purpose_evidence già predisposto per
 tips/payment_connector.py  (registro, fail-closed)     un futuro "source_memo" Mercury)
        │  connector_code = 'MERCURY'
        ▼                                                      ✗ nessun collegamento
 technical/connectors/mercury/client.py  ──HTTPS──► api-sandbox.mercury.com
```

Principi già approvati e implementati:
- **Connettore tecnico separato dai Domini** (`rfone_data_store/technical/connectors/`): conosce solo Mercury, nessuna logica Tips.
- **Neutralità del connettore** (decisione PO): `TipPaymentInstruction` dice *cosa* pagare; la configurazione dice *chi* esegue. Nessun fallback silenzioso a Mercury.
- **Protezione primaria dal doppio pagamento = RF-One** (vincolo unico per `(calcolo, dipendente)` + chiave di idempotenza); la protezione anti-duplicati di Mercury è solo rete di sicurezza.
- **Esito verificato** solo con `status = sent` **e** `postedAt` valorizzato; un successivo `reversed` riapre il caso (Attention Item).
- **Dati sensibili** (numero conto, routing) rimossi da ogni risposta prima di uscire dal connettore; il dipendente è collegato solo tramite l'id opaco del destinatario Mercury.
- **Payroll**: valore `MERCURY_ACH` previsto in `PayrollRun.payment_execution_provider` come segnaposto strutturale, nessun codice di esecuzione; ADP resta l'esecutore attuale.
- **Bank**: `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md` §10 — *"Mercury è una sorgente futura, da integrare tramite connettore"*; aggiungere una sorgente = un nuovo parser che produce lo stesso `FinancialTransaction`, senza cambiare schema né export Kermali.
- **Intercompany** (`SETTLEMENT_POLICY_001.md`): il contante può stare fisicamente in un unico conto Mercury con attribuzione economica alla Legal Entity d'origine — concetto documentato, nessun runtime.

---

## 4. Funzionalità mancanti

| # | Funzionalità | Perché serve |
|---|---|---|
| M1 | Configurazione **endpoint/token di produzione** nel connettore (oggi solo sandbox per costruzione) | prerequisito di qualsiasi uso reale |
| M2 | Lettura **elenco movimenti** per conto (paginata, per intervallo di date) e saldi correnti | base per Bank |
| M3 | **Source Adapter Mercury per Bank** → `RawBankTransaction` / `FinancialTransaction`, con deduplica e conservazione del dato grezzo | portare Mercury dentro la riconciliazione WHO/WHY/WHAT |
| M4 | Registrazione del conto Mercury come **strumento/sorgente** in Bank (profilo sorgente, periodo mensile, copertura) | coerenza con il flusso mensile Bank |
| M5 | **Sincronizzazione automatica** (job pianificato, checkpoint, stato) | evitare import manuali |
| M6 | **Webhook** (ricevitore pubblico, verifica firma) oppure decisione esplicita di restare a polling | notifiche tempestive di esiti/movimenti |
| M7 | **Correlazione pagamento istruito ↔ movimento bancario** (Tips → Bank) | decisione PO già registrata come confine futuro in `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md` ("Future correlation between an operational payment and `FinancialTransaction`"), non progettata |
| M8 | Creazione/gestione **destinatari** dei dipendenti (oggi solo collegamento a destinatari esistenti) | onboarding reale dei beneficiari |
| M9 | Uso del flusso di **approvazione Mercury** (`RequestSendMoney`) se si vuole doppio controllo lato banca | non provato nel pilota |
| M10 | Secret su AWS (Secrets Manager) e rete in uscita con IP fisso, se richiesto da Mercury per i token di scrittura | prerequisito del deploy |

---

## 5. Problemi o rischi individuati

| # | Problema (fatto osservato) | Perché conta | Correzione minima proposta |
|---|---|---|---|
| R1 | Il token **sandbox** è nel file `RF One/.env`, dentro OneDrive (ignorato da Git). In passato esisteva anche `Secrets/secretsmercury_sandbox_token.txt` (oggi la cartella non c'è). | un file sincronizzato su cloud è un'esposizione non necessaria; un token di produzione non deve mai seguire la stessa strada | token di produzione solo in AWS Secrets Manager; in locale nessun token di produzione |
| R2 | Il working copy corrente (`handoff/2026-10-17`) ha **due head Alembic**; anche la copia locale dei dati riporta due versioni (`k9f120261112`, `t9d120261113`). | i test Tips/Mercury non partono qui; una migrazione futura potrebbe fallire | riallineare la catena migrazioni prima di qualsiasi sviluppo Mercury (attività separata, da autorizzare) |
| R3 | `rfone-tips` su AWS contiene il codice del connettore ma **nessun token** Mercury. | oggi un tentativo di pagamento fallisce in modo sicuro ("connettore non disponibile"); nessun rischio di pagamento, ma la pagina Payment Control non è utilizzabile | nessuna azione finché non si decide la produzione |
| R4 | Il fallback del conto sorgente sceglie **il primo conto checking attivo con saldo positivo** se `mercury_source_account_id` non è configurato. | in produzione con più conti potrebbe addebitare il conto sbagliato | in produzione rendere obbligatoria la configurazione esplicita (nessun fallback) |
| R5 | Il connettore usa `float(amount)` nel corpo della richiesta. | rischio teorico di arrotondamento su importi monetari | verificare il formato decimale accettato da Mercury e inviare l'importo come stringa/decimale |
| R6 | L'evidenza del test sandbox reale è solo dichiarata nel report (log non archiviato). | prova non ripetibile da terzi | rieseguire `sandbox_pilot_e2e.py` e archiviare l'output (senza segreti) prima del passaggio in produzione |
| R7 | Il branch originale `review/tips-core2-pilot` non esiste più. | solo tracciabilità; il codice è integrato in `main` | nessuna: fare riferimento a `87d73f7` / `229cd90` |
| R8 | Finanziamento Chase → Mercury fuori ambito: RF-One legge solo il saldo disponibile. | un ciclo di pagamento può restare bloccato per fondi insufficienti (comportamento voluto: blocca tutto il lotto) | processo operativo di finanziamento, non software |
| R9 | Le capacità API di produzione (webhook, tipi di token, eventuale whitelist IP per token di scrittura) sono state verificate solo sulla sandbox nel settembre 2026. | i presupposti potrebbero essere cambiati | rileggere la documentazione ufficiale Mercury prima di progettare M1/M6/M10 |

---

## 6. Proposta per completare l'integrazione con RF-One Bank

Principio: **riusare il connettore esistente, non duplicarlo.** Mercury diventa una sorgente di Bank esattamente come Chase e PayPal, e lo stesso connettore continua a servire i pagamenti Tips.

1. **Estendere `technical/connectors/mercury/`** (stesso pacchetto) con: configurazione esplicita sandbox/produzione (nessun default di produzione), lettura elenco movimenti per conto e lettura saldi. Nessuna logica Bank nel connettore.
2. **Nuovo Source Adapter Bank "Mercury API"** nel modulo `bank_reconciliation`, che trasforma le transazioni Mercury in `RawBankTransaction` + `FinancialTransaction`, con:
   - identità di deduplica = id transazione Mercury;
   - memo/nota Mercury → `source_memo` (già previsto da `purpose_evidence.py`);
   - nessuna modifica allo schema canonico né all'export Kermali (§10 del documento di normalizzazione).
3. **Profilo sorgente/strumento** per il conto Mercury nelle tabelle Bank esistenti, così il controllo di copertura mensile lo tratta come gli altri conti.
4. **Fase 1 solo lettura**: token di produzione **read-only**, nessuna capacità dispositiva. I pagamenti Tips restano in sandbox.
5. **Fase 2 (separata, da autorizzare)**: correlazione pagamenti Tips ↔ movimenti Mercury in Bank, poi eventuale abilitazione dei pagamenti reali con token di scrittura dedicato.

Documentazione da aggiornare insieme al codice: `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md` (§10), `Tips Payment Execution.md`, How Works della pagina Bank coinvolta, `PROJECT_STATE.md`.

---

## 7. Sequenza operativa consigliata per arrivare in produzione

| Passo | Attività | Autorizzazione necessaria |
|---|---|---|
| 1 | Riallineare le head Alembic del working copy (R2) | sì (attività tecnica separata) |
| 2 | Rieseguire e archiviare il test sandbox reale `sandbox_pilot_e2e.py` (R6) | no (sandbox, già autorizzato in passato) — confermare |
| 3 | Rilettura documentazione Mercury di produzione: tipi di token, webhook, whitelist IP, limiti (R9) | no |
| 4 | Specifica funzionale "Mercury come sorgente Bank" (Documentation First) | approvazione PO |
| 5 | Sviluppo M1–M4 (connettore esteso + adapter Bank), test automatici con client finto | approvazione della specifica |
| 6 | Prova in locale con token **read-only di produzione** custodito fuori da OneDrive, importazione di un mese e confronto con l'estratto conto Mercury | PO crea il token read-only nel pannello Mercury |
| 7 | Secret AWS `rfone-tips/mercury-…` (o servizio Bank) + verifica egress (NAT `rfone-nat` se serve IP fisso) | sì (modifica AWS) |
| 8 | Release Bank con How Works aggiornato, `check_how_works.py`, checklist di rilascio | sì (deploy) |
| 9 | Sincronizzazione automatica (M5) e decisione webhook vs polling (M6) | approvazione PO |
| 10 | Solo dopo: correlazione Tips ↔ Bank (M7) e, se voluto, pagamenti reali con token di scrittura (M8–M9) | approvazione esplicita, rischio finanziario |

---

## 8. Riferimenti

### File
- `03 Software/RF-One Data Store/rfone_data_store/technical/connectors/mercury/__init__.py`, `client.py`
- `03 Software/RF-One Data Store/rfone_data_store/tips/payment_connector.py`, `payment_instruction.py`, `payout_process.py`, `payment_cycle_service.py`, `payment_readiness.py`, `schedule_service.py`, `scheduler.py`, `readiness.py`
- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `TipsPaymentScheduleConfig.mercury_source_account_id`, `EmployeeExternalPaymentAccount`, `TipPaymentInstruction`, `PayrollRun.payment_execution_provider`
- `03 Software/RF-One Data Store/rfone_data_store/bank_reconciliation/purpose_evidence.py` (predisposizione `source_memo`)
- Migrazioni: `efe49dbc7321`, `2b7d65e73c2e`, `96337baf293c`, `b4f3c8a1d6e2`, `f2c8b6d4e1a7`
- Test: `test_tips_payment_connector.py`, `test_tips_payment_execution.py`, `test_tips_scheduler.py`, `rfone_data_store/tips_payment_*_validation.py`; script reale `03 Software/Tips/sandbox_pilot_e2e.py`
- UI: `03 Software/Tips/templates/payment_control.html`, `_general_configuration_section.html`
- Documenti: `01 Domains/Business Domain/Restaurant/Tips/Tips Payment Execution.md`, `Tips Configuration.md`; `01 Domains/Shared Domains/Administration/Payroll/Payment Execution.md`; `01 Domains/Shared Domains/Administration/Bank Reconciliation/BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md`; `01 Domains/Shared Domains/Intercompany Funding & Settlement/SETTLEMENT_POLICY_001.md`
- Report: `07 Tasks/Reports/TASK_TIPS_CORE2_PILOT_REPORT.md`, `TASK_PAYROLL_002_REPORT.md`, `TASK_PAYROLL_003_REPORT.md`; `PROJECT_STATE.md`; `RF_ONE_2_0_BASELINE.md`; `LOCAL_ENVIRONMENT.md` §3.3

### Branch / commit
- `main`, `origin/main` (@ `9c154f9`), `release/bank-reinstall`, `handoff/2026-10-17` (working copy) — connettore presente e identico
- Commit chiave: `87d73f7` (pilota), `229cd90` (STEP 12B), `c70b3ef` (chiusura baseline)

### Servizi AWS (account `418674484214`, `us-east-1`) — letti, non modificati
- App Runner `rfone-tips` (RUNNING, immagine `tips-performance-20261112t002621z`): contiene il codice Mercury, **nessuna variabile o secret Mercury**
- App Runner `rfone-web`: nessuna variabile Mercury
- Secrets Manager: nessun secret con "mercury" nel nome
- SSM Parameter Store: nessun parametro
- RDS (tramite secret `rfone-tips/database-url`): schema pagamenti Tips presente, tabelle vuote (verificato sulla copia locale)
- Nessuna Lambda, API Gateway o job ECS relativo a Mercury

### Credenziali (solo presenza)
- `MERCURY_SANDBOX_API_TOKEN`: valorizzata in `RF One/.env` (locale, git-ignored, dentro OneDrive)
- Token di produzione: **non trovati** in file locali, variabili d'ambiente o AWS
