# Registry / Restaurant Organization — Ruoli, reparti e sorgenti
**Decisioni funzionali consolidate al 22 novembre 2026**  
**Stato:** specifica di responsabilità e mapping approvati; lo stato runtime AWS indicato nei report di rilascio deve essere verificato separatamente.  
**Ambito:** anagrafica, ruoli e reparti; **non** modifica Clover, Tips, Compensation o Bank.

## 1. Autorità e responsabilità
- **RF-One Registry** custodisce l'identità canonica della persona, il ruolo organizzativo e il reparto configurato in RF-One.
- **Clover** è una possibile sorgente del ruolo operativo POS; il ruolo Clover **non** determina da solo l'organizzazione canonica e non conferisce automaticamente ruoli fuori dall'ambito previsto.
- Per le persone non importate da Clover, Registry deve supportare i flussi approvati di inserimento manuale e da Training/Selection. La presenza di un importatore Clover non costituisce dipendenza obbligatoria dell'anagrafica.
- La classificazione **FOH/BOH** appartiene a Registry per i ruoli operativi e non definisce di per sé il WHY contabile in Bank.
- I ruoli POS/Registry sono distinti dalle autorizzazioni di accesso e dalle regole di ripartizione Tips.

## 2. Reparti e tabella ruolo/reparto
- `Restaurant Operations` rimane l'area organizzativa.
- `FOH` e `BOH` sono **reparti** all'interno di Restaurant Operations, non domini distinti.
- La mappatura è una tabella **configurabile in Anagrafica → Reparti e ruoli** e può differire per sede.
- I ruoli RF-One **Server**, **Host**, **Cook**, **Dishwasher**, **Server Help** sono distinti. **Server Help è un ruolo autonomo FOH**, non alias di Server.
- Mapping approvato dell'Excel storico: `2-Serv → Server / FOH`; `3-Host → Host / FOH`; `4-Cook → Cook / BOH`; `6-Dish → Dishwasher / BOH`.
- Dati Clover WP: `Server` e `Host` → FOH; `Team Leader` → FOH nell'ambito già approvato; `BOH` → reparto BOH, ruolo RF-One specifico non presumibile.
- `Manager`, `Admin`, `Employee`: **non** dedurre automaticamente FOH/BOH senza conferma di ruolo funzionale.

## 3. Import Clover (se attivato)
- Riutilizzare **l'importatore esistente**; niente secondo sincronizzatore.
- Le identità sono ricondotte ai codici sorgente e agli identificativi canonici, con protezioni contro duplicati.
- Per ogni sede, la modifica di ruolo chiude l'assegnazione precedente e ne apre una nuova, conservando lo storico.
- Quando una persona scompare dalla fonte Clover, chiudere l'assegnazione proveniente dalla sorgente **senza eliminare la persona**.
- Le assegnazioni manuali e la documentazione storica non vengono sovrascritte da una sincronizzazione.
- Winter Park e Mount Dora sono contesti separati: una persona può operare in entrambe le sedi senza duplicare la sua identità.
- Una seconda importazione dello stesso contenuto deve essere idempotente.
- Nessun import di vendite MD è implicitamente autorizzato dal recupero dei suoi dipendenti.

## 4. Dati storici Excel
Il file storico `2026 - WP Control Bank.xlsb`, foglio `Note`, è fonte di identità, reparto e ruolo storico:
- dal report di confronto: 57 righe con nome/ID, 56 persone distinte, 48 persone con ruolo/reparto documentati, tutte 56 già riconciliate in Registry via identificativo Clover;
- **non** trasferire in Registry dati bancari, coordinate di deposito, stipendi o telefoni per il solo scopo della classificazione ruoli;
- non dedurre lo stato di servizio attuale dall'Excel;
- se ruolo storico e ruolo Clover corrente differiscono, preservare la distinzione temporale, non sovrascrivere il presente con il passato.

## 5. Confini verso altri domini
- **Tips** usa il ruolo valido nel tempo e la corrispondenza di Registry; mantiene le proprie politiche e percentuali di distribuzione.
- **Compensation** mantiene condizioni retributive indipendenti da un cambiamento automatico del ruolo Clover; nessun ricalcolo automatico dei periodi approvati.
- **Bank** può utilizzare il reparto come elemento gestionale quando sarà progettato, ma la classificazione WHO di gruppo resta autonoma e non coincide con FOH/BOH.
- **Training e Selection** possono creare/riutilizzare la persona canonica, secondo specifiche approvate separatamente.

## 6. Stato e verifiche
Il report del rilascio Registry del 21/11 riferisce: WP sincronizzata, tabella FOH/BOH e pagina attive su AWS, storico Excel caricato, Mount Dora non sincronizzata in quel rilascio. Sono **evidenze di report**, non un'attestazione indipendente del runtime AWS da parte di questo audit.

Il piano `REGISTRY_CLOVER_DEPARTMENTS_RELEASE_PLAN.md` nel branch `feature/registry-clover-departments` contiene lo stato originario **prepared, not executed** ed è storico; il successivo `CLOVER_MULTISITE_RELEASE_PLAN.md` nel branch `feature/clover-multisite-registry` è un piano per la fase multisede, non prova di deploy.

## 7. Divieti
Nessun aggiornamento di dati AWS, nessun import o deploy implicito e nessun nuovo modello organizzativo oltre le corrispondenze approvate. Se il codice attuale differisce, aprire un rilievo di conformità, non riscrivere la specifica per giustificarlo.
