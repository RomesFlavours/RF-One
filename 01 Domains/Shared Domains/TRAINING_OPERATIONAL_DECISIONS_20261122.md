# Training — Decisioni operative sul percorso formativo e il registro persone
**Data:** 2026-11-22  
**Stato:** integrazione funzionale di `TRAINING_SERVICE_001.md`, senza cambiare autonomamente la tassonomia Domain e senza dichiarare un rilascio operativo.

## 1. Confine
Training è il servizio interno che governa percorsi, prove, evidenze e conferma di preparazione. Operational Knowledge conserva il patrimonio di contenuti riutilizzabili; la responsabilità funzionale rispetto ai contenuti del percorso è precisata nella specifica Training esistente. Non trasformare questa relazione in una ristrutturazione arbitraria di cartelle e Domain.

## 2. Corso Server
- Percorso originario definito in **15 unità**, con prerequisiti, evidenze, verifiche e prove pratiche.
- La regola operativa dei 120 secondi, le verifiche casuali e i contenuti specifici approvati appartengono al corso e non a un motore universale.
- Certificazione automatica finale disattivata nella configurazione discussa; la competenza a lavorare autonomamente richiede verifiche e approvazione del lead.
- Il tempo impiegato nella formazione è tempo retribuito secondo la configurazione del personale.

## 3. Accesso e inviti
- Trainee: accesso tramite link personale privato; lead tramite account RF-One e autorizzazioni.
- `Send to Training` in Selection avvia la registrazione/invito, riutilizzando la persona in Registry.
- Un invito inviato direttamente da Training deve creare o riutilizzare **la stessa identità**.
- Firma/attestazione del lead su verifiche pratiche, eventuali correzioni del tempo e autorizzazione a lavorare da soli: conservare autore, data e contenuto.

## 4. Conferma assunzione
- `Confirm Hire` disponibile dopo completamento delle unità, delle prove e della firma del lead; trainer conferma.
- Owner può autorizzare **Confirm anyway**, con motivo e audit di chi/quando.
- `Trainee` → `Employee` in Registry non equivale alla creazione automatica del record payroll, che resta separato.
- Il sistema non deve dichiarare assunto o pronto una persona sulla sola base di completamento tecnico del corso.

## 5. Didattica e valutazione
Il corso ibrido è progettato per usare AI in modo mirato, non invasivo. Prima unità discussa `A3 — The table's journey`. Misurazioni previste: reazione a situazione nuova, memoria a due settimane, osservazione del lead. Per sicurezza/allergie occorre validazione da responsabile designato; non inventare una certificazione non ancora approvata.

## 6. Verifiche aperte
Versioni finali dei contenuti, disponibilità del corso su AWS, permessi, gestione concorrenza AI, questionario e validazione sicurezza. Le copie di contenuto `Server Course` e `Management Course` nei branch software sono materiale di riferimento, non automaticamente un master approvato.
