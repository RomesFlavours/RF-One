# REPORT

## 1. Esito

La tabella fornita dall'utente è stata applicata al master AWS utilizzando esclusivamente il codice Clover esatto. I dati forniti dall'utente sono conservati come evidenza manuale distinta dalle risposte API Clover.

| Riscontro | Esito |
| --- | ---: |
| Righe ricevute | 36 |
| Codici unici | 35 |
| Ripetizioni identiche accorpate | 1 |
| Anagrafiche già presenti corrispondenti | 9 |
| Nomi mancanti completati su identità esistenti | 5 |
| Ulteriori anagrafiche storiche aggiunte | 26 |
| Identità dipendente totali dopo l'intervento | 63 |
| Identità duplicate per codice Clover | 0 |
| Nomi ancora sconosciuti con timbrature | 2 |

I cinque nomi sono stati aggiunti alle righe dipendente già collegate alle timbrature, senza cambiarne l'identificativo RF-One. I 26 ulteriori profili conservano il nome e il codice forniti: non vengono presentati come profili API verificati né marcati automaticamente disponibili o indisponibili su Clover.

## 2. Identità completate e residue

Completati i nomi delle identità `70TJB5368SHKY`, `58D46DV5CJAQT`, `MG51TH4QAPKQ4`, `75M0CNV777VYR`, `X4HHDPE1WYGY2`. I nomi sono conservati nel database e nella fonte privata; non vengono riprodotti nel rapporto versionabile.

Gli identificativi `W8MEV8C062PHG` e `FBT1TZP87Y4S8` non compaiono nell'elenco ricevuto e restano senza nome. Le loro timbrature e identità sono preservate.

## 3. Normalizzazione e limiti della fonte

La ripetizione identica di `GYA28CNZ63EM0` è stata accorpata. La riga di `P3QH46KN81C5C` era spostata fra colonne: sono stati utilizzati soltanto codice e nome riconoscibili. Gli altri valori ambigui sono documentati in una nota della fonte e non assegnati automaticamente a campi del database.

Ruoli, aree, date e tariffe sono conservati come valori forniti dall'utente. Non sono stati trasformati in ruoli storici con intervalli inventati, date di assunzione o cessazione, condizioni retributive o dati restituiti da Clover. Il valore `########` rimane un contenuto non leggibile della fonte, non un importo.

Tre date indicate sono successive alla prima timbratura già presente:

| Codice Clover | Data indicata | Prima timbratura, data locale New York |
| --- | --- | --- |
| `75M0CNV777VYR` | 1 luglio 2026 | 25 giugno 2026 |
| `X4HHDPE1WYGY2` | 19 luglio 2026 | 3 luglio 2026 |
| `M5M2XEB3CDSPE` | 23 agosto 2026 | 19 agosto 2026 |

Nessuna timbratura è stata esclusa in base a queste date. La colonna ricevuta non viene automaticamente dichiarata una data contrattuale verificata. Per utilizzare operativamente i ruoli nella ricostruzione delle tip occorre stabilire la loro validità storica.

## 4. Integrità e verifiche

Prima del commit sono stati confrontati gli identificativi e i collegamenti delle timbrature e gli hash/conteggi di tutte le tabelle tip del baseline: identici. Bank non è stato aperto in scrittura. Nessuna tip è stata ricalcolata; nessuna tariffa, assegnazione temporale o anagrafica già nominata è stata sovrascritta.

Una verifica indipendente dopo il commit ha confermato tutti i 35 abbinamenti codice/nome, 35 osservazioni documentali distinte, zero codici duplicati e due sole identità con timbrature ancora senza nome. Il nuovo documento è riconosciuto tramite SHA256: una seconda applicazione identica viene fermata prima di scrivere nuovamente l'evidenza.

## 5. Riferimenti

- `output/clover_user_employee_roster_20261019.json`: audit aggregato senza nomi, codici completati, anomalie e controlli di integrità.
- Run documentale `116041`, modalità `EMPLOYEE_EVIDENCE`, risorsa `employee_user_roster`: provenienza utente esplicita, distinta da una sincronizzazione API. Nessuna copertura temporale di scaricamento viene attribuita a questo run.
- `source_records`, tipo `employee_user_roster`: 35 osservazioni con fonte, codice, dati forniti, note di normalizzazione e impronta del documento.
- SHA256 della fonte normalizzata: `366bdbeaeec87d41250c3905fef24d552ac22abb6a7afb8e198bf34b102b5a65`.
- `tmp/employee_roster_user_20261019.json`: fonte privata con dati personali, esclusa da Git tramite regola specifica.
- `tmp/apply_user_employee_roster.py`: confronto preparatorio in sola lettura e applicazione esplicita.
- `tmp/verify_user_employee_roster.py`: verifica indipendente successiva al commit.

I dati originali restano conservati. Non sono stati eseguiti deploy, cancellazioni o nuovi backup Bank.
