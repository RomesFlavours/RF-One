# RF-One — Registro di riconciliazione decisioni → documenti
**Data:** 2026-11-22  
**Natura:** registro di audit, non nuova specifica funzionale. Basato sulle decisioni esplicite del Product Owner nelle conversazioni e sui file effettivamente letti su GitHub.  
**Stati:** `MATCHED` = documento esistente corrispondente verificato; `GAP` = non riscontrato nella documentazione canonica esaminata; `PARTIAL` = esistono riferimenti ma non è documentata l'intera decisione; `OPEN` = non assumere approvazione o dettaglio; `RUNTIME UNVERIFIED` = non attribuire alla documentazione prova di AWS.

**Importante:** una decisione riportata qui non diventa automaticamente mandato di implementazione. Le decisioni che non sono state ancora formalizzate come specifiche vanno trascritte e approvate per la rispettiva fase; il codice non è un sostituto.

## A. Decisioni e relative lacune

| ID | Area | Decisione o vincolo approvato | Riscontro Git e azione | Stato |
|---|---|---|---|---|
| G-01 | Governance | Product Owner + ChatGPT progettano; Claude implementa la specifica; Codex verifica indipendentemente; Product Owner autorizza merge e deploy | `README.md`, `CLAUDE.md`, `AGENTS.md` su `main` | MATCHED |
| G-02 | Core/data | Modello informativo canonico RF-One indipendente dai provider; i connettori acquisiscono dati ma i domini non assumono il modello Clover | `00 Core/ExternalDataMappingPrinciples.md`, `03 Software/RF-One Data Store/README.md` | MATCHED in principio; verificare l'applicazione |
| G-03 | UI | Le nuove funzioni devono rispettare regole UI/How Works senza mascherare elementi annidati con workaround | `03 Software/Shared UI/UI Rules.md`, How Works presente nei branch feature | PARTIAL: verificare versione corrente e ruoli |
| B-01 | Bank | RFBank è unica base ufficiale, non BankAWS/Bank 1.0; nessun secondo motore | `rfbank/main` separato; `main` mantiene molte specifiche Bank storiche | PARTIAL; disciplinare ramo operativo/canonico |
| B-02 | Bank WHO | Testuale → regole WHO solo testuali (Source opzionale) → AI residui; nessun WHY nel riconoscimento WHO | `BANK_WHO_FUNCTIONAL_MODEL_20261122.md` ora nel canonico `main` | MATCHED (design only) |
| B-03 | Bank WHO | Tre classi esclusive: univoco, plurimo, di gruppo; nome reale conservato e gruppo come WHO operativo; zero/uno gruppo per WHO | Stessa specifica WHO 22/11 | MATCHED (design only) |
| B-04 | Bank WHO | Nuovi WHO AI proposti nel Riconcilio; nuovi WHO di gruppo AI marcati 'da confermare'; alias certi automatici, incerti da confermare | Stessa specifica WHO 22/11 | MATCHED (design only) |
| B-05 | Bank WHO | Risultato WHO parziale persistito; conferme umane protette; correzioni simulate e tracciate | Stessa specifica WHO 22/11 | MATCHED (design only) |
| B-06 | Bank import | Import conti/carte separato da import Zelle/PayPal/ADP/Amazon; matching arricchitori nell'import, non nel motore WHO; manual run di riconciliazione | Registrato nel documento WHO come confine; dettagli import indipendenti non ancora canonizzati | PARTIAL |
| B-07 | Bank aggregate | Modello di movimenti con zero/una/più righe economiche; ADP e Amazon possono esplodere un movimento senza WHO/WHY sul padre | Decisioni in dialogo; vecchi docs Bank non sostituiti | GAP, **fase successiva** |
| B-08 | Bank WHY | WHO univoci → WHY approvato; plurimi → regole approvate, nessuna AI su WHY; Gruppo + Source determina WHY secondo decisione approvata; FOH/BOH non cambiano WHY | Vecchie regole di ottobre non affidabili come specifica corrente; documento WHO rinvia il WHY | GAP, **non sviluppare finché WHO non collaudato** |
| B-09 | Bank contabilità | Entity deriva solo dalla Source; rettifiche su già esportato/chiuso hanno prima/dopo WHO, WHY, WHAT, allocazioni, coda export per Bookkeeper; export progressivo | Decisioni registrate nel dialogo, non ancora specifica completa; QBO compatibilità da verificare | PARTIAL / fase rinviata |
| B-10 | Bank matching | Giroconti/pagamenti carte pre-WHO, intercompany distinto; contropartite mancanti in attesa; statement mancanti non bloccano gli altri movimenti | Nel documento WHO come confine; il matcher sarà verificato nella fase propria | PARTIAL |
| R-01 | Registry | Ruolo / Reparto gestiti in Anagrafica; FOH/BOH reparti in Restaurant Operations; Server Help ruolo separato FOH | `feature/registry-clover-departments`: piano `REGISTRY_CLOVER_DEPARTMENTS_RELEASE_PLAN.md`; nuovo codice in branch | PARTIAL, documentazione canonica da integrare |
| R-02 | Registry | Registro persone unico; Selection e Training inviano/riutilizzano la persona; nuovi inserimenti manuali/Training, non dipendenza obbligatoria da Clover | Documenti `Selection`, `TRAINING_SERVICE_001.md` e branch Registry da rivedere insieme | GAP/PARTIAL; audit integrazione |
| R-03 | Clover | Ruolo Clover letto come dato sorgente, sincronizzazione dei cambi senza due ruoli aperti, WP/MD separati; import multipla senza doppioni | Branch `feature/registry-clover-departments`, `feature/clover-multisite-registry` | PARTIAL |
| R-04 | Registry / Clover | MD multisede senza mischiare WP; non assumere MD già attiva sulla base del solo piano | `CLOVER_MULTISITE_RELEASE_PLAN.md` esplicitamente PLAN ONLY; documenti AWS più recenti vanno confrontati | RUNTIME UNVERIFIED |
| T-01 | Tips | Regole di distribuzione/percentuali propri del dominio; Registry fonte della mappatura ruoli Clover→RF-One; nessun secondo mapping operativo Tips | `feature/tips-registry-roles:SOURCE_ROLE_MAPPING_RETIREMENT.md` | PARTIAL: manca riferimento canonico su `main` |
| T-02 | Tips | Ruoli storici per validità, non proiettare ruolo corrente nel passato; periodi definitivi e pagamenti non vanno ricalcolati implicitamente | `SOURCE_ROLE_MAPPING_RETIREMENT.md`, `Tips/Finalized Tips Period.md` | MATCHED nel disegno, runtime da verificare |
| T-03 | Tips | Regole Host #2/#3 con validità non sovrapposta e correzione di AWS; disattivazione non deve cambiare il passato | Report operativo del 21/11 e `RULE_DEACTIVATION_RETROACTIVE_DEFECT.md` su branch feature; `Tips/Tip Policy.md` norma tempi | PARTIAL: target UI e codice da rivedere, AWS runtime non ispezionato |
| T-04 | Tips multisede | Nessun import/export/calcolo/pagamento di MD senza sito attivo; separazione per ristorante e sede | Branch `feature/clover-multisite-registry` piano di rilascio | PARTIAL / RUNTIME UNVERIFIED |
| C-01 | Compensation | Voci retributive e paga non cambiano automaticamente quando cambia il ruolo; separare compenso e payroll provider | `Personnel Management/Compensation/README.md` draft; `COMPENSATION_AND_INCOME_COMPOSITION_001.md` | PARTIAL, revisione V1 necessaria |
| S-01 | Selection | Job Position Draft/Active/Closed e comunicazioni ai candidati; invio a Training e riuso del Registry | `Selection` docs e rapporti vecchi di settembre; recente integrazione da verificare | GAP / PARTIAL |
| S-02 | Selection | AI interview e criteri di screening, colloquio, evidenze, prerequisiti; evitare criteri non approvati | `Selection` canonical docs; stato attuale report del 06/09 | PARTIAL; confrontare tutte le decisioni successive |
| TR-01 | Training | Corso Server in 15 unità, avanzamento, prove, attestazione lead, conferma assunzione, inviti automatici e paid training time | `TRAINING_SERVICE_001.md` + contenuti corso in branch Registry; non assumere convergenza | GAP/PARTIAL |
| TR-02 | Training/Operational Knowledge | Training service e Operational Knowledge (Pills): responsabilità funzionale vs posizione Domain | `TRAINING_SERVICE_001.md`, `Operational Knowledge/README.md`, `CLAUDE.md` | PARTIAL; chiarimento redazionale |
| M-01 | Management | People/Organization/PM, processi owner+backup, controlli e decision log, follow-through, attenzione quotidiana | `Restaurant/MyRF/Project Management/README.md` v1 del 12/10; documenti Management parziali in branch feature | GAP/PARTIAL; evitare di promuovere draft 21/10 a policy |
| M-02 | MyRF/Kitchen Call | MyRF primo rilascio: progetti, assegnazioni, attenzione e decision log; Kitchen Call PWA | Documentazione locale/software in branch feature, `main` non prova release finale | GAP/PARTIAL |
| W-01 | Wines | Campo annata amministrazione/DB, misure discovery e contenuti vino per formazione vendita per livelli | Non riscontrata specifica canonica corrente tra i file campionati di `main` | GAP da ricerca estesa |
| K-01 | Kitchen/Visual Menu | Contenuti Kitchen e Visual Menu, check UI e accessi | La presenza in codice non dimostra spec approvata su `main` | GAP da ricerca estesa |
| INF-01 | Infra | AWS come ambiente principale; NAT e infrastruttura autorizzati nei rispettivi lavori; Render solo pilota | `03 Software/Infrastructure/` e branch release; stato AWS non deducibile dai file | PARTIAL |
| L-01 | Legacy/Brand | Legacy 1.0 Rev.2 e Brand come riferimento validato; non sostituirlo con corso o bozza non approvati | Copie di `legacy-1.0-rev2.md` in branch feature | PARTIAL: identificare master approvato e versioni |

## B. Incoerenze da risolvere con evidenze, non con implementazioni
1. **La documentazione Bank del 13/10** si presenta come current state su `main`, ma la nuova specifica WHO è ora canonica per il perimetro WHO. Le pagine storiche non vanno cancellate: annotare come superate per WHO.
2. **Tips usa Registry** nel branch verificato; il `main` può descrivere metodi storici di risoluzione SourceRole. Non cambiare percentuali.
3. **Training**: non confondere una relazione funzionale con una riorganizzazione del Domain senza decisione.
4. **Registry e Clover**: non trasformare la scelta di mantenere Registry indipendente da Clover in cancellazione arbitraria del connettore Clover; distinguere fonte facoltativa da autorità canonica.
5. **Management**: parte dei documenti è un draft per revisione con Shelbi, non policy già approvata.
6. **Stato AWS**: branch o piani di deploy non equivalgono a release avvenuta.

## C. Prossima verifica Codex
Per ogni riga `PARTIAL` e `GAP`, Codex dovrà verificare il documento sorgente e le revisioni reali, classificando `PASS / FAIL / NOT VERIFIED` rispetto al testo approvato, senza inserire nuove scelte funzionali. Le decisioni ancora aperte restano aperte.

## D. Governo del registro
Aggiornare questo registro per decisioni importanti, indicando **una** specifica canonica per dominio, l'eventuale branch implementation e la verifica Codex. Non registrare come `APPROVED` le semplici proposte dell'assistente. Nessuna riga autorizza deploy.
