# RF-One — Audit documentale trasversale, ricognizione iniziale
**Data:** 2026-11-22  
**Repository:** `RomesFlavours/RF-One`  
**Branch principale ispezionato:** `main` @ `96f29f6a3a7d9b460198e89c095726ecf4d7e46f`  
**Branch Bank separato:** `rfbank/main` @ `c5b43b7dc077170d6a32720cdf05949633963857`  
**Stato:** AUDIT IN CORSO — inventario completo dei percorsi e analisi mirata di documenti principali; **non** certificazione del contenuto di tutti i file, né conformità runtime o stato AWS.

## A. Metodo e inventario
La ricognizione ha letto l'albero Git completo di `main` (1.569 elementi, non troncato) e rilevato **433 file .md/.txt**. Sono stati letti direttamente gli entrypoint e un campione mirato di documenti canonici e tecnici nei domini Bank, Tips, Selection, Training/Operational Knowledge, Compensation, Restaurant Organization, Core, Clover e MyRF, oltre a governance e stato del progetto. Non sono stati eseguiti deploy, modifiche ai database o controlli AWS.

I documenti hanno livelli di autorità diversi secondo `README.md`: `00 Core/`, `01 Domains/`, `02 Products/`, `09 Strategy/`, `10 System/` per il significato progettuale; `03 Software/` per l'implementazione; `07 Tasks/`, `PROJECT_STATE.md` e `90 Archive/` come storia/evidenza, non come autorità corrente. Non prendere una dicitura `IMPLEMENTED` come prova del comportamento attuale su AWS.

### Dimensione documentale rilevata
- `01 Domains/Shared Domains/`: 105 documenti
- `01 Domains/Business Domain/`: 99
- `07 Tasks/Reports/`: 71
- `90 Archive/Legacy Repository/`: 36
- `00 Core/ConceptualArchitecture/`: 19
- `90 Archive/Task History/`: 17
(I conteggi sono per prefisso del percorso; non sono una misura di approvazione.)

## B. Riscontri verificati e lacune di allineamento

| ID | Area | Esito | Evidenza | Azione proposta |
|---|---|---|---|---|
| AUD-01 | Bank, governance di branch | **BLOCCO documentale** | Nuova specifica WHO `docs/RFBANK_WHO_SPEC_DECISIONS_20261122.md` presente su `rfbank/main`, **non nel** `main`. Il canonico Bank su `main` è in `01 Domains/Shared Domains/Administration/Bank Reconciliation/` e `README.md` descrive come "current state" il reset del 13/10 e la classificazione con AI Rules. | Non dichiarare il canonico Bank aggiornato. Confrontare decisioni WHO 22/11 con documenti Bank già superseded; integrare il documento canonico SOLO dopo review per evitare conflitti, preservando lo storico. |
| AUD-02 | Stato globale | **FRESCHEZZA NON ATTESTATA** | `PROJECT_STATE.md` dichiara un indice stato attuale aggiornato al commit `66289c3` (fase STEP 12B/12C), mentre le attività operative riferite da 20–22/11 includono versioni successive Registry, Tips e Bank su altri branch. | Ricostruire stato per branch, versione AWS eseguita, locale e prove: non sovrascrivere lo stato senza riscontri runtime. |
| AUD-03 | Training/Operational Knowledge | **TENSIONE TERMINOLOGICA DA CHIARIRE**, non contraddizione automaticamente provata | `CLAUDE.md` descrive Operational Knowledge quale Shared Domain autonomo; `TRAINING_SERVICE_001.md` §3 lo definisce componente interno a Training sul piano funzionale; `Operational Knowledge/README.md` conserva la sua natura Shared Domain e menziona la decisione Training. | Aggiungere una nota esplicita che distingue collocazione nella tassonomia dei Domain e responsabilità funzionale del Training Service, senza riclassificare autonomamente. |
| AUD-04 | Clover / Data Store | **BASE DOCUMENTALE DATATA / DIFFERENZA DI Cadenza** | `03 Software/Infrastructure/deploy/clover-correction-sync/README.md` documenta un poller circa **60 s** approvato nel settembre 2026; le decisioni più recenti del Product Owner (21/11) parlano di **un unico motore Clover, acquisizione incrementale ogni 30 s**, indipendenza del database operativo dalle sorgenti. | Confrontare decisione più recente, codice che gira su AWS e architettura; distinguere requisiti target, implementazione presente e migrazione prevista. |
| AUD-05 | Registry / Clover multisede | **APPROVAZIONE PIÙ RECENTE NON RISCONTRATA COME CANONICO SU MAIN** | L'utente ha deciso nuova Registry multisede, WP/MD separati, input manuale/Training e nessun obbligo di import Clover; i file principali consultati su `main` continuano a descrivere acquisizione Clover e Organization preesistenti. | Cercare nei branch specifici la specifica Registry approvata e formalizzarne il posto canonico. Separare connettore Clover e Registry, preservando provenienza e identità storiche. |
| AUD-06 | Tips | **RISCHIO DI CONFONDERE SPECIFICA E VERSIONE AWS** | `Tips/README.md` e `Finalized Tips Period.md` descrivono regole temporalmente valide e periodi finalizzati immutabili. I report del 21/11 registrano la correzione delle regole #2/#3 su AWS e nuovo mapping Tips→Registry non ancora deployato. | Documentare distintamente comportamento progettato, configurazione corretta su AWS e codice di mapping in branch; verificare l'assenza di retroattività delle disattivazioni. |
| AUD-07 | MyRF Project Manager | **GAP DA CONFRONTARE** | `Restaurant/MyRF/Project Management/README.md` è v1 minimale del 12/10: task, responsabili come nomi, Gantt e progressi manuali. Le decisioni successive riguardano owner/backup, checkpoint, decision log, brief e attention feed. | Confrontare il modello approvato dopo il 21/10; non dichiarare la v1 vecchia come specifica completa del nuovo MyRF. |
| AUD-08 | Selection / Training | **FRESCHEZZA NON VERIFICATA** | `Selection/reports/SELECTION_CURRENT_STATUS.md` dichiara esplicitamente review del **06/09**; `TRAINING_SERVICE_001.md` nasce da decisione del **11/09** e si definisce documentazione-only. Le decisioni successive comprendono Send to Training, Registry reuse, inviti, corso 15 unità, firma e confirm hire. | Confronto con documentazione corrente nei branch e specifiche; non equiparare report vecchi a stato novembre. |
| AUD-09 | Compensation | **SPECIFICA DRAFT** | `Personnel Management/Compensation/README.md` segnala Version 0.2 / Draft, pur descrivendo alcuni componenti implementati. | Separare decisioni approvate, implementato e stato AWS; confrontare l'integrazione Tips e il rapporto con ADP. |
| AUD-10 | Governance agents | **COERENTE NEL CAMPIONE** | `README.md`, `CLAUDE.md`, `AGENTS.md`: progettazione Product Owner + ChatGPT → Claude implementa → Codex verifica → Product Owner autorizza merge/deploy. | Preservare la sequenza e distinguere approvazione della specifica, push, merge e deploy. |
| AUD-11 | Data ownership | **PRINCIPIO PRESENTE, APPLICAZIONE DA VERIFICARE** | `00 Core/ExternalDataMappingPrinciples.md` e `03 Software/RF-One Data Store/README.md` affermano modello canonico vendor-independent e source mapping. | Confrontare tutti i connettori e i domini per dipendenze dirette da Clover; confermare la distinzione tra documenti target e stato operativo. |
| AUD-12 | Altre aree (Wines, Kitchen, Visual Menu, Management) | **COPERTURA NON COMPLETA** | Nell'inventario del `main` non emerge una specifica corrente chiaramente nominata per tutte le scelte di novembre. La ricerca per titolo/percorso da sola non prova assenza di contenuto. | Ricerca testuale mirata su branch, archivio e fonti approvate; registrare le decisioni mancanti senza inventarle. |

## C. Priorità di riconciliazione
1. **P0:** mappa dei branch e documenti approvati non confluiti in `main`; Bank WHO, Registry, Clover, Tips.
2. **P0:** registro unico delle decisioni approvate con data, fonte, dominio, stato `APPROVED/OPEN/SUPERSEDED`, percorso canonico e branch; non usare il codice come fonte delle scelte.
3. **P1:** Management/MyRF, Selection→Training, Compensation, Wines, Kitchen/Visual Menu e altri documenti con revisioni di novembre.
4. **P1:** verificare cross-reference e link rotti e revisionare diciture "current", "deployed", "approved" e "implemented".
5. **P2:** consolidamento dei duplicati **senza cancellare** storia/archivi prima di verifica.

## D. Regole di aggiornamento
- **Non** fare merge automatici tra architetture e versioni software.
- Tenere distinta documentazione approvata, progettazione in discussione, implementazione e release verificata.
- Sostituire solo affermazioni dimostrate superate, lasciando link al documento storico.
- Per ogni correzione canonica: citare fonte della decisione, data, file precedente, controllo Codex.
- Non pubblicare dati personali, finanziari o credenziali nei documenti.
- Git locale, repository remoto e AWS **non** si sincronizzano automaticamente.

## E. Limiti di questo rapporto e prossime attività
La ricognizione dell'**albero** Git è completa, mentre la verifica **del contenuto** di 433 documenti non è ancora completa: è stata eseguita la lettura mirata di entrypoint, fonti canoniche e file tecnici selezionati. Anche la ricerca di decisioni nelle conversazioni non è ancora un registro esaustivo. Non dichiarare "tutta la documentazione aggiornata" né inviare tale attestazione a collaboratori.

La fase successiva è produrre un inventario decisione→specifica per ogni dominio, controllare i branch di feature e far verificare i gap a Codex; solo poi aggiornare documenti canonici uno per uno.
