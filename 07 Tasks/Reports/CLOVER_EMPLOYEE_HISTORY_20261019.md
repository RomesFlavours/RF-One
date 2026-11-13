# REPORT

## 1. Esito osservato

Il master AWS conserva 37 identità dipendente Clover. Il controllo del 19 ottobre ha trovato 28 profili correnti e nove non più raggiungibili, confermati con GET individuale 404. Non viene dedotta la cessazione del rapporto di lavoro o una data di cancellazione.

| Riscontro | Conteggio |
| --- | ---: |
| Profili disponibili | 28 |
| Profili non raggiungibili, conservati | 9 |
| Timbrature dei nove profili storici | 312 |
| Profili storici con dati già conosciuti e preservati | 2 |
| Identità storiche ancora senza nome documentato | 7 |
| Timbrature totali con collegamenti preservati | 3.325 |

I sette identificativi sconosciuti erano già collegati a 300 timbrature. Altri due profili oggi non disponibili conservano i dati già acquisiti e altri 12 collegamenti.

## 2. Ricostruzione documentale

Controllati 14 file selezionati degli archivi dipendenti, timbrature, ordini e pagamenti e cache dipendenti, oltre alle osservazioni employee/employee_reference e ai riferimenti dipendente delle timbrature già su AWS. La ricerca usa l'identificativo Clover esatto: nessun nome viene associato per somiglianza o ricavato da Zelle.

Non sono emersi nomi documentati per i sette account sconosciuti. Queste anagrafiche restano identità storiche valide con campi nullable. Per completare i nomi serve una fonte che colleghi esplicitamente identificativo e persona. Anche i ruoli storici non vengono inventati.

## 3. Soluzione implementata

Entrambi i percorsi di importazione, API e archivi, preservano i campi già conosciuti quando ricevono riferimenti parziali, vuoti o nulli. Un nuovo valore documentato può aggiornare lo stesso dipendente senza cambiare l'identità.

Il catalogo mantiene gli identificativi esistenti e verifica individualmente i profili scomparsi. Un GET404 conserva dettagli, ruoli e collegamenti e registra la mancata reperibilità. Errori diversi dal 404 non diventano false cancellazioni. Un riferimento storico mai visto conserva comunque il vero identificativo, senza inventare altri dati.

Aggiunte ad AWS le sole colonne nullable `employees.source_available` e `source_checked_at`, separate da `active`. Aggiornato il risultato di reperibilità dei 37 profili; nessuna anagrafica nota è stata svuotata e nessun record cancellato. La revisione Alembic preesistente resta invariata; la migrazione di progetto riconosce le colonne già presenti, senza applicare migrazioni estranee.

## 4. Verifiche e limiti

| Criterio | Risultato |
| --- | --- |
| Identità e collegamenti delle 3.325 timbrature preservati | Passato |
| Riferimenti parziali non svuotano dati noti nei due importatori | Test passato |
| Profilo omesso dal catalogo e GET404 conserva nome, ID e stato lavorativo | Test passato |
| Nuovo nome aggiorna la stessa identità | Test passato |
| Hash e conteggi delle tabelle tip prima e dopo | Identici |
| Scritture Bank o ricalcolo tip | Nessuno |
| Nuovi container AWS pubblicati | Nessuno |

Test passati: otto regressioni complessive di storia dipendente e recupero mensile, 40 controlli di sicurezza acquisizione e 59 controlli acquisizione, su database temporanei.

Il connettore corretto è nel progetto. **Perché la nuova protezione venga eseguita automaticamente dai servizi AWS serve pubblicare il codice aggiornato nei loro container**, che non sono stati sostituiti in questo intervento. Il master ha già le identità storiche e l'esito della verifica corrente. Non è stata aggiornata la copia locale Clover.

## 5. Evidenze e riferimenti

- `output/clover_employee_history_20261019.json`: audit applicato, identificativi non disponibili, nomi irrisolti e verifiche di integrità.
- `tmp/recover_employee_history.py`: preparazione e applicazione esplicita senza accesso scrivibile a Bank.
- `tmp/audit_historical_employees.py`: ricognizione delle identità con timbrature e nome mancante.
- `03 Software/RF-One Data Store/rfone_data_store/models.py`: attributi di reperibilità.
- `03 Software/RF-One Data Store/rfone_data_store/technical/connectors/clover/acquisition.py`, `ingest.py`, `mapping.py`: conservazione delle anagrafiche e riferimenti storici.
- `03 Software/RF-One Data Store/migrations/versions/d120261019ee_employee_source_availability.py`: migrazione additiva.
- `03 Software/RF-One Data Store/test_clover_employee_history.py`: regressioni.
- `tmp/employee_history_safety_test.log`, `tmp/employee_history_acquisition_test.log`: esiti dei controlli.

Archivi e dati originali conservati. Nessun nuovo backup manuale Bank.
