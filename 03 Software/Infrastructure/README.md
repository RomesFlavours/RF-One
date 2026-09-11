# Infrastructure

Local dev-environment tooling. This is **not RF-One product code** and not a Domain/Product/Core concept — it is operational scripting to make the developer/session environment usable (see `03 Software/README.md` "What belongs here": scripts and tooling).

---

## AWS dev access check/login

**Script:** [`aws-dev-access.ps1`](aws-dev-access.ps1)

**Comando unico da eseguire (PowerShell):**

```powershell
& "C:\Users\servi\OneDrive\AI-RF-ONE\RF One\03 Software\Infrastructure\aws-dev-access.ps1"
```

Alternativa esplicita per il login tramite codice (device code), da usare quando il flusso con browser locale non è praticabile — già verificata con successo in passato:

```powershell
& "C:\Users\servi\OneDrive\AI-RF-ONE\RF One\03 Software\Infrastructure\aws-dev-access.ps1" -Remote
```

**Valori attesi (fissi, definiti nello script):**

| Parametro | Valore |
|---|---|
| Eseguibile AWS CLI | `C:\Program Files\Amazon\AWSCLIV2\aws.exe` |
| Profilo | `rfone-dev-login` |
| Regione | `us-east-1` |
| Account atteso | `418674484214` (`arn:aws:iam::418674484214:user/RFone-admin`) |

**Comportamento:**

1. Esegue `sts get-caller-identity` sul profilo `rfone-dev-login`.
2. Se le credenziali sono valide e l'account combacia con quello atteso → conferma "AWS pronto" e termina (`exit 0`), **senza chiedere login**.
3. Se l'account restituito è diverso da quello atteso → segnala l'errore e termina (`exit 2`), **senza avviare login**.
4. Se `sts get-caller-identity` fallisce, lo script distingue l'errore prima di agire:
   - errore di rete, di configurazione (profilo/regione/eseguibile) o di permessi → segnala il problema e termina (`exit 3`), **senza avviare login** (nessun ciclo di login inutile);
   - errore riconducibile a credenziali assenti/scadute → **unico caso** in cui avvia `aws login --profile rfone-dev-login` (o `--remote` se richiesto), mostrando prima le istruzioni su quando aprire il browser e quando incollare il codice nel terminale.
5. Dopo un login, ri-verifica identità e account con lo stesso controllo del punto 1-3 e dichiara successo solo se il controllo riesce (`exit 0`); altrimenti segnala l'esito effettivo.

Nessuna password o codice viene passato come argomento di comando o scritto su log dallo script: il login avviene interamente nel meccanismo standard `aws login` nel terminale interattivo dell'utente.

**Regola operativa per l'agente AI ("il mulo"):** prima di qualunque operazione che richieda AWS, eseguire questo script (o quantomeno `sts get-caller-identity` con questo profilo/regione) e leggerne l'esito. Chiedere l'intervento umano (aprire il browser, incollare il codice) **solo** quando lo script lo richiede esplicitamente per rinnovare il login — mai avviare `aws login` "per sicurezza" quando l'identity check è già positivo, e mai invalidare una sessione valida per testare il ramo di rinnovo.

**Verificato il 2026-09-11:** con le credenziali già valide in sessione, il ramo "nessun login necessario" (punto 2) è stato eseguito ed è stato confermato l'account `418674484214`. Il ramo di rinnovo (`aws login` / `--remote`), il ramo di mismatch account e il ramo di errore di rete/permessi/configurazione **non sono stati eseguiti in questa verifica** (per non invalidare la sessione valida) — sono stati implementati e riletti a codice ma non osservati a runtime.

---

## URL AWS verificati (ricognizione)

Ricognizione eseguita interrogando direttamente AWS App Runner (`aws apprunner list-services --profile rfone-dev-login --region us-east-1`) e poi verificando ogni indirizzo con una richiesta HTTP reale, controllando il contenuto restituito (titolo/pagina), non solo il codice di stato — vedi il report completo in chat per il dettaglio del metodo di verifica di ciascuna riga.

Servizi App Runner trovati in `us-east-1` sul profilo `rfone-dev-login`:

| ServiceName | ServiceUrl | Status |
|---|---|---|
| `rfone-web` | `vhmsm9mgh8.us-east-1.awsapprunner.com` | RUNNING |
| `rfone-tips` | `mxgsc3nwha.us-east-1.awsapprunner.com` | RUNNING |

| Componente | URL | Verificato il | Note |
|---|---|---|---|
| Home RF-One | `https://vhmsm9mgh8.us-east-1.awsapprunner.com/` | 2026-09-11 | App Runner `rfone-web`. `GET /` → 302 a `/login?next=/`; `/login` risponde 200 con `<title>Log in · RF-One</title>`, branding "RF-ONE", form con `csrf_token` — confermata l'app RF-One Web (`03 Software/RF-One Web/app.py`), non solo lo status HTTP. |
| Training integrato | `https://vhmsm9mgh8.us-east-1.awsapprunner.com/training` | 2026-09-11 | Stesso servizio `rfone-web`. `GET /training` → 302 a `/login?next=/training`: confermato che la route è montata dentro RF-One Web dietro lo stesso login (SSO), coerente con `domain_registry.py` (`TRAINING`, `link="/training"`) e `training_integration.py`. **Verifica pubblica (redirect) ripetuta il 2026-09-11 dopo il deploy della modale multi-assegnazione; contenuto autenticato (pagina studente, modale) verificato solo in locale con account tecnici su DB temporaneo, non in produzione.** |
| Menu pubblico | `https://vhmsm9mgh8.us-east-1.awsapprunner.com/training/menu` | 2026-09-11 | Stesso servizio `rfone-web`. `GET /training/menu` → 200, senza login, con `<title>Rome's Flavours · Dish guide</title>` — la "unauthenticated dish-guide route" citata in `app.py`. Stesso contenuto raggiungibile anche su `rfone-tips` (`https://mxgsc3nwha.us-east-1.awsapprunner.com/training/menu`, verificato anch'esso 200 con lo stesso titolo) — indirizzo duplicato, non un'app diversa. |
| Tips | `https://mxgsc3nwha.us-east-1.awsapprunner.com/` | 2026-09-11 | App Runner `rfone-tips`. `GET /` → 200 con `<title>RF-One · Tips</title>` e riferimenti a `distribution-rules`/`calculate-tips` nel markup — confermata l'app Tips (`03 Software/Tips/app.py`), servizio separato da `rfone-web`, coerente con `domain_registry.py` (`TIPS`). **Non ridistribuito in questa sessione — verificato di nuovo il 2026-09-11 solo per confermare che è rimasto invariato.** |
| Selection — pagina provvisoria | `https://vhmsm9mgh8.us-east-1.awsapprunner.com/selection` | 2026-09-11 | Stesso servizio `rfone-web`. **Non è l'app Selection reale** (`03 Software/Selection/app.py`, mai deployata) — è una pagina "Selection — Work in progress" dentro RF-One Web, dietro `require_domain_access("SELECTION")` (account ACTIVE + Domain SELECTION abilitato). `GET /selection` senza login → 302 a `/login?next=/selection` (verificato via curl, pubblico). Con account tecnico + accesso SELECTION su DB temporaneo locale → 200 con testo "Selection — Work in progress" (verificato in locale, non in produzione — nessun account di test creato sul DB reale). Motivo: l'app Selection reale non ha autenticazione server-side utilizzabile (`/identity/switch` è esplicitamente documentata nel suo stesso codice come "not a login screen") e salva i CV su disco locale del container (perso a ogni redeploy) — pubblicarla con dati reali sarebbe stata un'esposizione di PII senza controllo d'accesso. |
| Compensation V1 (operativa) | `https://vhmsm9mgh8.us-east-1.awsapprunner.com/compensation` | 2026-09-11 (redeploy pomeridiano) | Stesso servizio `rfone-web`, immagine ECR `rfone-web:latest` ridistribuita (digest `sha256:85f81556fa0846fa27081e1331f0346262cc349a6b54ccd438111b3430e7e5d0`, deploy operation `ee625a15a6e7459d9d6a711ff1621430`, SUCCEEDED). Sostituisce la pagina "Work in progress": ora monta `03 Software/RF-One Web/compensation_routes.py` (creazione run, calcolo, approvazione, prospetto/export CSV, conferma comunicazione manuale, registrazione risultato provider, riconciliazione), sempre dietro `require_domain_access("COMPENSATION")`. `GET /compensation` senza login → 302 a `/login?next=/compensation` (verificato via curl, pubblico, dopo il redeploy). Migrazione `f7174fa37e93` applicata al database reale `rfone-dev` (RDS PostgreSQL) — snapshot manuale `rfone-dev-pre-compensation-v1-20260911t135758z` creato come punto di recupero prima della migrazione. Ciclo funzionale completo (calcolo → approvazione → export → conferma comunicazione → registrazione risultato manuale → riconciliazione) verificato su un database PostgreSQL di test disposable, creato ed eliminato sulla stessa istanza RDS — non sul database `rfone` reale e senza dati/provider reali. |

**Da non presentare come verificato senza ripetere il controllo:** questa tabella riflette lo stato osservato il 2026-09-11. Un nuovo deploy, un redeploy con nuovo URL, o l'integrazione futura di Selection in AWS possono invalidarla — ripetere la ricognizione prima di riusarla come fonte. La riga Selection resta valida solo finché quella route continua a servire la pagina provvisoria — se in futuro viene ricollegata a un'app reale, va riverificata.

---

## Procedura di rilascio di `rfone-web` (ricostruita ed eseguita il 2026-09-11)

Nessuno script di deploy era presente nel repository; la procedura è stata ricostruita ispezionando la configurazione AWS effettiva (il `Dockerfile`/`buildspec.yml` esistevano solo dentro il sorgente già distribuito su S3, mai committati) ed eseguita per pubblicare Compensation V1. Componenti riusati, nessuno creato ex novo:

| Componente | Identificativo |
|---|---|
| Bucket sorgente | `s3://rfone-tips-deploy-418674484214/rfone-web-source.zip` |
| Progetto CodeBuild | `rfone-web-build` (builda l'immagine Docker e la pubblica su ECR `:latest`) |
| Repository ECR | `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web` |
| Servizio App Runner | `rfone-web` (`AutoDeploymentsEnabled: false` — un nuovo `:latest` su ECR **non** si ridistribuisce da solo) |
| Database | RDS PostgreSQL `rfone-dev` (`rfone-dev.coj0wskcg634.us-east-1.rds.amazonaws.com:5432`, DB `rfone`), credenziali in Secrets Manager `rfone-tips/database-url` (condiviso con `rfone-tips`) |

**Passi (PowerShell, profilo `rfone-dev-login`):**

1. Pacchettizzare `03 Software/{RF-One Data Store, RF-One Web, Training, Shared UI}` più `Dockerfile`/`buildspec.yml` (estratti dal sorgente già distribuito) in uno zip **con separatori `/` nei nomi dei file** — `Compress-Archive` di PowerShell 5.1 scrive `\`, che CodeBuild/Docker su Linux non riconoscono come directory (causa un build context vuoto); usare `zipfile` di Python o un tool equivalente che scriva `/`. Escludere `__pycache__/`, `*.pyc`, `data/` (DB SQLite locali).
2. Backup del sorgente corrente: `aws s3api copy-object` da `rfone-web-source.zip` a `backups/rfone-web-source-pre-<label>-<timestampUTC>.zip` nello stesso bucket — **prima** di sovrascrivere.
3. `aws s3api put-object` del nuovo zip su `rfone-web-source.zip`.
4. `aws rds create-db-snapshot` su `rfone-dev` (snapshot manuale, `rds wait db-snapshot-available`) — punto di recupero **prima** di qualunque migrazione.
5. `aws codebuild start-build --project-name rfone-web-build`; attendere `buildStatus != IN_PROGRESS` (`codebuild batch-get-builds`). In caso di `FAILED`, i log sono in CloudWatch `/aws/codebuild/rfone-web-build`, stream = build id.
6. Applicare le migrazioni (`alembic upgrade head`) al database reale **prima** del redeploy dell'app (le migrazioni Compensation sono additive — vecchio codice applicativo, nuove tabelle/colonne coesistono senza errori).
7. `aws apprunner start-deployment --service-arn <arn rfone-web>`; attendere `Service.Status == RUNNING` (`apprunner describe-service`).
8. Verifica non invasiva: `curl` su `/`, `/login`, e sulle route nuove/esistenti — solo redirect/status, mai creare o modificare dati reali.

**Nota:** la password del database non deve mai comparire in output di terminale/log — recuperarla da Secrets Manager solo all'interno di uno script che la usa in-process (es. `boto3`) e la maschera prima di qualunque stampa (vedi `redact_database_url` in `rfone_data_store/database.py`), mai con `aws secretsmanager get-secret-value ... --output text` diretto in console.

---

## Stato SES (mittente RF-One)

Verificato il 2026-09-11 via `aws sesv2 get-account` / `get-email-identity` / `get-account` (dopo `put-account-details`):

| Voce | Stato al 2026-09-11 |
|---|---|
| Identità mittente `rfone@romesflavours.com` | Creata (`create-email-identity`), `VerificationStatus: PENDING` — email di verifica AWS inviata alla casella; nessuno l'ha ancora confermata (accesso alla casella riservato al Product Owner, non tentato da questa sessione). |
| Richiesta uscita sandbox | Inoltrata (`sesv2 put-account-details`, self-service, non richiede AWS Support a pagamento), `ReviewDetails.Status: PENDING`. `mail-type=TRANSACTIONAL`, `website-url=https://vhmsm9mgh8.us-east-1.awsapprunner.com`. |
| `RFONE_EMAIL_FROM_ADDRESS` su `rfone-web` | **Non impostata** — condizionata al mittente verificato, non ancora avvenuto. |
| Prova reale di invio | **Non eseguita** — il mittente non è ancora verificato, quindi SES rifiuterebbe qualunque invio da quell'indirizzo. |

**Prossimo passaggio (richiede il Product Owner):** aprire l'email di verifica AWS in `rfone@romesflavours.com` e confermare. Dopo la conferma, una sessione futura deve: impostare `RFONE_EMAIL_FROM_ADDRESS=rfone@romesflavours.com` su `rfone-web` (Secrets Manager o env var diretta), ridistribuire, ed eseguire una prova reale di invio verso la stessa casella — distinguendo l'accettazione della chiamata SES dalla consegna effettiva in casella (solo il Product Owner può verificare la seconda).
