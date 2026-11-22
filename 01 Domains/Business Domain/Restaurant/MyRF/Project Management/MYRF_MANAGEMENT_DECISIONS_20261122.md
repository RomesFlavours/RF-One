# MyRF / Management — Consolidamento funzionale delle decisioni
**Data:** 2026-11-22  
**Stato:** decisioni funzionali del Product Owner ricostruite dalle conversazioni successive al 21 ottobre; **non** certifica implementazione, deploy o copertura dei test.  
**Relazione:** integra, senza cancellare, la specifica minima del Project Management approvata il 12 ottobre (`README.md`).

## 1. Finalità
MyRF deve far risparmiare tempo nel pianificare, eseguire e verificare il lavoro. Il governo è centrato su responsabilità, impegni verificabili, eccezioni e risultati; non su una proliferazione di pagine e promemoria.

## 2. Ambiti condivisi
- **People:** raccolta strutturata di esperienze e autovalutazioni tramite intervista; valutazioni di manager e colleghi, con identità dell'autore conosciuta al sistema anche quando le risposte sono anonime per il valutato. Non inventare dati assenti.
- **Organization:** processi e responsabilità, titolare dell'attività, backup, regole di escalation e Management Control. Le proposte AI non equivalgono a decisioni approvate. Esiste una gerarchia di autorizzazioni e le responsabilità non vanno ricostruite arbitrariamente dal codice.
- **Project Manager:** definizione di progetto, piano, attribuzione e accettazione dell'incarico, attenzione alle scadenze, decision log, brief e verifica di outcome.

## 3. Unità di impegno
Ogni incarico operativo deve poter esprimere:
- risultato atteso;
- owner/responsabile unico e backup quando necessario;
- data di scadenza e checkpoint;
- valore/effetto atteso e criterio di verifica;
- dipendenze;
- risultato osservato e motivazione delle deviazioni.

Un impedimento segnalato **prima della scadenza** è trattato diversamente da un incarico semplicemente non completato: l'escalation deve portare il problema all'attenzione della persona competente, non nasconderlo in un indicatore aggregato.

## 4. Decision log e apprendimento
Una decisione rilevante (spesa, cambiamento operativo, tema fra aree) deve conservare autore, data, razionale, risultato atteso, data di verifica e risultato reale. Il sistema può proporre revisioni a 30 giorni e riepiloghi quotidiani; frequenza/attivazione sono configurazioni, non nuove decisioni automatiche.

## 5. Governance delle persone
Il Product Owner mantiene il potere di approvazione. La configurazione organizzativa deve supportare responsabilità laterali, ruoli di controllo e backup; non assumere che una vecchia etichetta `GM` implichi sempre autorità su tutte le aree. L'escalation segue il percorso collega → responsabili coinvolti → owner secondo l'organizzazione approvata.

## 6. Primo perimetro MyRF
Il primo rilascio desiderato comprende: progetto, incarico/accettazione, feed di attenzione, decision log e brief quotidiani. La v1 storica con Gantt e progressi manuali rimane documentazione della vecchia implementazione, non prova che tutte queste funzioni esistano.

## 7. Punti ancora da verificare
Modello fisico delle responsabilità, ruoli e permessi, criteri di valutazione RFCore, integrazione del registro persone, email/brief, costi AI e confini di accesso. **Non inferire implementazione dalla presente specifica.**
