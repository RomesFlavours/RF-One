# CV Selection SP — migrazione locale OpenAI

Data: 3 novembre 2026. Base locale: `origin/shelbi/sp-cv-reading-fixes` @ `64f3058`.
Questa copia isolata evita le modifiche non committate nel checkout principale.
Nessun push, deploy, modifica di segreti AWS o invio di CV reali è autorizzato da questo lavoro.

## Motivazione

Benchmark fornito dall’utente: gruppi corretti 80/84 Terra contro 69/84 Haiku;
costo osservato $6,68 contro $9,97 per 1.000 CV; latenza 19,2 contro 16,3 secondi.
Sono risultati precedenti dell’utente, non nuove misure ottenute durante questa migrazione.
Il prompt resta SP-1.1. Verifica delle citazioni, date, stabilità e ranking rimangono
quelli del branch Shelbi; nessuna nuova soglia o regola di selezione è introdotta.

## Confine del cambiamento

Il nuovo `workspace/sp/provider.py` riguarda solo SP (analisi, rilettura esplicita e OCR degli upload SP).
La selezione globale `RFONE_AI_PROVIDER`, il registro condiviso e gli altri domini non vengono migrati.
Le cinque schede restano Selection, Applications, Evaluation, Interviews, Decisions.
Il branch Shelbi è la baseline inclusa: parser dei telefoni, conservazione dei dati
in rilettura, immagini limitate a 1.600 pixel/4 pagine, timeout, queue deduplication,
correzioni delle citazioni/skills, periodi sovrapposti e switch Short stays sono presenti.
Il confronto di questa migrazione rispetto a Shelbi non modifica il motore deterministico.

SP non esegue più automaticamente sia il parser AI dell’identità sia l’analisi AI.
Riusa il nome della risposta SP solo se presente nel CV; email/telefono restano estratti localmente.
`SP_AI` distingue questa lettura dalla lettura completa del parser `REAL_AI`.
“Read again” resta un’azione esplicita per CV precedenti: una lettura del profilo, nessuna nuova analisi SP.
Il riuso delle analisi esistenti resta basato su versione requisiti e checks, non sul provider:
le analisi storiche Haiku mantengono la propria provenienza e non vengono pagate nuovamente.

## Configurazione e segreti

Variabili di processo, iniettate dal secret store: `RFONE_SP_OPENAI_API_KEY` (preferita)
o `OPENAI_API_KEY`. Il provider SP non legge la chiave da `.env` o da file nel repository. Su Windows riconosce anche la variabile utente già salvata nel profilo corrente, se il processo desktop è stato aperto prima della sua configurazione; il registro viene solo letto.
Non incollare chiavi in chat, comandi con argomenti visibili, configurazioni versionate o log.
Per AWS futuro: usare un riferimento a Secrets Manager/SSM nel servizio, dopo approvazione separata;
nessun segreto o ruolo viene creato da questa implementazione locale.

- `RFONE_SP_AI_PROVIDER=OPENAI` è il default SP, modello fissato `gpt-6.1-terra`.
- `RFONE_SP_AI_PROVIDER=BEDROCK` forza Haiku 4.5 per SP, indipendente dal modello globale.
- `RFONE_SP_AI_FALLBACK=BEDROCK` abilita il fallback solo per errori transitori di trasporto;
  senza questa variabile è disabilitato. Errori di autenticazione/configurazione non attivano fallback.
- I permessi AI della singola posizione e dell’installazione continuano ad applicarsi.
- `RFONE_SP_SYNTHETIC_ONLY=1` serve esclusivamente ai test con dati generati; non abilitarlo
  nell’applicazione che accetta CV reali. Non è un classificatore automatico dei dati.

## Verifica dati prima di CV reali

Documentazione ufficiale consultata:
[Data controls](https://developers.openai.com/api/docs/guides/your-data),
[modello Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra).

Le richieste usano HTTPS verso `api.openai.com/v1/responses`, `store=false`,
ragionamento `none`; nessun Files upload, thread remoto, background mode o conversation id.
I dati API non sono usati per training per default. `store=false` disabilita lo stato della risposta,
ma non elimina da solo i log di monitoraggio abusi (normalmente fino a 30 giorni);
ZDR/MAM richiedono abilitazione/approvazione dell’organizzazione. Per immagini esistono eccezioni
specifiche indicate dalla documentazione. La mascheratura di email e telefoni non anonimizza il CV:
nome, datori e testo libero possono ancora identificare la persona; OCR riceve le immagini originali.

La configurazione effettiva di organizzazione/progetto, data sharing, retention/ZDR, eventuale regione
e trattamento delle immagini NON è verificabile con i segreti disponibili in questa sessione.
Prima dei CV reali registrare la verifica del progetto/account e della base autorizzativa per il trattamento.
Solo allora impostare `RFONE_SP_DATA_REVIEWED=openai-api-reviewed`.
Se si abilita fallback con CV reali, serve anche `bedrock-reviewed`, separato da virgola.
Il codice blocca le chiamate prive della relativa attestazione; non pretende di verificare ZDR tramite API.

## Timeout, duplicati e limiti

Testo: un tentativo di trasporto, timeout 45 s; una sola ripetizione aggiuntiva se JSON non valido.
Scansioni: massimo due tentativi transitori, 12 s ciascuno più attesa di 1 s.
Con fallback scansioni: massimo una richiesta OpenAI e una Haiku.
Nessun retry per 400/401/403. Risposte incomplete/rifiutate non vengono accettate.
L’hash dei byte della scansione viene cercato prima dell’OCR: un upload identico riusa il testo salvato.
La coda persistente conserva i controlli di lease e versione del branch Shelbi.
Un crash dopo la risposta remota e prima del commit può ancora ripetere una richiesta alla ripresa:
non è una garanzia exactly-once verso il provider; nessun nuovo sistema distribuito è stato introdotto.
Scansioni simultanee non ancora salvate possono ancora fare due OCR; quelle già archiviate sono riusate.
PDF oltre quattro pagine richiedono controllo dell’originale; nessuna copertura integrale è promessa.

## Esecuzione locale

Dalla cartella Selection, usando Python con le dipendenze già presenti:

```powershell
python -X utf8 test_sp_openai.py
python -X utf8 test_sp_engine.py
python -X utf8 test_sp_real_cvs.py
python -X utf8 test_sp_integration_http.py
python -X utf8 test_sp_openai_live.py
```

Il test live genera un solo CV fittizio e un PDF raster dello stesso CV; non apre CV dell’utente.
Non crea email e non accede al database operativo. Richiede il segreto nell’ambiente di processo o, su Windows, nella variabile utente già configurata.
Scrive solo un consuntivo token/costo senza contenuto dei CV e senza credenziali.
Prezzi ufficiali consultati: input $1/M, output $5/M, input in cache $0,05/M.
Costi del benchmark precedente e costi di questo test devono rimanere separati.


## Verifica live completata

Il 3 novembre 2026 il test con OpenAI reale è riuscito: analisi di un CV generato e OCR del suo PDF raster.
La chiave del benchmark era già presente nella variabile utente Windows `OPENAI_API_KEY`;
la prima sessione di sviluppo non l’aveva ereditata. Non occorre creare una nuova chiave o acquistare crediti
per eseguire queste prove: l’API ha accettato entrambe le richieste.
Token: testo 1.361 input / 1.178 output; OCR 2.495 input / 91 output; cache 0.
Stima totale $0,010201, da riconciliare con il billing ufficiale; nessun saldo residuo viene dedotto da questa misura.
Nessun CV reale inviato. La verifica account di retention resta necessaria prima dei CV reali.

## Review by Shelbi, 3 November 2026 (branch `shelbi/sp-openai-review`, on top of this one)

- **Dates are never phones, in every format.** `deterministic_parser.phone_spans` masks date ranges and
  month-years ("01.2019 - 03.2022", "06-2019 - 03-2022", "2018.06 - 2021.03", "2019 - Present") before looking for
  a phone. Before, these were still read as a phone, both in the redaction sent to SP and in the duplicate
  check. `redact_contacts` now removes exactly the phones the reader recognizes, so a phone on the same line as
  a date range ("Server 2019 - 2022 407-555-0132") is removed too; before, it reached the AI.
- **Busy provider:** SP's evaluation waits 5, 15, 30 s and asks again after a 429/5xx, a timeout or Bedrock
  throttling, never after 400/401/403. No new attempt starts after 150 s, so one CV (even with the Haiku
  fallback and the JSON retry) ends inside the 10-minute lease and is never paid twice. Without this, the throttle
  waits removed in this branch left a busy minute as failed CVs to analyze again by hand.
- **Bedrock:** a client from its own boto3 session (the default session is not safe between the queue's threads);
  the error code is kept in the message; with `RFONE_SP_AI_PROVIDER=BEDROCK` the fallback never calls Haiku twice.
- **Name:** a CV is marked `SP_AI` only when SP's reply gives a name found word for word in the CV. Otherwise it
  stays "read without the AI" and Read again stays available (before, a name like "RESUME" stayed with no way to fix it).
- **One AI per ranking:** an analysis made by the other AI (older Haiku analyses, or the opt-in fallback) shows
  "Analyzed with another AI: update recommended" and Analyze redoes it, so one Job never ranks Haiku and OpenAI
  readings side by side.

Tests: `test_sp_openai.py` 19/19 (5 new), real CVs 35/35, engine 30/30, integration 30/30, CV Delete 30/30
(PowerShell), workspace 89/89, process 30/30, batch upload 39/39, the other Selection tests and Data Store
`test_selection_*` all pass.

**Before deploying this branch:** with no `RFONE_SP_DATA_REVIEWED`, every SP analysis, scan and Read again is
refused, Haiku included (`bedrock-reviewed`). Set it, and the OpenAI secret, or SP stops on deploy.
