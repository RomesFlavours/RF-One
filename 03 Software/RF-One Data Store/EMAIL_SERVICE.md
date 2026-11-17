# RF-One Email Service 1.0

Nota per il rilascio AWS: questa analisi descrive la baseline locale iniziale.
La ricognizione AWS successiva ha confermato il NAT e recuperato i componenti
Aruba/Selection già operativi. Il rilascio additivo, la revisione di produzione
`e9a120261117` e la procedura effettiva sono documentati in
`../Infrastructure/deploy/rfone-email/README.md` e nel relativo report di rilascio.

Stato: implementazione locale additiva, 17 novembre 2026. Nessun invio reale,
accesso AWS, deploy o cambiamento ai database di produzione effettuato.
I Domain esistenti non sono ancora migrati.

## 1. Analisi e architettura effettiva

La baseline esaminata è il commit `ec9c6c4`. In questo checkout non sono
presenti `account_email.py`, `smtp_email.py`, `selection_workspace_email_outbox`
o riferimenti al bridge RMAED. Non è quindi possibile dichiarare riutilizzata
o verificata la loro implementazione di retry e antiduplicazione. Occorre
confrontare questi componenti con la versione operativa prima della migrazione.

Procedure rilevate:

- `rfone_data_store/selection/communication_service.py`: rendering dei template,
  invio tramite `communication_providers.get_email_provider()`, registrazione
  del risultato nella comunicazione Selection. Il provider di default è
  `MockEmailProvider`, sincrono; non è la outbox descritta nella richiesta.
- `RF-One Web/app.py`: `_issue_and_send_code` e notifica cambio password chiamano
  `technical/ses_email.py`. Sono flussi preesistenti, da sostituire nella fase
  MyRF; il nuovo servizio non importa né utilizza SES. La centralizzazione di
  tutti gli invii non è completa finché questi chiamanti non sono migrati.
- Training non contiene un trasporto email autonomo; la pagina creazione
  studente indica la condivisione diretta delle credenziali. L'integrazione
  account è in `RF-One Web/training_integration.py`.
- `InvoiceIntake/mailbox_acquisition` acquisisce posta Aruba via IMAP: è un
  flusso in ingresso, non un invio da migrare nella coda.

Il percorso locale predefinito `data/rfone.db` non contiene un database in
questo worktree. Non sono stati risolti URL da `.env` né aperti database remoti.
Lo schema è stato esaminato nel codice e ricostruito tramite l'intera catena
Alembic in un database SQLite temporaneo.

La documentazione Infrastructure include una precedente assenza del NAT per
il connettore VPC Tips. Non dimostra lo stato attuale del NAT indicato dal
committente. Nessuna configurazione di rete è stata cambiata.

Architettura realizzata:

```text
Domain → API Python transazionale / API HTTP RF-One
                      ↓
           database RF-One: email_requests
                      ↓
         worker autonomo con lease DB globale
                      ↓
            Aruba SMTP TLS → destinatario

Administration → Email Control → coda, tentativi, audit, heartbeat
```

Non occorrono SES, Redis, SQS o nuovi servizi database. L'API Python può
accodare nella stessa transazione dell'evento di business. Il chiamante
esegue commit/rollback. L'API HTTP esegue il commit prima della risposta 202.
La chiave di deduplicazione è unica nel Domain; la stessa chiave con un
payload diverso viene rifiutata. Il database gestisce le collisioni concorrenti.

Il worker acquisisce atomicamente una lease globale di 300 secondi prima
di cercare messaggi; serializza tutti i worker e applica un intervallo globale
persistente, predefinito di 2 secondi. Esegue I/O SMTP fuori dalla transazione.
La proprietà della lease viene ricontrollata prima di registrare il risultato.
Un processo precedente non può sovrascrivere il recupero di un nuovo worker.

Stati: QUEUED, SENDING, RETRY, ACCEPTED, FAILED, UNCERTAIN, CANCELLED.
Un 4xx SMTP esplicito comporta retry esponenziale da 30 secondi, massimo 5
tentativi complessivi. Un 5xx comporta FAILED. Un'interruzione durante DATA
o un SENDING abbandonato comporta UNCERTAIN, escluso dal reinvio automatico
e manuale. L'operatore deve riconciliare l'esito con Aruba prima di autorizzare
un nuovo evento con una nuova chiave. Non si promette exactly-once SMTP.

ACCEPTED significa accettato dal server SMTP. Non significa consegnato al
destinatario; non è stato implementato un sistema bounce/DSN.

## 2. File creati e modificati

Percorsi relativi a `03 Software`:

Creati:

- `RF-One Data Store/rfone_data_store/email_service.py`
- `RF-One Data Store/rfone_data_store/email_worker.py`
- `RF-One Data Store/rfone_data_store/technical/aruba_smtp.py`
- `RF-One Data Store/migrations/versions/c7e5a3b9d201_shared_email_service.py`
- `RF-One Data Store/EMAIL_SERVICE.md`
- `RF-One Web/email_routes.py`
- `RF-One Web/templates/email_control.html`
- `RF-One Web/templates/email_detail.html`
- `RF-One Web/tests/test_email_service.py`

Modificati:

- `RF-One Data Store/migrations/env.py`: registra i modelli per il confronto Alembic.
- `RF-One Web/app.py`: registra le nuove route, senza scritture all'avvio.
- `RF-One Web/templates/home.html`: collega Email Control in Administration per gli amministratori.

## 3. Componenti riutilizzati

SQLAlchemy `Base`, engine/session factory RF-One, Alembic, account e revoca
sessione `rfone_web_session`, autorizzazioni `RFOneAccountDomainAccess`,
CSRF RF-One, template `base.html`, CSS e formattatore dei timestamp condivisi.
Il client Secrets Manager segue la catena di credenziali boto3 già utilizzata
nel repository; il parsing del segreto SMTP resta separato dall'helper RDS.
Non viene creata una seconda autenticazione.

## 4. Tabelle e migrazione

Revisione Alembic `c7e5a3b9d201`, successiva a `b6e4d2a8c1f9`:

| Tabella | Contenuto |
| --- | --- |
| email_requests | UUID, Domain, destinatario, oggetto, testo, evento, chiave/hash antiduplicazione, stato, tentativi, date, errore sanificato |
| email_attempts | Numero tentativo, inizio/fine, esito ed errore; unicità richiesta/numero |
| email_audit | Richiesta, account RF-One, operazione amministrativa e timestamp |
| email_worker_state | Singleton con proprietario lease, scadenza, heartbeat, prossimo slot e modalità |

Nessuna modifica a tabelle dei Domain esistenti. Il downgrade elimina queste
quattro tabelle: usarlo soltanto in ambiente di prova o dopo backup e
riconciliazione. Per un rollback operativo conservare coda e audit.

## 5. API per i Domain e autorizzazioni

API Python interna, per codice server RF-One attendibile:

```python
from rfone_data_store import email_service

with SessionFactory.begin() as db:
    email = email_service.enqueue(
        db, domain="TRAINING", recipient="recipient@example.test",
        subject="Example", body="Message", event="training.assignment:123",
        dedup_key="assignment:123:notification:v1",
    )
```

Il Domain deve usare il proprio codice del registro RF-One e una chiave
stabile derivata dall'evento, non generarne una nuova a ogni retry HTTP.
La libreria interna non costituisce un confine di sicurezza per codice
server non attendibile: i controlli di accesso esterni sono nelle route HTTP.

| Metodo e percorso | Operazione |
| --- | --- |
| POST /api/email/{domain}/requests | Accoda: recipient, subject, body, event, dedup_key; risposta 202 |
| GET /api/email/{domain}/requests | Cronologia, fino a 100 righe, offset |
| GET /api/email/{domain}/requests/{id} | Stato e dettaglio tentativi |
| POST /api/email/{domain}/requests/{id}/cancel | Annulla QUEUED o RETRY |
| POST /api/email/{domain}/requests/{id}/resend | Reinvio di FAILED, soltanto amministratore con accesso al Domain |
| GET /administration/email | Dashboard e ricerca globale per amministratori |
| GET/POST /administration/email/{domain}/{id} | Dettaglio e operazioni amministrative |

Filtri: domain (solo pannello globale), recipient, status, start, end, offset.
Date UTC, estremo finale esclusivo. Gli orari mostrati usano il formattatore
RF-One. Le risposte non includono il corpo del messaggio.
Le route richiedono un account ACTIVE con sessione RF-One valida; l'API
Domain richiede la relativa abilitazione. Non basta essere amministratore
per usare un endpoint Domain senza relativa assegnazione. Il pannello
globale richiede is_admin. Le modifiche JSON richiedono X-CSRF-Token;
i form usano csrf_token. Reinvii e annullamenti registrano l'account nell'audit.
Non sono introdotti token statici o account macchina: per processi interni
senza sessione usare la libreria transazionale.

## 6. Test locali

Comando, dalla radice del repository:

```powershell
python '03 Software/RF-One Web/tests/test_email_service.py'
```

Suite dedicata: 20 test superati. Accodamento, accettazione SMTP simulata, cronologia,
deduplicazione e conflitto payload, concorrenza fra accodamenti e worker,
isolamento e uso simultaneo di Training/Selection, rate limit persistente,
errori 451/550, retry e relativo esaurimento, ripartenza, crash durante invio,
esiti incerti bloccati, annullamento, reinvio autorizzato con audit,
CSRF JSON, revoca sessione, autorizzazioni, rendering delle pagine,
validazione date, header injection, sanificazione errori e CLI dry-run.

Verificata inoltre l'intera migrazione da database SQLite vuoto alla nuova
head; risultano presenti tutte e quattro le tabelle email.
Regressioni RF-One: accounts/domain HTTP 38 controlli superati;
startup senza migrazioni/scritture 4 controlli superati.

Non eseguiti: connessione reale Aruba via NAT, autenticazione Aruba, invii
reali, test su PostgreSQL/AWS. Nessuno di questi esiti viene assunto dai mock.

## 7. Limiti

Solo testo semplice, un destinatario per richiesta, nessun allegato o template
centralizzato. I template restano nei Domain. Un worker attivo per mittente
centralizzato: si preferisce semplicità al parallelismo SMTP. Il limite Aruba
effettivo deve essere confermato; 2 secondi è un'impostazione iniziale RF-One,
non una quota garantita dal provider. Le credenziali vengono caricate
all'avvio: per la rotazione riavviare ordinatamente il worker.

L'heartbeat è registrato fra i messaggi; durante SMTP il pannello considera
valida la lease. Un arresto improvviso può apparire operativo fino alla sua
scadenza (massimo 300 secondi). Il recupero è conservativo anche se il crash
avviene prima della connessione. La libreria e le migrazioni supportano
SQLite/PostgreSQL; il comportamento PostgreSQL deve essere validato su staging.

Il corpo è persistito perché necessario all'invio: applicare accessi DB
ristretti, cifratura e una politica di conservazione prima della produzione.
Nessun contenuto, password o risposta libera SMTP viene scritto nei log
del servizio. Configurare anche gli access log HTTP senza query string,
header o corpo: i filtri possono contenere indirizzi email.

## 8. Procedura proposta per AWS

Da eseguire solo dopo autorizzazione esplicita, senza cambiare Wix o DNS:

1. Confrontare questo checkout con quello operativo: recuperare outbox
   Selection, moduli email e dipendenze RMAED prima di sostituirli.
2. Scegliere un host/process manager già esistente con accesso al database
   RF-One, al NAT già configurato e a Secrets Manager. Non eseguire il worker
   nel processo web o affidarsi alla permanenza di una sessione utente.
   Se manca un host adatto, sottoporre la scelta di compute prima di crearne uno.
3. Creare/configurare un segreto Secrets Manager dedicato e concedere
   GetSecretValue esclusivamente al ruolo del worker per quel segreto.
   Non assegnarlo ai ruoli dei Domain o al processo web. Schema del segreto:

   ```json
   {"host":"smtps.aruba.it","port":465,"username":"<mailbox>","password":"<secret>","from_address":"<approved sender>"}
   ```

   TLS con verifica del certificato obbligatoria. Host e porta sono quelli
   della [guida ufficiale Aruba](https://guide.aruba.it/hosting-e-domini/email/configurazione-posta/parametri-configurazione-posta).
4. Verificare route/subnet/security group e uscita TLS 465 attraverso il NAT
   esistente. Prima provare handshake senza MAIL/RCPT/DATA; un invio di prova
   richiede ulteriore autorizzazione esplicita e destinatario concordato.
5. Eseguire backup DB e validare upgrade/downgrade in staging PostgreSQL.
   Poi, soltanto con autorizzazione, applicare `alembic upgrade head` una volta
   dalla directory Data Store e distribuire API/pannello. L'avvio web non migra.
6. Impostare RFONE_EMAIL_SMTP_SECRET_ID e AWS_REGION nel solo worker.
   Impostare l'URL DB come configurazione protetta; non stamparlo né inserirlo
   in script versionati. Usare RFONE_DATABASE_URL nell'ambiente protetto
   del processo, così la password DB non compare negli argomenti del processo.
   Il CLI accetta anche --database-url per SQLite locale, senza mai leggere `.env`.
7. Avviare prima `python -m rfone_data_store.email_worker --database-url <local-test-url> --once`
   sul DB di prova: senza --send verifica la raggiungibilità senza consumare
   messaggi. Per l'esecuzione autorizzata aggiungere --send e rimuovere --once;
   configurare restart del processo e log senza dati sensibili. SIGTERM
   completa il messaggio corrente prima dell'arresto.
8. Confermare quota, mittente e autorizzazione all'invio; eseguire un canary
   autorizzato, osservare ACCEPTED separatamente dalla consegna effettiva.

## 9. Migrazione e rollback per Domain

Ordine vincolante: Training → Selection → MyRF → altri Domain.
Usare per ogni Domain un selettore di trasporto, introdotto con il relativo
adattatore; questi selettori non sono ancora implementati nei chiamanti.

| Domain | Migrazione proposta | Rollback |
| --- | --- | --- |
| Training | Collegare gli eventi reali di notifica e i flussi account al metodo enqueue; chiave evento stabile, commit con il business | Ripristinare precedente gestione dell'evento; annullare soltanto QUEUED/RETRY del Domain e conservare esiti e audit |
| Selection | Confrontare outbox operativa e dedup; adattare il provider senza trasformare QUEUED in consegna; drenare o importare una volta le richieste pendenti con mapping ID | Ripristinare provider precedente soltanto dopo riconciliazione fra outbox e coda centrale; nessun doppio consumer sullo stesso evento |
| MyRF | Sostituire i due chiamanti SES; coordinare scadenza codici e ritardi in coda, annullando notifiche con codici scaduti | Ripristinare release/configurazione precedente soltanto con scelta esplicita del trasporto conforme; non riattivare automaticamente SES |
| Altri | Adattare un Domain alla volta, con canary e stessa chiave per retry dello stesso evento | Disabilitare nuovo routing del singolo Domain; riconciliare le richieste ancora pendenti prima di riattivare il vecchio consumer |

Per ogni passaggio: fermare il vecchio consumer per gli eventi trasferiti,
verificare coda e chiavi, eseguire canary autorizzato, controllare audit,
errori e tempi di attesa. ACCEPTED e UNCERTAIN non vanno mai reinviati durante
rollback. Non eliminare tabelle o audit per tornare al vecchio routing.
Rimuovere RMAED soltanto dopo inventario dei suoi chiamanti, migrazione
completa, assenza di richieste pendenti e verifica end-to-end autorizzata;
conservare fino ad allora una release ripristinabile.

## 10. Decisioni ancora necessarie

- Individuare la versione operativa che contiene i componenti mancanti e le
  dipendenze RMAED; confermare percorso NAT e host esistente del worker.
- Confermare mittente Aruba, secret ID, quota e intervallo SMTP approvato.
- Definire conservazione dei corpi e degli indirizzi nel DB e nei backup.
- Definire gli eventi Training da notificare e il comportamento per codici
  MyRF scaduti mentre attendono in coda.
- Autorizzare separatamente test reali, deploy e migrazione di produzione.
