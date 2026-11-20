# REPORT

## 1. Decisione confermata dall'utente

Il 19 ottobre 2026 l'utente ha confermato che i due account storici ancora senza nome e assenti dall'elenco fornito erano trial e non devono essere considerati nel successivo lavoro su tip e pagamenti Zelle:

- `W8MEV8C062PHG`
- `FBT1TZP87Y4S8`

L'indicazione riguarda questi due identificativi. Non è una regola automatica per classificare come trial qualsiasi dipendente presente o futuro non incluso nell'elenco storico.

## 2. Applicazione e integrità

Decisione conservata sul master AWS come evidenza utente `employee_user_classification`, separata dalle informazioni restituite da Clover. Nelle prossime ricostruzioni storiche delle tip e confronti Zelle questi due identificativi vanno esclusi e non richiedono ulteriore ricerca del nome.

Anagrafiche e timbrature originali restano conservate con i collegamenti esistenti. Non sono stati modificati lo stato lavorativo canonico, le assegnazioni, le tariffe o i risultati dei calcoli esistenti. Non è stato ricalcolato alcun dato e non viene dichiarato che i vecchi calcolatori siano stati aggiornati: questa è una decisione vincolante da applicare nella successiva ricostruzione.

Confrontati hash delle tabelle tip e collegamenti delle timbrature prima e dopo: invariati. Bank non è stato aperto in scrittura. Registrazione idempotente mediante SHA256 della decisione.

## 3. Riferimenti

- `output/clover_employee_trial_exclusions_20261019.json`: decisione, identificativi, run documentale e controllo di integrità.
- AWS `source_records`, tipo `employee_user_classification`: due osservazioni di provenienza utente.
- `tmp/record_employee_trial_decision.py`: registrazione della decisione senza cancellare dati storici.
- `CLOVER_USER_EMPLOYEE_ROSTER_20261019.md`: elenco normalizzato e precedenti due identità irrisolte, ora classificate trial.
