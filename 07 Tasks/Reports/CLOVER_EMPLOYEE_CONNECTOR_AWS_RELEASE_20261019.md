# REPORT

## 1. Esito

Il connettore Clover aggiornato è pubblicato e attivo su AWS dal 19 ottobre 2026. Il servizio continuo è stabile, con un solo processo sulla nuova revisione e nessun runtime Clover precedente ancora in esecuzione. Anche i prossimi lavori di importazione useranno l'immagine verificata.

La protezione conserva identità e dati anagrafici conosciuti quando Clover non restituisce più un dipendente o invia un riferimento parziale. La reperibilità del profilo resta distinta dallo stato lavorativo. Non sono stati cancellati account reali su Clover per provare il comportamento: i casi di cancellazione/404 sono stati simulati nei test isolati dentro l'immagine effettivamente pubblicata.

## 2. Rilascio eseguito

| Componente | Risultato |
| --- | --- |
| Immagine | `rfone-tips:clover-employees-20261019T113315Z` |
| Digest immutabile | `sha256:4bf22dc069c3f27fa8cf4d5c9393f20bfe16fe3d1df2129e1bd3da130f67e7bd` |
| Lavori Clover | `rfone-clover-acquisition-job:2` |
| Servizio continuo | `rfone-clover-correction-sync:2`, rollout COMPLETED |
| Processo attivo verificato | `54927add940549b3b565fd131d46943b` |
| Build | `rfone-tips-build:cedd3aca-8128-405c-9580-e50ed52b1818`, SUCCEEDED |

Il pacchetto parte dal sorgente già distribuito, con un overlay limitato a quattro moduli Clover e ai tre campi ORM necessari, già presenti nel database: due per reperibilità dipendenti e uno per le righe storiche degli ordini. Non è stato pubblicato il resto delle modifiche locali al modello dati o alle applicazioni. Aggiunti manifest e verifiche del rilascio. Il sorgente S3 ordinario è stato aggiornato mantenendo la ricetta di build standard; il sorgente precedente è conservato.

L'interfaccia RF-One Web usa la famiglia del task senza fissare la vecchia revisione: i prossimi lavori risolveranno la revisione 2. I servizi App Runner delle interfacce non sono stati riavviati; l'acquisizione Clover viene eseguita nei task ECS aggiornati, non in quelle interfacce.

## 3. Verifica sul codice effettivamente attivo

Dieci test sono passati prima nel pacchetto preparato, poi in un task AWS isolato sulla nuova immagine e infine all'avvio del processo continuo realmente in esecuzione. Il controllo confronta gli SHA256 dei file con il manifest del rilascio, per evitare di certificare soltanto il sorgente locale.

Fra i casi verificati: profilo omesso dalla collezione con GET404 conserva identificativo, nome noto e stato lavorativo; riferimenti vuoti o parziali non svuotano i dati nei due importatori; nuovi dati documentati aggiornano la stessa identità. I controlli di integrità leggono il master in modalità sola lettura.

Il runtime attivo ha confermato 37 anagrafiche, 28 profili disponibili e nove storici non raggiungibili, di cui due con nome già conosciuto; zero timbrature prive di anagrafica collegata. I sette nomi storici sconosciuti restano irrisolti e non sono stati inventati.

Dopo il rilascio sono ripresi i cicli ordinari: run 115985 e 115989 COMPLETE, senza errore. Il servizio continua il proprio normale aggiornamento dei dati sorgente Clover; non è stato avviato un nuovo scaricamento storico per effettuare la verifica.

## 4. Integrità e criteri di successo

| Criterio | Esito |
| --- | --- |
| Nuovo codice sul processo Clover attivo | Verificato tramite digest e manifest |
| Prossimi lavori collegati all'immagine corretta | Verificato sulla revisione della famiglia ECS |
| Test di protezione eseguiti nel runtime attivo | 10 passati |
| Runtime Clover precedenti ancora attivi | Nessuno |
| Hash e conteggi delle 11 tabelle tip prima/dopo | Identici |
| Campi anagrafici prima/dopo | Identici |
| File Bank locale prima/dopo | SHA256 identico |
| Scritture Bank, ricalcolo tip, migrazioni DB | Nessuno |

## 5. Riferimenti e ripristino

- `tmp/employee_connector_release/release.json`: manifest, digest, task, verifica runtime, build e indirizzi del sorgente conservato.
- `tmp/employee_connector_release/integrity_before.json` e `integrity_after.json`: hash e conteggi di integrità, senza nomi in chiaro.
- `tmp/employee_connector_release/normal_cycles.json`: ripresa dei cicli e assenza di runtime precedenti.
- `tmp/employee_connector_release/previous-source.zip` e `published-source.zip`: pacchetto precedente e pubblicato.
- Backup AWS del sorgente: `s3://rfone-tips-deploy-418674484214/backups/employee-connector/clover-employees-20261019T113315Z/source.zip`.
- Log del processo attivo: gruppo `/ecs/rfone-clover-correction-sync`, stream `poller/clover-correction-sync/54927add940549b3b565fd131d46943b`.
- Definizioni versionate: `03 Software/Infrastructure/deploy/clover-acquisition-job/task-definition.json` e `clover-correction-sync/task-definition.json`.
- Rapporto precedente: `CLOVER_EMPLOYEE_HISTORY_20261019.md`. Il limite allora indicato, codice non ancora pubblicato, è superato da questo rilascio.

Per un ripristino tecnico restano le revisioni 1 delle due famiglie ECS e il sorgente precedente. Ripristinare il codice precedente rimuoverebbe anche la nuova protezione: non è stato eseguito alcun ripristino né alcuna operazione sui dati storici.
