# RF1_OPERATIONAL_DATABASE_001 — approved source decision (verbatim, Italian)

> **Immutable record.** This file preserves, verbatim, the decision approved by the
> Product Owner and supplied on 2026-11-21 as
> `RF1_Principio_Database_Operativo_e_Governance.md`. Do not edit it. The normative
> English text used by the repository is [README.md](README.md); if the two ever
> appear to differ, this original prevails and the discrepancy must be reported.

---

# RF-One — Principio architetturale obbligatorio

**Stato:** decisione progettuale approvata; da recepire nella documentazione effettiva del progetto.  
**Ambito:** RF-One Core, infrastruttura, Data Store, API, connettori, tutti i domini e moduli, standard di sviluppo, testing e rilascio.  
**Prevalenza:** ogni documento precedente che attribuisca a Clover, OpenTable o altro fornitore il ruolo di modello dati operativo principale deve essere corretto.

## 1. Principio non negoziabile

**RF-One possiede il proprio modello informativo e il proprio database operativo canonico.** Le applicazioni esterne (Clover, OpenTable, ADP, PayPal, Amazon o future sorgenti) non determinano la struttura logica di RF-One: forniscono dati tramite connettori/API/upload. Il futuro RF POS alimenterà lo stesso modello tramite interfacce RF-One. Sostituire una sorgente non deve obbligare a riscrivere i domini utilizzatori.

Non significa una sola tabella per ogni contenuto: significa un unico modello canonico RF-One, con entità coerenti e relazioni appropriate. Separare i dati operativi (ordini, pagamenti, righe ordine, tavoli, ecc.) dai dati finanziari e dagli arricchimenti quando hanno semantica differente, mantenendo comunque integrazione e governo comuni.

## 2. Flusso interno obbligatorio

1. **Sorgente** (API esterna, upload, connettore o applicazione RF-One) →
2. **Connettore di acquisizione**, responsabile soltanto dell'estrazione e della traduzione del formato di origine →
3. **Servizio comune di ingestione**, che identifica sede/entità, controlla validità, deduplicazione, checkpoint, errori e tracciabilità →
4. **Modello canonico e database operativo RF-One**, in cui i fatti aziendali sono registrati e aggiornati →
5. **Domini RF-One**, che leggono tramite interfacce e dati RF-One, mai direttamente dalle API o dalle tabelle specifiche di un fornitore per la normale logica di business.

I connettori possono avere staging tecnico, ma nessuna tabella di staging o schema di fornitore diventa un contratto informativo di WHO, WHY, Tips, Kitchen, Management o altri domini.

## 3. Acquisizione incrementale e integrità

- Per i POS esterni: **un solo servizio di acquisizione condiviso** per tutte le sedi, non un importatore per dominio; le sedi mantengono credenziali e identificativi distinti.
- **Obiettivo operativo: una verifica ogni 30 secondi**, nei limiti delle API e dei vincoli tecnici verificati. La frequenza è definita dal servizio comune, non dai domini.
- Sincronizzare soltanto dati nuovi o modificati dall'ultimo checkpoint consolidato; dopo un'interruzione recuperare automaticamente l'intervallo mancante.
- Aggiornare il checkpoint solo dopo scrittura valida; usare upsert idempotenti, chiavi RF-One e mapping degli ID esterni.
- Prevedere aggiornamenti tardivi, annullamenti, rettifiche, paginazione, retry e rilevazione delle lacune, senza duplicare eventi.
- Il primo import storico, ove necessario, è un'operazione di inizializzazione separata; non deve essere ripetuto ad ogni utilizzo di un dominio.
- Sedi/merchant e società devono restare correttamente separati.
- Conservare origine e ID esterno per audit, non come ID primario concettuale del modello operativo.

## 4. Proprietà dei domini

- **Clover, OpenTable e sistemi futuri:** sono fornitori/connettori sostituibili.
- **RF POS futuro:** scriverà negli stessi contratti canonici, senza rendere necessario un adattamento di Tips, Kitchen, Bank, Management o altri consumer.
- **Domini consumer:** interrogano esclusivamente RF-One per il proprio lavoro ordinario; non aprono accessi indipendenti allo stesso fornitore e non creano copie parallele dello stesso fatto aziendale.
- **Bank/Arricchitori:** gli arricchitori normalizzano informazioni esterne e valorizzano il campo di arricchimento del movimento RF-One, distinto da descrizione bancaria e memo originali. WHO/WHY consultano solo i campi canonici della transazione; non tabelle di fornitori o staging.

## 5. Contratti e modello dati da documentare prima dell'implementazione

Per ciascuna entità operativa, la progettazione deve definire: significato, campi, tipi, chiavi RF-One, relazioni, sede/società, provenienza, ID esterni, criteri di aggiornamento, mutabilità, storia/audit, errori e uso da parte dei domini. Per ciascun connettore: endpoint/formato, mapping campo per campo, frequenza, checkpoint, recupero, rate limits, credenziali, retry, deduplicazione, controlli e test. Evitare di inventare nomi di colonne o tabelle non verificati nel codice esistente.

## 6. Divieti di progettazione

1. Nessun nuovo motore Clover per un dominio o un periodo specifico.
2. Nessuna dipendenza diretta della logica dei domini dal database/schema di Clover o altro fornitore.
3. Nessuna duplicazione sistematica degli stessi eventi per ciascun modulo.
4. Nessun nuovo modello informativo deciso autonomamente da Claude durante l'implementazione.
5. Nessuna migrazione distruttiva o modifica alla produzione senza approvazione.

## 7. Processo di sviluppo vincolante

**Progettazione: utente + ChatGPT.** Definiscono comportamento esterno, architettura, flussi interni, modello dati, API, algoritmi, casi limite e criteri di accettazione.

**Implementazione: Claude.** Esegue le specifiche approvate nel codice, senza aggiungere workflow, schemi o decisioni architetturali autonomamente. Se emerge una scelta non definita, si ferma e la sottopone a progettazione.

**Revisione indipendente: Codex.** Verifica conformità, test, regressioni, dipendenze, schema e rischi. Non cambia i requisiti; segnala eventuali difformità prima del deploy.

**Rilascio:** soltanto dopo approvazione esplicita dell'utente. Nessun push, merge, deploy o modifica a produzione senza autorizzazione specifica, se non già espressamente autorizzati nell'incarico.

## 8. Allineamento documentale obbligatorio

Aggiornare tutte le fonti normative pertinenti: principi/Legacy/Model, architettura RF-One e Data Store, diagrammi dati, specifiche API, connettori/integrazioni, Clover multisede, OpenTable, RF POS, documentazione dei domini, istruzioni di sviluppo per Claude, checklist indipendente Codex, piano migrazione e collaudo. **Non** modificare automaticamente documenti storici firmati o report di esecuzione: contrassegnarli come storici e aggiungere rinvio alla decisione prevalente.

Per ciascun file modificato: registrare percorso, sezione, riferimento all'aggiornamento, eventuali incongruenze e decisioni ancora aperte. Eliminare o rettificare le affermazioni operative obsolete che autorizzano i domini a interrogare direttamente Clover. Conservare la storia delle modifiche.

## 9. Criteri di accettazione documentale

- Un nuovo sviluppatore identifica immediatamente un unico modello operativo RF-One, distinto dai sistemi sorgente.
- Il percorso end-to-end sorgente → connettore → ingestione → DB operativo → domini è definito in modo univoco.
- Ogni documento pertinente adotta gli stessi principi, senza istruzioni contraddittorie.
- Il contratto dei dati canonici è indipendente da Clover; la futura sostituzione con RF POS non richiede riprogettazione dei consumer.
- La sincronizzazione incrementale, il target di 30 s e le salvaguardie di integrità sono specificati, senza attribuire supporto API non verificato.
- Claude e Codex hanno istruzioni distinte e vincolanti sul proprio ruolo.
- Nessun codice, database o servizio AWS è modificato nell'attività di solo aggiornamento documentale.

## 10. Incarico operativo per Claude — solo documentazione

1. Inventaria tutta la documentazione pertinente nel repository e nelle cartelle locali RF-One, incluse le istruzioni per agenti e gli eventuali diagrammi.
2. Confronta ogni documento con il presente principio approvato.
3. Aggiorna **solo** documenti e diagrammi, rispettandone strutture e terminologia; crea una pagina di riferimento unica e linkala dalle altre, evitando copie divergenti.
4. Aggiorna le istruzioni di Claude con l'obbligo di implementare specifiche complete senza progettare autonomamente. Aggiorna la checklist Codex per la revisione architetturale indipendente.
5. Produci un registro dei documenti aggiornati, dei documenti storici non modificati e delle incongruenze ancora aperte.
6. Non cambiare codice, database, configurazioni, credenziali o AWS; non effettuare push, merge o deploy. Crea commit locale dedicato alla sola documentazione.

**Consegna a Codex:** il commit documentale e il registro modifiche. Codex deve verificare che tutte le principali fonti normative siano allineate e che non rimangano istruzioni contraddittorie; ogni lacuna torna alla progettazione.
