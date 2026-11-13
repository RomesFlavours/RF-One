# Regole generali, per categoria WHO e per singolo WHO

**Codice:** BANK_RULE_SCOPE_AND_WHO_CATEGORY_001  
**Decisioni del Product Owner:** 2026-11-03.  
**Stato:** analisi e requisiti approvati da conservare per lo sviluppo. Questo documento non certifica che tutte le funzioni descritte siano già implementate.

## 1. Obiettivo della modale Controlla

La modale parte dal gruppo già scelto e dalle sue occorrenze. Serve a capire se esiste una regola applicabile all’intero gruppo o a sottogruppi verificabili; non richiede di ricostruire filtri tecnici o di selezionare arbitrariamente sei movimenti.

Mostra il WHO/gruppo, il motivo dell’apertura, le occorrenze e le evidenze. L’analisi AI distingue: non ancora eseguita, in corso, proposta disponibile, nessuna regola sufficientemente supportata, dati mancanti ed errore tecnico. Un blocco di file su altre Source non deve essere rappresentato come incapacità dell’AI né impedire l’analisi assistita del gruppo disponibile. La riconciliazione automatica complessiva mantiene i propri controlli di completezza.

Un solo ingresso per riga, «Controlla», porta al percorso che comprende AI e dettagli avanzati. Non introdurre flussi paralleli sulla riga.

## 2. Tre ambiti delle regole WHY

| Ambito | Significato | Esempio |
|---|---|---|
| Generale | Condizioni trasversali, non legate a un solo WHO | Criteri di classificazione che dipendono dalla natura del movimento e dalla Source |
| Categoria/tipo di WHO | Politica comune ai WHO che svolgono un’attività verificata | Ristoranti + Source personale/aziendale |
| Singolo WHO | Condizioni per una controparte o un suo servizio particolare | Distinguere servizi UBER o classificare articoli Amazon |

Questi sono ambiti delle regole di determinazione del WHY: non vanno confusi con le regole che estraggono o riconoscono il WHO. Non ripristinare il vecchio motore General Rules documentato come rimosso in BANK_GENERAL_RULES_001.

La categoria di WHO descrive l’attività della controparte/servizio; non è il WHAT contabile e non coincide con la modalità WHO UNIVOCO/MULTIPLO. Il WHAT continua a derivare dal WHY.

## 3. Nessuna precedenza rigida che impedisca l’accorpamento

Non è approvata una gerarchia fissa «la specifica prevale sempre e la generale è soltanto un ripiego». Una regola generale o per categoria può risolvere correttamente più regole di singoli WHO e più transazioni.

La simulazione confronta tutti gli ambiti interessati e distingue:
- **equivalenza:** le regole producono lo stesso risultato nell’ambito verificato; proporre accorpamento;
- **eccezione legittima:** una specifica risolve casi differenti che la generale non copre; conservarla esplicitamente;
- **contrasto:** risultati incompatibili; mostrare condizioni, regole e movimenti interessati e richiedere una decisione.

Non scegliere arbitrariamente la prima regola né usare l’AI per scavalcare un conflitto non risolto. Le decisioni manuali confermate rimangono protette.

Modificando una generale/per categoria, mostrare transazioni risolte o cambiate, regole specifiche rese ridondanti, eccezioni da mantenere e conflitti. Dopo simulazione e approvazione esplicita, si può applicare la nuova regola e **disattivare/archiviare** quelle sostituite, preservando versioni, provenienza, storico e ripristino. Non cancellare distruttivamente né disattivare automaticamente.

L’equivalenza sugli esempi storici non dimostra da sola equivalenza delle condizioni su tutti i movimenti futuri: dichiarare l’ambito verificato e gli eventuali limiti.

## 4. L’AI riconosce anche il tipo di WHO

L’AI può proporre, anche mediante ricerca internet, che una controparte o un servizio appartenga a una categoria (ristorante, supermercato, compagnia aerea, ecc.). Conservare categoria proposta, evidenze/fonti, certezza e conferma/decisione che ne autorizza l’uso; non ripetere inutilmente la stessa ricerca finché il contesto resta valido.

L’identità esatta o la filiale non devono bloccare la classificazione quando la natura necessaria è sufficientemente stabilita. Se l’identità resta incerta, usare il percorso WHO generico senza inventare un’identità a catalogo.

Esempio approvato:
- tipo WHO/servizio = ristorazione (ristorante, bar o caffetteria);
- Source personale alla data → `Owner Personal — Restaurant`;
- Source aziendale alla data → `Business Meals & Entertainment`;
- titolarità non determinabile → richiesta mirata, non assunzione.

Non dedurre che ogni acquisto presso un intermediario o fornitore eterogeneo abbia la stessa natura.

## 5. Dichiarazioni dell’utente e regole contestuali: UBER

Il Product Owner dichiara: **«Io uso UBER soltanto per trasporto».** È un’informazione esplicita utilizzabile per proporre una regola contestuale alle sue Source, da simulare e confermare; non è una proprietà universale di UBER e non va estesa ad altri utenti o aziende.

Distinguere le due informazioni: «tipo di servizio = trasporto» e «WHY corretto», che dipende anche dalla Source e dalle politiche approvate. Non inventare un WHY definitivo o applicare la dichiarazione ai dati reali con la sola scrittura di questo documento.

Se una descrizione o un documento indica un servizio diverso o contraddice la dichiarazione, isolare l’eccezione e chiedere un chiarimento. La rappresentazione bancaria distinta di Uber Eats rispetto a Uber trasporto **non è stata verificata** e non deve essere assunta come garanzia.

Un report serve quando rimane un’ambiguità rilevante. Non richiederlo per principio se descrizione, evidenze e dichiarazione contestuale approvata bastano.

Amazon è un WHO con acquisti eterogenei: usare il report articoli e le ripartizioni quando servono. Conservare le tre righe dei ventilatori come acquisti reali; non deduplicarle per identità di testo e non moltiplicare il totale ordine ripetuto.

## 6. Editor, simulazione e applicazione nella riconciliazione corrente

La modale Controlla deve consentire di definire o rivedere regole generali, per categoria e per quel WHO. Il pulsante «Definisci regola» richiama l’editor esistente con le liste WHY e WHAT da cui copiare i riferimenti, senza costruire un editor parallelo.

Percorso: **definisci/modifica → simula → conferma → salva e applica ora**, oppure salva una bozza distinta e inattiva.

La simulazione mostra risultati prima/dopo, movimenti coperti/esclusi, sottogruppi, conflitti e impatto sulle altre regole. Cambiando testo, versione, dati o contesto rilevante, la simulazione va invalidata e ripetuta.

Dopo conferma esplicita la regola si può attivare e applicare subito ai movimenti pertinenti del riconcilio corrente, senza doppie applicazioni e senza sovrascrivere decisioni umane. Aggiornare elenco, conteggi e casi aperti e conservare il contesto di ritorno. La regola entra nel motore condiviso per i caricamenti futuri.

## 7. Guida contestuale obbligatoria

Ogni pagina Bank ha «Come funziona» (How Works nella versione inglese), diretto alla sezione di quella pagina nella guida Bank. Ogni modale ha un «?» visibile che apre **la sezione esatta della descrizione di funzionamento di quella modale**, non la cima della guida o una spiegazione generica.

L’apertura/chiusura della guida non perde campi, filtri, selezioni, posizione o bozza. La guida segue la lingua della UI (italiano locale, inglese condiviso/pubblicato), descrive il comportamento implementato e si aggiorna insieme al codice. Per lo standard condiviso vedere `03 Software/Shared UI/How Works Standard.md` (UI_HOW_WORKS_001).

## 8. Tracciabilità e stato

Questa registrazione raccoglie le decisioni successive al lavoro su WHO UNIVOCO/MULTIPLO e sulle regole WHY (`BANK_WHO_WHY_MODE_001`) e integra il percorso di `BANK_UPLOAD_AND_RECONCILE_001`. Non sostituisce i controlli di sicurezza applicativa, il modello di classificazione o le autorizzazioni ai provider.

Nessuna regola o categoria è attivata, nessun movimento è riconciliato e nessun database è modificato da questa attività documentale. Implementazione e test sono da verificare nel lavoro in corso; non presentarli come già completati.


## 9. Stato di implementazione (sviluppo locale, 2026-11-04)

Implementato nel codice locale, non pubblicato e non applicato al database operativo. Verificato su copie isolate del database.

- **Ambiti:** le regole WHO WHY (`who_why_rules`) hanno tre ambiti — `WHO`, `CATEGORY`, `GENERAL` — con lo stesso ciclo di vita (bozza non attiva, attivazione, sostituzione approvata con storico e ripristino). Il motore valuta tutte le regole applicabili senza precedenza: stesso WHY = un risultato; WHY diversi = «Regole in conflitto».
- **Simulazione tra ambiti** (C-Bank `rule_scopes.simulate`): equivalente (sui dati attuali, oppure anche sulle condizioni), complementare, in contrasto, eccezione mantenuta (eccezione esplicita «il WHO è tra …» nella regola più ampia). Non si applica con conflitti aperti; un token invalida la simulazione se cambiano regola, scelte, dati, regole o contesto.
- **Categoria WHO e dichiarazioni** (`who_categories`, record append-only in `bank_flow_artifacts`, nessuna migrazione): proposta AI con ricerca internet sul solo nome del WHO, evidenze, fonti, certezza; usata dalle regole per categoria solo dopo conferma. Una dichiarazione contestuale dà la categoria al WHO soltanto sulle Source dichiarate.
- **Modale Controlla:** «Definisci regola» apre l’editor delle regole WHY nella modale. L’editor dei profili di riconoscimento resta raggiungibile, ma — verificato sulla copia — non si applica ai movimenti con WHO già riconosciuto (gruppo UBER: 0 di 72 nella coda dei profili) né ai nuovi movimenti il cui WHO non è letto da una regola di estrazione. Decisione del Product Owner richiesta: vedi il report di consegna.

## Indirizzo permanente di sviluppo RF-One (2026-11-04)

Applicare UI_OUTCOME_SINGLE_FLOW_001, documentato in `03 Software/Shared UI/Outcome and Single-Flow Design Standard.md`: esperienza orientata al risultato, un solo percorso principale per obiettivo, complessità gestita dal sistema, richieste umane necessarie e contestuali. «Controlla» è l’ingresso unico al completamento del gruppo; AI, editor regole e dettagli sono attività interne al percorso, con ritorno e stato conservati. Prima della consegna verificare coerenza con tutte le regole scritte pertinenti e correggere le difformità. L’inserimento formale del principio nel Core resta proposto per il confronto con Shelbi.
