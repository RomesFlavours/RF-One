# REPORT

## 1. Esito e perimetro

Il master Clover su AWS è stato aggiornato e il confronto degli input acquisiti con la fonte è passato: **VERIFIED, zero discrepanze residue**. La verifica riguarda il merchant **PYQYB7SKB6V31**, Rome’s Flavours Winter Park, dal **1 gennaio 2026 alle 00:00 EST al 5 ottobre 2026 alle 04:00 EDT escluso**. Include i primi quattro giorni di ottobre per chiudere la settimana iniziata il 28 settembre.

| Input confrontato con Clover | Record verificati | Esito |
| --- | ---: | --- |
| Pagamenti: identificativi, importi, esito, ordine, dipendente, mance e tasse riportate dalla fonte | 13.204 | Corrispondenti |
| Rimborsi: identificativi e importi | 4 | Corrispondenti |
| Timbrature: identificativi, dipendente, entrata, uscita e correzioni | 3.186 | Corrispondenti |
| Ordini referenziati dai pagamenti: proprietario, righe, prezzi, quantità e gratuity | 12.261 | Corrispondenti per i controlli eseguiti |

La copertura deriva dal confronto degli identificativi e dei valori delle collezioni paginate e dai dettagli degli ordini. La sola presenza di una prima e ultima data non è stata usata come prova di completezza; i giorni senza vendite non sono stati classificati automaticamente come mancanti.

## 2. Recupero eseguito su AWS

Gennaio–luglio erano già stati recuperati. Gli ultimi blocchi completati sono:

| Periodo | Run | Ordini elaborati | Pagamenti elaborati | Timbrature elaborate |
| --- | --- | ---: | ---: | ---: |
| Agosto | 113312 | 1.145 | 1.217 | 334 |
| Settembre | 113353 | 963 | 1.012 | 312 |
| 1–4 ottobre e chiusura alle 04:00 del 5 ottobre | 113383 | 258 | 277 | 67 |

Questi sono conteggi di elaborazione per blocco; non vanno sommati come se ogni ordine fosse necessariamente distinto tra richieste. La verifica finale ha confrontato le identità uniche. I mesi COMPLETE non sono stati rieseguiti alla ripresa e non sono stati duplicati run attivi.

## 3. Correzioni e storico conservato

Il connettore nel progetto suddivide le richieste storiche di pagamenti e rimborsi in finestre mensili e richiede che ogni paginazione termini correttamente. Risolve inoltre i riferimenti ai dipendenti storici senza inventare nomi quando Clover risponde 404.

La prima verifica completa ha rilevato 38 segnalazioni. La diagnosi ha distinto:

- 120 righe conservate su 33 ordini, non più presenti nella collezione corrente Clover. L'assenza di ciascuna riga è stata confermata anche con GET individuale 404. Nessuna riga corrente risultava mancante.
- Un pagamento storico con esito FAIL, conservato in AWS e non più restituito da Clover, anche tramite GET individuale 404. Rimane nello storico e non rappresenta un pagamento riuscito da recuperare.
- Quattro letture di dettagli temporaneamente non disponibili, successivamente riuscite.

Nessun record è stato cancellato. È stata aggiunta ad AWS la sola colonna nullable `order_items.source_present`; le 120 righe storiche confermate assenti sono marcate False. I valori e i collegamenti originari rimangono conservati. I conteggi fisici delle tabelle, pertanto, possono superare quelli della collezione corrente Clover. Per utilizzare le righe correnti occorre escludere `source_present = false`; NULL indica presenza non ancora classificata dal connettore e non è una prova di assenza.

Il connettore corretto aggiorna questa presenza dopo una lettura completa, riattiva le righe ritornate alla fonte e considera autorevole anche una collezione vuota. Una lettura fallita o parziale interrompe l'acquisizione e non marca righe come assenti. Rimosso il ripiego sul vecchio contenuto annidato quando la collezione dedicata è vuota.

Una seconda verifica integrale ha confermato i valori e le identità, con una sola lettura temporaneamente non disponibile. Il controllo completo di proprietario, righe, prezzi, quantità e gratuity di quell'ordine è stato ripetuto in sola lettura ed è passato. Il rapporto completo precedente è conservato e collegato mediante SHA256 al rapporto finale; la segnalazione non è stata ignorata.

## 4. Cosa è utilizzabile e cosa resta da chiarire

Gli input verificati sono disponibili sul master AWS per preparare la ricostruzione delle tip fino a settembre, includendo la settimana conclusa il 4 ottobre. **Le tip non sono state ricalcolate o sovrascritte.**

Restano sette identità di dipendenti storici senza nome disponibile da Clover, che aveva risposto 404. Gli identificativi sono conservati; nessun nome o ruolo è stato inventato. Occorre risolvere le identità e le assegnazioni storiche dei ruoli necessari per distribuire correttamente le tip e collegarle ai destinatari Zelle. I ruoli correnti Clover non provano il ruolo svolto in ogni giorno del passato.

Non sono certificati come completi: tasse derivate delle righe, sconti di riga non ancora acquisiti dall'importatore, cronologia dei ruoli e versioni storiche del catalogo. Il confronto delle tasse copre il valore riportato sui pagamenti, non una certificazione di tutte le tasse storiche ricostruite.

Nel perimetro verificato non risultano ulteriori input correnti mancanti da scaricare. Il passo successivo è risolvere identità e ruoli storici, poi predisporre una ricostruzione verificabile delle tip e il confronto con le causali Zelle. Tale lavoro non è stato eseguito in questa fase.

## 5. Integrità e limiti operativi

| Criterio | Esito |
| --- | --- |
| Verifica Clover finale passata, issue_count = 0 | Passato |
| Hash e conteggi di tutte le tabelle tip confrontati con il baseline conservato | Identici |
| Scritture Bank da questo workflow | Nessuna |
| File Bank fisicamente identico al checksum iniziale | No: variazione registrata, causa non accertata |
| Copia del master Clover nel database locale in questa fase | Non eseguita |
| Pubblicazione di nuovi container o riavvio dei servizi AWS | Non eseguiti |

Il file Bank era in uso e il suo checksum è cambiato durante il recupero. Questo workflow lo ha soltanto letto per l'audit e non ha aperto connessioni scrivibili a Bank. Il checksum iniziale è conservato: non viene dichiarata un'identità byte per byte e non viene attribuita la variazione a una causa non dimostrata.

La correzione del connettore è nel progetto ed è stata eseguita dal processo locale di recupero contro AWS. I container dei servizi AWS non sono stati aggiornati. La sola colonna additiva necessaria è stata applicata sullo schema AWS esistente, senza eseguire migrazioni estranee e senza avanzare la revisione Alembic `c8e4b2a6f0d1`. La migrazione di progetto `b9e620261019` riconosce la colonna già presente quando verrà applicata la normale catena di migrazioni. Le letture future devono rispettare il marcatore delle righe storiche.

## 6. Test ed evidenze

Test passati dopo la correzione: 6 regressioni per finestre mensili, identità e conservazione delle righe; 40 controlli di sicurezza acquisizione; 59 controlli acquisizione. I test hanno usato database temporanei, senza modificare Bank o le tip operative.

Riferimenti nel progetto:

- `output/aws_clover_master_verification_20261018.json`: esito finale, periodi, conteggi, storico escluso e controllo mirato risolutivo.
- `output/aws_clover_master_verification_20261019_before_transient_retry.json`: seconda verifica completa prima del controllo mirato.
- `output/aws_clover_master_verification_20261018_initial_mismatches.json`: prima verifica completa con le 38 segnalazioni originarie.
- `output/clover_line_presence_reconciliation_20261019.json`: 120 assenze individualmente confermate, zero cancellazioni, controllo tip e revisione schema.
- `output/aws_clover_master_diagnostics_20261019.json`: diagnosi mirata degli scostamenti iniziali.
- `tmp/aws_clover_master_recovery_20261018.json`: run, eventi, baseline e fingerprint finali delle tip, osservazioni Bank.
- `tmp/clover_year_backfill_audit.json`: baseline originale conservato.
- `tmp/recover_aws_clover_master.py`, `tmp/verify_aws_clover_master.py`, `tmp/finalize_clover_source_verification.py`: esecuzione e verifica.
- `03 Software/RF-One Data Store/rfone_data_store/technical/connectors/clover/acquisition.py` e `historical_backfill_detail.py`: correzioni del connettore.
- `03 Software/RF-One Data Store/migrations/versions/b9e620261019_clover_order_line_presence.py`: modifica additiva dello schema.
- `03 Software/RF-One Data Store/test_clover_line_presence.py`, `test_clover_monthly_recovery.py`, `test_clover_acquisition_safety.py`, `test_clover_acquisition.py`: test.

Gli audit e le segnalazioni precedenti sono conservati. Non è stata prodotta una nuova copia locale del master o un nuovo backup manuale Bank.
