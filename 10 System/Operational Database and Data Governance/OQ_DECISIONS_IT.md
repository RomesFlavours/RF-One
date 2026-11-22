# Decisioni sulle questioni aperte OQ-1…OQ-11 — testo originale approvato

**Stato:** APPROVATO — Product Owner (progettazione Product Owner + ChatGPT), 2026-11-21.
**Natura:** testo originale, riportato senza modifiche. Non va riscritto: eventuali cambi richiedono una nuova decisione.
**Riferimento:** [README.md](README.md) §11 (resa inglese con stato attuale dell'implementazione); decisione di principio: [SOURCE_DECISION_IT.md](SOURCE_DECISION_IT.md). In caso di differenza prevale questo testo.

---

## Decisioni successive del Product Owner

Le decisioni qui riportate prevalgono sui punti OQ-1–OQ-8 precedenti per gli aspetti aggiornati. Il testo originale resta in fondo per tracciabilità. OQ-9–OQ-11 restano valide.

**OQ-1.** Acquisizione condivisa a mezzanotte di dati nuovi e correzioni; live a 30 secondi solo su richiesta attiva per sede. Ripresa dall’ultimo checkpoint valido.

**OQ-2.** Conservare l’ultima versione Clover e le evidenze grezze di audit. I periodi FINAL non si riaprono. Storico nativo rinviato a RF POS.

**OQ-3.** Inizio dal giorno operativo successivo all’ultimo consolidamento della sede; fine da parametro dedicato anche in manuale. Calcola e Consolida richiedono copertura verificata dell’intero periodo per sede. Se incompleta, blocco e motivo in modale con Scarica dati. Chi può calcolare può richiedere lo stesso processo notturno per la sola sede, senza CLOVER_ACQUISITION generale. Pagamenti separati.

**OQ-4.** A mezzanotte un solo motore apre due connessioni distinte, con credenziali, checkpoint ed esiti per sede. In futuro il live di ogni sede è indipendente.

**OQ-5.** Prove limitate all’inserimento di ordini del Server Tablet in Clover per la sede selezionata. Altri dati, modifiche e annullamenti dopo accettazione rinviati. Inserimento da implementare.

**OQ-6.** Step limitato a import conto/carta, import report arricchitori e collegamento dei singoli record ai movimenti corretti. Testo bancario originale intatto anche al reimport; copia normalizzata separata. Memo distinto da enrichment_note. WHO, WHY, regole, ripartizioni e utilizzo fuori perimetro. Adozione nel Data Store principale al collegamento degli arricchitori.

**OQ-7.** Selezione rilascia il candidato a Training. Solo dopo la conferma di arrivo dell’operatore Training lo iscrive e lo registra in Anagrafica come Studente. Poi Anagrafica lo crea in Clover per la sede competente e registra l’ID restituito come POS ID. Il ruolo Tips proviene da Anagrafica per persona, sede e data. Creazione Clover e POS ID da implementare; fonte della sede e record canonico da decidere.

**OQ-8.** Compensation legge da RF-One solo le Tips FINAL quando servono. Tips non invia dati né avvia Compensation. CALCULATED resta interno a Tips fino a FINAL.

## Testo originale delle decisioni

1. OQ-1 — Frequenza Clover. Un solo servizio di acquisizione controlla ogni 30 secondi sia i dati nuovi sia le correzioni, entro i limiti tecnici verificati. Dopo un’interruzione recupera ciò che manca ripartendo dall’ultimo salvataggio valido. Distingui la cadenza approvata dai precedenti intervalli di 15 e 60 secondi e dal comportamento del software attuale. Segnala le risorse per cui la copertura delle correzioni resta da verificare.

2. OQ-2 — Storico e rettifiche. RF-One mantiene lo stato corrente e registra le rettifiche rilevanti come eventi. Una rettifica non riapre automaticamente un periodo Tips chiuso. Lo storico necessario a spiegare le rettifiche appartiene a RF-One e deve restare utilizzabile se cambia il fornitore.

3. OQ-3 — Avvio del calcolo Tips. Quando l’utente chiede un calcolo da una data all’altra, Tips verifica in RF-One che i dati coprano l’intero periodo richiesto. Se manca anche solo una parte, il calcolo non parte e una modale spiega che i dati disponibili non coprono tutto l’intervallo. Il controllo di copertura sostituisce il controllo separato di consolidamento per l’avvio del calcolo. Questa decisione riguarda il calcolo. Qualunque modifica alle condizioni di pagamento richiede una decisione separata.

4. OQ-4 — Acquisizione multisede. Un solo servizio controlla le sedi in parallelo. Ciascuna sede mantiene le proprie credenziali, i propri identificativi e il proprio punto di ripresa. Se una sede si blocca, le altre continuano. La sede bloccata riparte dal proprio ultimo salvataggio valido.

5. OQ-5 — Invio ordini da MyRF. RF-One registra subito l’ordine come in attesa e lo invia al POS tramite il connettore. Se l’esito è incerto, RF-One lo verifica prima di un eventuale reinvio, per evitare ordini duplicati. Tieni distinti invio, ricezione da parte del POS e inoltro in cucina. Il futuro RF POS usa gli stessi contratti RF-One. Segnala le capacità di Clover ancora da verificare.

6. OQ-6 — Arricchitori Bank. Gli arricchitori scrivono solo nel campo dedicato, chiamato `enrichment_note` nell’implementazione RFBank verificata. La descrizione importata va conservata esattamente com’è arrivata dalla banca. Nessun processo, compresi importazioni successive e ricaricamenti, può sovrascriverla, ripulirla, normalizzarla o aggiungervi testo. Il Memo bancario originale resta separato dall’arricchimento. WHO e WHY leggono i campi canonici del movimento. Le tabelle sorgente e degli arricchitori servono all’importazione e all’abbinamento. Distingui il campo già verificato in RFBank dalla sua eventuale adozione nel Data Store principale.

7. OQ-7 — Ruoli Tips. Fa fede l’Anagrafica RF-One, con il ruolo valido per la persona, la sede e la data del lavoro. I ruoli importati restano solo come evidenza storica. L’identificativo esterno può collegare il dipendente alla persona RF-One. Il ruolo importato non entra nel calcolo, neppure se manca un’assegnazione in Anagrafica.

8. OQ-8 — Flusso primario di Tips e Compensation. Prima si definiscono il flusso principale dei due moduli e i contratti dei dati e dei connettori che servono a quel flusso. La pulizia dei vecchi percorsi viene dopo. Documenta questa priorità e i contratti da preparare prima dell’implementazione. Il disegno del flusso e le scelte funzionali ancora mancanti spettano a noi.

9. OQ-9 — Scelte di Claude. Claude decide i dettagli tecnici che rispettano la specifica approvata. Se deve cambiare flusso, schema, API o comportamento, si ferma e chiede a noi. Allinea a questa regola le istruzioni di sviluppo, compreso il passaggio MIEAF.

10. OQ-10 — Esempi nel Core. Aggiorna solo le frasi interessate nei documenti 16 e 17. Chiarisci che Cognito legge i dati operativi RF-One, oggi alimentati dal connettore Clover. Mantieni il significato degli esempi e il resto dei testi approvati.

11. OQ-11 — Lavoro locale. Usa la copia di lavoro separata e preserva le modifiche già presenti nella copia principale. Verifica le versioni locali delle istruzioni pertinenti, in particolare `CLAUDE.md`, `How Works Standard.md`, `UI Rules.md` e `LOCAL_ENVIRONMENT.md`. Assicurati che le regole più recenti sull’aiuto contestuale e sul database locale siano rispettate nella documentazione che prepari. Lascia il lavoro locale estraneo fuori dal diff.
