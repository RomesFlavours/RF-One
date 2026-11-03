# Invoice Intake — Test Master Report

Redatto: 2026-10-05. Consolida le prove di lettura fatture del 2026-09-27 (AWS Textract, Amazon Bedrock, lettura
diretta). Non sostituisce il report di dettaglio
`Risultati AI visiva/Confronto letture - Bedrock, lettura diretta Mulo, Textract.md`, che resta la fonte delle
conclusioni riga per riga.

Legenda: **[FATTO]** = osservato nei file; **[DOC]** = interpretazione già scritta in un file del repository (citato);
**[APERTO]** = questione non risolta in nessun file.

---

## 1. Scopo

[DOC] Prova isolata, "nessuna integrazione in RF-One" (Confronto, intestazione): confrontare come tre metodi leggono
le stesse fatture fornitori reali — AWS Textract `AnalyzeExpense`, un modello visivo su Amazon Bedrock, la lettura
diretta del Mulo — rispetto agli originali letti a vista.

## 2. Documenti di prova

[FATTO] Tre fatture distinte, una pagina ciascuna, ognuna presente in **due copie identiche** (stesso SHA-256) nella
radice di `07 Tasks/Invoices/` e in una **terza copia identica** in
`01 Domains/Shared Domains/Administration/Invoice Intake/Invoices/Raw/`.

| Fattura | Copia "nominata" (usata da `make_pdfs.py`) | Copia identica in radice | Copia in `Raw/` (Domain) | SHA-256 (12) |
|---|---|---|---|---|
| Ben E. Keith, 08/26/2026, pagina 1 di 2 | `2026-08-Keith PM.pdf` | `2026-08-29_22228 PM.pdf` | `2026-08-29_22228 PM.pdf` | `792a82fc0b00` |
| Gordon Food Service, 08/26/2026, pagina 1 di 2 | `2026-08-Gordon.pdf` | `Receipt_2026-08-29_22343 PM.pdf` | `Receipt_2026-08-29_22343 PM.pdf` | `1050699ac5f2` |
| Cheney Brothers, 08/19/26 | `2026-08-Cheney.pdf` | `Receipt_2026-08-29_22037 PM.pdf` | `Receipt_2026-08-29_22037 PM.pdf` | `b7e2e8ba1c23` |

[FATTO] Keith e Gordon riportano "Page 1 of 2": la pagina 2 non è disponibile in nessuna copia.

## 3. Test AWS Textract

[FATTO]
- **Quando / come:** 2026-09-27 20:01 UTC, API `AnalyzeExpense`, regione `us-east-1`, profilo `rfone-dev-login`;
  una chiamata per pagina per ogni file **distinto** (le copie identiche lette una volta sola). 3 pagine, costo
  stimato USD 0,03 (`Risultati AWS/Risposte Amazon/run_log.json`).
- **Script:** `textract_run.py`. **Non è nel repository:** si trova solo nello scratchpad temporaneo della sessione
  `75b3cfd9-…` (`%TEMP%\claude\…\75b3cfd9-6961-4791-9685-562f649ca513\scratchpad\textract_run.py`).
- **Risposte grezze:** `Risultati AWS/Risposte Amazon/<sha12>_page1.json`, intatte, con i `request_id` nel run log.
- **PDF leggibili:** `Risultati AWS/<Fornitore> - <data> - <numero>.pdf` = originale + quanto restituito da Amazon,
  "verbatim", senza correzioni (generati da `build_pdfs.py`, anch'esso **solo** nello stesso scratchpad, via HTML
  intermedi in `pdf_build/`). Il nome del PDF Cheney ("data non restituita") registra che Textract non ha
  restituito la data come data.

[DOC] Esiti (Confronto, tabelle per fattura e Sintesi): nessun errore sui numeri degli articoli; dati importanti in
campi generici (`OTHER`: confezione, peso, fuel charge, pagine, parti della data); errori di tipizzazione con impatto
contabile — subtotali di sezione come righe (Keith), due prezzi per riga (Gordon, Inv Value come `UNIT_PRICE`),
supplemento tipizzato `DISCOUNT` (Cheney), "Page Total" come `TOTAL` (Gordon); omissioni — base del prezzo (Cheney),
promo già inclusa (Gordon), data Cheney; `VENDOR_NAME` doppio (Keith, Gordon). Textract non inferisce.

## 4. Test Bedrock / AI

[FATTO]
- **Script:** `Risultati AI visiva/run_bedrock_vision.py` — API `bedrock-runtime Converse`, `us-east-1`,
  `max_tokens` 11000, thinking adattivo. Al modello vanno solo tre immagini della pagina (intera orientata + metà alta
  + metà bassa sovrapposte) e il prompt; nessun output Textract, nessuna trascrizione, nessun valore atteso.
- **Prompt:** `Risultati AI visiva/prompt_used.txt` (unico; estrazione JSON di fornitore, data, righe, charges,
  problemi del documento; regole "non inventare", "un valore calcolato non è un valore letto").
- **Immagini inviate:** `Risultati AI visiva/Immagini inviate/` (9 JPG: `<Fornitore>_oriented|top|bottom.jpg`).
  Lo **script che le ha prodotte (orientamento e ritaglio) non è stato trovato** né nel repository né negli scratchpad.
- **Esecuzioni** (`Risposte modello/run_log_*.json`):

| Fattura | Modello | Esito | Token in/out | Costo stimato USD |
|---|---|---|---|---|
| Keith | Claude Opus 4.6 (`us.anthropic.claude-opus-4-6-v1`) | `end_turn`, 9 righe, 1 charge | 5.272 / 4.039 | 0,1273 |
| Gordon (1° tentativo) | Claude Opus 4.6 | **Perso**: timeout client 60 s, 4 retry automatici di botocore, 5 invocazioni fatturate, nessuna risposta | 5×5.664 / 29.470 | 0,8783 |
| Gordon | Claude Sonnet 4.6 (`us.anthropic.claude-sonnet-4-6`) | `max_tokens`: risposta **troncata**, JSON non completo | 5.664 / 11.000 | 0,182 |
| Cheney | Claude Sonnet 4.6 | `end_turn`, 2 righe, 1 charge | 5.462 / 4.463 | 0,0833 |

  Dopo il tentativo perso, lo script è stato portato a `read_timeout` 900 s e a nessun retry automatico (commento
  nello script). Totale stimato Bedrock ≈ USD 1,27.
- **Risposte grezze:** `Risposte modello/<Fornitore>_response.json` (risposta completa) e `_answer.txt` (solo il
  testo restituito).
- **PDF leggibili:** `Keith - 08-26-2026 - Bedrock Opus 4.6.pdf`, `Gordon - 08-26-2026 - Bedrock Sonnet 4.6
  (incompleta).pdf`, `Cheney - 08-19-26 - Bedrock Sonnet 4.6.pdf`, generati da `make_pdfs.py` senza chiamate al
  modello. Per Cheney il PDF mostra due **correzioni di presentazione** del Mulo (unità di peso "lb" non stampata);
  la risposta originale resta intatta in `Cheney_answer.txt`.

[DOC] Esiti (Confronto): nessun dato inventato in nessuna fattura; numeri stampati letti correttamente; aggiunge il
significato (base del prezzo, subtotali esclusi, segni, sconti già inclusi). Rischi osservati: alcune inferenze
formulate come lettura (2 unità "lb" su Cheney; base "per CS" su Gordon), troncamento dell'output (Gordon: 1 riga,
charges e segnalazione della pagina mancante persi; campo casse vuoto), un dubbio non pertinente sull'anno 2026
(Keith).

## 5. Test lettura diretta

[FATTO] Solo **Gordon**. Lettore: "Mulo (Claude, direct visual reading in the Claude Code session, 2026-09-27); no
AWS or external service call" (`Lettura diretta Mulo/Gordon_lettura_diretta_Mulo.json`). Fonte: `2026-08-Gordon.pdf`.
Risultato: 16 righe, 0 charges, valori distinti tra stampati e inferenze, 3 ambiguità, 2 problemi del documento.
PDF: `Gordon - 08-26-2026 - Lettura diretta Mulo.pdf`, generato da `make_direct_pdf.py` (nessuna chiamata esterna).

[DOC] "Ulteriore lettura, verificata con controlli aritmetici, non una verità assoluta" (Confronto). Controlli: su
tutte le 16 righe Q.tà × costo = importo; 197.86 + 596.95 + 209.49 = 1004.30 = Page Total — "sono calcoli, non dati
stampati".

## 6. Confronto dei risultati

[DOC] Sintesi del Confronto, riportata senza aggiunte:

| | Bedrock | Textract |
|---|---|---|
| Errori sui valori stampati | nessuno | nessuno sui numeri degli articoli |
| Omissioni | Gordon: 1 riga, charges e pagina mancante (troncamento), campo casse | base del prezzo (Cheney), promo (Gordon), data Cheney come data |
| Inferenze presentate come lette | 2 unità "lb" (Cheney); base "per CS" (Gordon) | nessuna |
| Errori di significato / tipizzazione | nessuno | subtotali come articoli, due prezzi per riga, supplemento come DISCOUNT, Page Total come TOTAL |
| Dati in campi generici | — | confezione, peso, fuel charge, pagine, parti della data |

[DOC] Interpretazione già scritta: "entrambe le letture automatiche riportano correttamente i numeri stampati.
Bedrock aggiunge il significato […]. Il suo rischio è di formulare come lettura qualche inferenza e di troncare
l'output. Textract non inventa nulla, ma lascia molto in campi generici e sbaglia alcune classificazioni con impatto
contabile."

[FATTO] Copertura non uniforme: ogni fattura è stata letta da **un solo** modello Bedrock (Keith Opus, Gordon e Cheney
Sonnet); la lettura diretta esiste solo per Gordon.

## 7. Limiti osservati

[FATTO / DOC]
- Pagina 2 di Keith e Gordon mai disponibile: charges, tasse e totale fattura non determinabili.
- Gordon/Bedrock incompleto (`max_tokens`); il tentativo Opus su Gordon è andato perso ma fatturato.
- Campione di 3 fatture, 3 fornitori, una pagina ciascuna.
- Il riferimento è la lettura a vista degli originali; non esiste un valore atteso "certificato".
- Riproducibilità parziale: script Textract e generatore PDF AWS fuori dal repository; script di preparazione delle
  immagini non trovato.
- Costi indicati come **stime** a listino; "Bedrock billing may differ" (`run_bedrock_vision.py`).

## 8. Decisioni già prese

[DOC] Solo quelle scritte nei file:
- **Provider iniziale V1 = AWS Textract `AnalyzeExpense`** per il percorso dei documenti non strutturati; RF-One resta
  provider-agnostic al confine dell'agente; la risposta grezza del provider si conserva intatta
  (`01 Domains/Shared Domains/Administration/Invoice Intake/CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001.md`).
- L'app Invoice Intake legge foto e scansioni con Textract e, per design, le manda quasi sempre in revisione HUMAN;
  i limiti osservati (subtotali "Cooler"/"Dry" letti come righe, fornitori multipli, unità di misura) sono già
  documentati in `03 Software/InvoiceIntake/README.md` (INVOICE_SCAN_ACQUISITION_001).
- Le prove sono isolate: nessuna integrazione di Bedrock in RF-One (Confronto).
- Gli artefatti con contenuto delle fatture reali non vanno in Git (`.gitignore`, righe "Invoice reading trials":
  `*.pdf`, `*.jpg`, `*.zip`, `*.json`, `Risposte modello/*.txt` sotto `07 Tasks/Invoices/`); il Markdown di confronto,
  il prompt e gli script restano visibili "so they can be decided on".

## 9. Questioni ancora aperte

[APERTO] Nessun file registra una decisione su:
1. se adottare una lettura AI visiva (Bedrock) accanto o al posto di Textract, e con quale modello;
2. una ripetizione completa di Gordon con Bedrock (oggi troncata) e la lettura delle pagine 2;
3. se salvare nel repository `textract_run.py` e `build_pdfs.py` (oggi solo in una cartella temporanea);
4. quale copia degli originali è quella di riferimento (radice di `07 Tasks/Invoices/` o `Raw/` del Domain);
5. le soglie di confidenza alta/bassa, già aperte in `CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001.md` (§8).

## 10. Mappa dei file

Percorsi relativi a `07 Tasks/Invoices/` salvo indicazione. Date = modifica su disco. Ruolo: S = sorgente,
R = risultato, X = script, P = prompt, D = report.

| Percorso | Data | Byte | Ruolo | Prova | Classificazione |
|---|---|---|---|---|---|
| `2026-08-Keith PM.pdf` | 2026-08-29 | 1.734.610 | S | tutte (Keith) | DA TENERE |
| `2026-08-29_22228 PM.pdf` | 2026-09-14 | 1.734.610 | S | — | DUPLICATO (= Keith PM e `Raw/`) |
| `2026-08-Gordon.pdf` | 2026-08-29 | 1.613.424 | S | tutte (Gordon) | DA TENERE |
| `Receipt_2026-08-29_22343 PM.pdf` | 2026-09-14 | 1.613.424 | S | — | DUPLICATO (= Gordon e `Raw/`) |
| `2026-08-Cheney.pdf` | 2026-08-29 | 2.048.514 | S | tutte (Cheney) | DA TENERE |
| `Receipt_2026-08-29_22037 PM.pdf` | 2026-09-14 | 2.048.514 | S | — | DUPLICATO (= Cheney e `Raw/`) |
| `Risultati AWS.zip` | 2026-09-27 | 3.055.634 | R | Textract | DUPLICATO (i 7 file interni identici a `Risultati AWS/`) |
| `Risultati AWS/Keith - 08-26-2026 - 57978854.pdf` | 2026-09-27 | 1.266.998 | R | Textract | DA TENERE |
| `Risultati AWS/Gordon - 08-26-2026 - 9039354564.pdf` | 2026-09-27 | 931.121 | R | Textract | DA TENERE |
| `Risultati AWS/Cheney - data non restituita - 05-9100355806.pdf` | 2026-09-27 | 1.070.501 | R | Textract | DA TENERE |
| `Risultati AWS/Risposte Amazon/792a82fc0b00_page1.json` (Keith) | 2026-09-27 | 1.084.601 | R grezzo | Textract | DA TENERE (dato unico, fatturato) |
| `Risultati AWS/Risposte Amazon/1050699ac5f2_page1.json` (Gordon) | 2026-09-27 | 1.372.839 | R grezzo | Textract | DA TENERE (dato unico, fatturato) |
| `Risultati AWS/Risposte Amazon/b7e2e8ba1c23_page1.json` (Cheney) | 2026-09-27 | 783.375 | R grezzo | Textract | DA TENERE (dato unico, fatturato) |
| `Risultati AWS/Risposte Amazon/run_log.json` | 2026-09-27 | 1.556 | R (log) | Textract | DA TENERE |
| `Risultati AI visiva/Confronto letture - Bedrock, lettura diretta Mulo, Textract.md` | 2026-09-27 | 6.973 | D | tutte | DA TENERE (unico report di dettaglio) |
| `Risultati AI visiva/prompt_used.txt` | 2026-09-27 | 3.734 | P | Bedrock | DA TENERE (unico prompt) |
| `Risultati AI visiva/run_bedrock_vision.py` | 2026-09-27 | 3.143 | X | Bedrock | DA TENERE |
| `Risultati AI visiva/make_pdfs.py` | 2026-09-27 | 9.631 | X | Bedrock (PDF) | DA TENERE |
| `Risultati AI visiva/make_direct_pdf.py` | 2026-09-27 | 5.700 | X | Lettura diretta (PDF) | DA TENERE |
| `Risultati AI visiva/Keith - 08-26-2026 - Bedrock Opus 4.6.pdf` | 2026-09-27 | 1.195.065 | R | Bedrock | DA TENERE |
| `Risultati AI visiva/Gordon - 08-26-2026 - Bedrock Sonnet 4.6 (incompleta).pdf` | 2026-09-27 | 1.124.262 | R | Bedrock | DA TENERE (documenta il troncamento) |
| `Risultati AI visiva/Cheney - 08-19-26 - Bedrock Sonnet 4.6.pdf` | 2026-09-27 | 1.053.414 | R | Bedrock | DA TENERE |
| `Risultati AI visiva/Gordon - 08-26-2026 - Lettura diretta Mulo.pdf` | 2026-09-27 | 1.152.483 | R | Lettura diretta | DA TENERE |
| `Risultati AI visiva/Lettura diretta Mulo/Gordon_lettura_diretta_Mulo.json` | 2026-09-27 | 15.412 | R | Lettura diretta | DA TENERE (dato unico) |
| `Risultati AI visiva/Immagini inviate/*.jpg` (9 file, 0,42–0,89 MB) | 2026-09-27 | 5.582.975 tot. | S derivata | Bedrock | DA TENERE (input esatto inviato; script di preparazione non trovato) |
| `Risultati AI visiva/Risposte modello/{Keith,Gordon,Cheney}_response.json` | 2026-09-27 | 17.211 / 45.154 / 20.866 | R grezzo | Bedrock | DA TENERE (dato unico, fatturato) |
| `Risultati AI visiva/Risposte modello/{Keith,Gordon,Cheney}_answer.txt` | 2026-09-27 | 4.984 / 8.191* / 3.157 | R | Bedrock | DA TENERE (derivabile dal `_response.json`, ma citato dal Confronto) |
| `Risultati AI visiva/Risposte modello/run_log_Gordon_Cheney.json` | 2026-09-27 | 1.096 | R (log) | Bedrock Sonnet | DA TENERE |
| `Risultati AI visiva/Risposte modello/run_log_Keith_opus46.json` | 2026-09-27 | 944 | R (log) | Bedrock Opus | DA TENERE (unica traccia del tentativo perso) |
| `INVOICE_INTAKE_TESTS_MASTER_REPORT.md` | 2026-10-05 | — | D | tutte | DA TENERE (questo file) |

\* 8.438 byte su disco (8.191 caratteri).

**Fuori da `07 Tasks/Invoices/` (solo lettura, non toccati):**

| Percorso | Ruolo | Classificazione |
|---|---|---|
| `%TEMP%\claude\…\75b3cfd9-…\scratchpad\textract_run.py` (2.273 B) | X Textract | DA TENERE — a rischio: cartella temporanea |
| `%TEMP%\claude\…\75b3cfd9-…\scratchpad\build_pdfs.py` (14.161 B) | X PDF Textract | DA TENERE — a rischio: cartella temporanea |
| `%TEMP%\claude\…\75b3cfd9-…\scratchpad\pdf_build\*.html` (3 file, ≈3,1 MB) | output intermedio dei PDF Textract | ELIMINABILE (i PDF esistono) |
| `%TEMP%\claude\…\75b3cfd9-…\scratchpad\pdf_build\edge-profile\` | profilo browser per la stampa PDF | ELIMINABILE |
| `01 Domains/…/Invoice Intake/Invoices/Raw/` (3 PDF identici agli originali delle prove) | S (Domain) | Non di competenza di questo task — non toccare |
| `03 Software/InvoiceIntake/uploads/` (719 file, 21 MB) | dati runtime dell'app | Fuori perimetro; nessun file coincide con le fatture di prova |

## 11. Elementi candidati alla pulizia

Nessuno spostamento né cancellazione è stato fatto.

| Elemento | Motivo | Proposta |
|---|---|---|
| `Risultati AWS.zip` | Contenuto identico, file per file (SHA-256), a `Risultati AWS/` | ELIMINABILE (o ARCHIVIARE se serve un pacchetto da condividere) |
| `2026-08-29_22228 PM.pdf`, `Receipt_2026-08-29_22343 PM.pdf`, `Receipt_2026-08-29_22037 PM.pdf` | Copie identiche delle copie nominate e di `Raw/` | ELIMINABILE dopo la decisione §9.4. Il `run_log.json` Textract cita entrambi i nomi: resta interpretabile perché registra lo SHA-256 |
| `pdf_build/*.html` ed `edge-profile/` (scratchpad) | Intermedi | ELIMINABILE |
| `textract_run.py`, `build_pdfs.py` (scratchpad) | Script unici fuori repository | Copiare in `05 Scripts/` prima che la cartella temporanea venga pulita |
| Script di preparazione delle immagini | Non trovato | DA VERIFICARE (le 9 JPG inviate restano l'unica traccia) |

**Vincoli per un eventuale riordino** (verificati il 2026-10-05):
- `run_bedrock_vision.py`, `make_pdfs.py` e `make_direct_pdf.py` cercano `prompt_used.txt`, `Risposte modello/`,
  `Immagini inviate/` e `Lettura diretta Mulo/` **relativi alla propria cartella**; `textract_run.py` e
  `build_pdfs.py` hanno percorsi assoluti a `07 Tasks/Invoices` e `Risultati AWS/`.
- Il Confronto cita `Risposte modello/Cheney_answer.txt`.
- `.gitignore` riga 176 esclude per percorso esatto `07 Tasks/Invoices/Risultati AI visiva/Risposte modello/*.txt`:
  spostando quei file **senza** aggiornare la regola, le risposte del modello (contenuto di fatture reali)
  diventerebbero committabili.
- Nessun codice applicativo (`03 Software/InvoiceIntake/`) né documento di Domain fa riferimento a questi file.
