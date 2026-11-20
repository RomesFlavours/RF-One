# Invoice Intake (prototipo)

**Nota canonica (Align legacy Invoice Intake with Purchased, evolve di TASK_PURCHASING_004):** Invoice Intake è il processo che alimenta **Purchased** (`01 Domains/Shared Domains/Purchased/README.md`), il Shared Domain proprietario del Purchase Fact (capture + normalize + publish). Il salvataggio finale avviene nel **RF-One Data Store** (`03 Software/RF-One Data Store/`, tramite `purchased_bridge.py`), che persiste il Purchase Document / Purchase Line (`line_type` PRODUCT/SURCHARGE/DISCOUNT) — lo stesso schema introdotto da TASK_PURCHASING_004, riusato as-is (nessuna tabella nuova). **Restaurant/Purchasing consuma** questo Purchase Fact per le proprie decisioni (Purchase Order, Configured Expectation, Physical Receiving, Reconciliation, Alert) — non lo possiede più, e non è mai un prerequisito per crearlo. Il file Excel (`data/PurchaseDocuments.xlsx`) resta disponibile solo come copia di debug/esportazione secondaria. Vedi `03 Software/RF-One Data Store/PURCHASING.md` per i dettagli implementativi.

Piccola web app locale: carichi una fattura (foto o PDF), l'app la legge e **salva subito** il documento come Purchase Fact canonico (Purchased), con stato funzionale **NORMALIZED/HUMAN**; ogni verifica o correzione avviene dopo, nella revisione (`/review/<id>`). `purchased_bridge.py` riconosce anche documenti duplicati/correzioni fornitore (Credit Memo, Corrected Invoice, ecc.) — vedi PURCHASING.md, §5.

**Acquisizione via email (`mailbox_acquisition/`):** oltre al caricamento manuale, Invoice Intake acquisisce fatture dalla casella **`invoices@romesflavours.com`** (Aruba) — un processo avviato a mano che scarica gli allegati e li consegna alla **stessa acquisizione** del caricamento manuale. Vedi `mailbox_acquisition/README.md`.

## Come funziona l'acquisizione (INVOICE_SCAN_ACQUISITION_001)

Un file = un'**acquisizione** (`document_acquisition.py`, archivio `data/document_acquisitions.db`), identificata dall'impronta SHA-256 del contenuto:

| Stato | Significato |
|---|---|
| `RECEIVED` | originale conservato in `uploads/`, non ancora letto |
| `FAILED` | lettura non riuscita (errore del servizio, file illeggibile, una pagina non elaborata). **Nessuna fattura creata**; l'originale resta conservato; pulsante **Riprova** in `/acquisitions` |
| `ACQUIRED` | ogni fattura trovata nel file è stata salvata come Purchase Document; Purchased decide NORMALIZED o HUMAN |

- **Ricaricare lo stesso identico file** non crea un'altra fattura né un'altra copia del file: vengono mostrati i documenti già creati.
- **Un nuovo tentativo** rilegge l'originale conservato (stesso record) e salva solo le fatture non ancora salvate (una per indice di fattura nel file): mai due volte la stessa.
- **Lettura** (`document_reader.py`):
  - PDF con testo digitale utilizzabile (il parser trova fornitore, un totale etichettato **e** almeno una riga): lettura dal testo, come prima, con divisione multi-fattura di `invoice_splitter.py`.
  - Ogni altro PDF (scansionato, o con uno strato di testo dello scanner che non dà righe) e ogni immagine (JPG, PNG, TIFF; WEBP/BMP convertiti in PNG in memoria): **AWS Textract `AnalyzeExpense`**, una chiamata per pagina (`providers/textract_provider.py`; le pagine di un PDF sono separate in memoria con pypdfium2, senza rasterizzare e senza OCR locale). Se anche una sola pagina non viene letta l'acquisizione è `FAILED` e l'errore elenca le pagine.
  - Le pagine sono raggruppate in fatture secondo il numero fattura letto su ciascuna: un numero diverso inizia una nuova fattura, una pagina senza numero continua la precedente.
- **Dati letti e conservati con l'acquisizione** (consultabili nel dettaglio `/review/<id>`, sezione B2): fornitore (tutte le letture diverse, se più d'una), numero, data, scadenza, destinatario, termini, valuta; righe con codice articolo, descrizione, quantità, unità di misura, prezzo unitario, importo, formato, marca, codice produttore; **importi di documento distinti**: totale fattura, subtotale, imposte, sconto, trasporto, altri supplementi (es. Fuel Charge), importo pagato/accreditato, **saldo residuo** — il saldo non è mai usato come totale. Per Textract, di ogni valore: pagina, posizione (bounding box), etichetta letta, confidenza. Risposta grezza del servizio in `uploads/_provider_mirror/`.
- **Nulla viene inventato**: un valore vuoto resta assente; un valore che non è ciò che il campo richiede (es. "Totals $ * Total" come subtotale) è elencato come **illeggibile**; due valori diversi per lo stesso importo sono un **conflitto**.

### Quando un documento è da verificare (HUMAN)

Oltre a fornitore/data/totale non riconosciuti (regola precedente), ogni volta che:

- mancano righe: una fattura senza nessuna riga acquisita non è mai completa;
- una riga non ha importo, o quantità × prezzo unitario ≠ importo;
- gli importi non tornano **al centesimo** (nessuna tolleranza: è stata eliminata l'accettazione automatica fino al 5%): righe = subtotale; subtotale (o righe) − sconto + imposte + trasporto + supplementi = totale; totale − pagato = saldo; saldo diverso dal totale senza alcun pagamento/credito indicato;
- ci sono letture in conflitto o valori illeggibili.

Il completamento della revisione applica lo stesso controllo ai valori effettivi (anche subtotale, imposte, sconto, trasporto, pagato e saldo sono correggibili). Un conflitto o un valore illeggibile resta bloccante finché il revisore non si è espresso su quel campo.

Nota: un codice articolo fornitore letto crea/usa il Supplier Product in Purchased; un articolo non ancora classificato genera la segnalazione di Purchased "Unknown or unclassified Supplier Product" (regola esistente di Purchased, non dell'acquisizione), che rende HUMAN il documento finché non viene risolta.

### Pagine

- `/` caricamento · `/acquisitions` stato di ogni file, errori, **Riprova** · `/documents` **tutti** i documenti, anche NORMALIZED · `/review` coda dei soli HUMAN · `/review/<id>` originale + dati letti + correzioni · `/mailbox` canale email.

## Requisiti

- Python 3.10 o superiore e le dipendenze in `requirements.txt` (`pdfplumber` porta con sé `pypdfium2`; `boto3` per Textract).
- **AWS Textract** per foto e scansioni: credenziali AWS risolte dalla catena standard di `boto3` (in locale `AWS_PROFILE=rfone-dev-login`, `AWS_REGION=us-east-1`); permesso `textract:AnalyzeExpense`. Senza accesso ad AWS, foto e scansioni finiscono in acquisizione `FAILED` (ritentabile), mai in una fattura vuota. Tesseract/Poppler **non** sono più usati dal flusso (`ocr_engine.py`/`tesseract_provider.py` restano nel repository ma non sono chiamati).
- Le dipendenze di `03 Software/RF-One Data Store/` (SQLAlchemy, Alembic), poiché `purchased_bridge.py` importa `rfone_data_store`.

## Installazione

Apri un terminale nella cartella del progetto:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r "../RF-One Data Store/requirements.txt"
```

## Avvio

```
set AWS_PROFILE=rfone-dev-login
set AWS_REGION=us-east-1
python app.py
```

Poi apri il browser su **http://127.0.0.1:5000**.

## Avvio dell'acquisizione email (opzionale)

```
python run_mailbox_acquisition.py          # loop continuo (30–60s configurabile)
python run_mailbox_acquisition.py --once   # un solo ciclo, poi esce
```

Richiede `ARUBA_IMAP_USERNAME`/`ARUBA_IMAP_PASSWORD` (vedi `.env.example` alla radice del repository) — vedi `mailbox_acquisition/README.md`, inclusa la sezione su come vengono riconosciuti e ignorati logo/firme email inline (mai un vero allegato di fattura).

## Dove finiscono i dati

Ogni fattura acquisita viene salvata nel RF-One Data Store (SQLite locale per default: `03 Software/RF-One Data Store/data/rfone.db`, o `RFONE_DATABASE_URL`). La schermata finale mostra il `PurchaseDocumentId` e lo stato NORMALIZED/HUMAN, oppure l'errore di lettura con il pulsante **Riprova**. Gli originali restano in `uploads/`; lo stato delle acquisizioni e i dati letti in `data/document_acquisitions.db`; la risposta grezza di Textract in `uploads/_provider_mirror/`. `uploads/` e `data/` non sono tracciati da Git.

Una fattura già registrata arrivata da un altro canale o come file diverso (stesso fornitore/numero/data/totale) non crea un secondo Purchase Fact (duplicato di Purchased). Un Credit Memo/Corrected Invoice/Return Credit/Adjustment viene registrato come nuovo documento collegato all'originale.

`data/PurchaseDocuments.xlsx` **non viene più aggiornato** dal flusso (nessun codice chiama più `excel_store.py`); resta solo come file storico.

## Riconoscimento fornitore + Supplier Format Training (foundation)

`supplier_format_training.py` registra, per ogni coppia (Fornitore, formato sorgente — es. "OCR/Direct", "PDF-Text/Instacart"), quanti documenti sono stati osservati e con quale esito NORMALIZED/HUMAN — un local store separato, solo osservativo. Una nuova coppia parte sempre `UNTRAINED`; una promozione a `TRAINING`/`VALIDATED` resta una decisione umana esplicita (`set_trust_state()`), mai automatica — l'unica transizione automatica è una *demotion* (`VALIDATED` → `DEGRADED`) quando il layout osservato cambia in modo sostanziale. Vedi `03 Software/RF-One Data Store/PURCHASING.md`, §11.

**"Purchased Supplier+Format Training — Phase 1"** ha avviato il training reale su documenti Purchased già acquisiti (Prime Line, Ben E. Keith, Costco — vedi il report in `07 Tasks/`). `supplier_format_rules.py` (nuovo) è lo stadio di specializzazione "generic parser → supplier-format specialization → validation" che `purchased_bridge.py` applica prima di validare un documento: correzioni mirate, verificate su documenti reali, solo per Prime Line Distributors, Costco Wholesale (canale diretto) e Ben E. Keith Foods (solo riconoscimento fornitore) — mai un'invenzione di pattern non osservati. `replay_supplier_format_training.py` riesegue in sola lettura (nessun nuovo Purchase Fact, nessun duplicato) l'estrazione sui documenti reali già acquisiti e aggiorna lo store di training/field-review.

Il riconoscimento del nome fornitore (`purchased_bridge._resolve_supplier_name`) preferisce sempre il testo del documento stesso; usa i Supplier già noti nel database solo per riconoscere alias dello stesso fornitore reale (es. "COSTCO" vs "Costco Wholesale #183"); usa il nome del file solo come **evidenza secondaria**, mai come fonte primaria, e non inventa mai un'identità fornitore che non sia già nota o presente nel testo.

**"Purchased Supplier Training — Phase 2"** ha chiuso tre gap emersi dalla Fase 1 (report in `07 Tasks/`):

- **Split multi-fattura** (`invoice_splitter.py`, nuovo): un solo PDF acquisito può contenere più fatture reali (Prime Line: 4 fatture, 1 per pagina; Ben E. Keith: 2 fatture, una su più pagine) — `purchased_bridge.save_purchase_documents_from_batch()` (usato ora da `mailbox_acquisition`) crea un `PurchaseDocument` per ogni fattura reale individuata, con provenance di pagina codificata in `source_reference` (es. `"file.pdf#p2-3"`). Se il confine tra fatture non è determinabile con sufficiente affidabilità, **non** viene fatto alcuno split automatico: l'intero file resta un solo documento, instradato a HUMAN dalla validazione esistente. Il flusso di upload manuale (`app.py`) resta invariato (fuori scope: "NON costruire una UI complessa").
- **Pulizia Supplier canonico + alias**: `Supplier.name` può ora essere corretto in-place (stesso `id`, nessuna FK rotta) tramite `repository.rename_supplier_canonical()`, che preserva il nome precedente come `SupplierAlias` — mai cancellato. `03 Software/RF-One Data Store/fix_supplier_canonical_names.py` ha già applicato questo al caso reale noto ("PRIME LINE DISTRIBUTORS INVOICE" → "Prime Line Distributors").
- **Soglia di trust configurabile**: `DEFAULT_TRUST_THRESHOLD = 5` è un default di partenza, non una regola universale — configurabile globalmente o per singola coppia Supplier+Format (`get_trust_threshold`/`set_trust_threshold`). La promozione `TRAINING` → `VALIDATED` (`promote_if_eligible()`) richiede N osservazioni consecutive corrette e resta sempre un'azione umana esplicita, mai automatica; un errore reale durante `VALIDATED` degrada subito a `DEGRADED` (oltre al cambio di layout già previsto in Fase 1).

## Purchased Human Review

`human_review.py` + le route `/review*` e `/training*` implementano il flusso HUMAN → review → correzione/conferma → NORMALIZED → training observation già descritto (ma mai costruito) da `Purchased/README.md`. Apri `/review` per la coda dei documenti HUMAN (più recenti per primi, con conteggio pendenti per Supplier); un allegato multi-fattura (Prime Line, Ben E. Keith) mostra tutte le fatture risultanti come record collegati. Aprendo un documento vedi provenance, header estratto, righe (con allocazione non-goods), e i motivi per cui è HUMAN; puoi confermare (CORRECT) o correggere (INCORRECT/UNREAD/AMBIGUOUS) ogni campo — **il valore originale estratto non viene mai sovrascritto** (`PurchaseDocument`/`PurchaseLine` restano immutabili "by convention"; la correzione è sempre un nuovo record additivo in `purchased_field_corrections`). "Completa review" ricalcola NORMALIZED/HUMAN con la stessa validazione usata al salvataggio iniziale, e aggiorna automaticamente lo store di training Supplier+Format — nessun secondo inserimento manuale. `/training` mostra lo stato trust di ogni coppia Supplier+Format ed espone "VALIDATE FORMAT" solo quando `is_eligible_for_validation()` è vera (mai una promozione automatica).

**Authority**: `10 System/Identity & Access/README.md` è congelato ("Do not continue implementation against this area"). `review_authority.py` è quindi un modello di azione minimo, locale a Purchased (VIEWER/REVIEWER/VALIDATOR), non il sistema Authority condiviso — `/review/login` non è un login reale, registra solo chi sta revisionando per l'audit trail e per i permessi di questa funzione soltanto.

## Limiti noti di questo prototipo

- **La lettura di foto e scansioni (AWS Textract) non è perfetta, e per design finisce quasi sempre in revisione (HUMAN)**: osservato su documenti reali (INVOICE_SCAN_ACQUISITION_001) — righe di una foto accorpate o spostate (quantità di una riga su un'altra), subtotali di sezione ("Cooler", "Dry", "TOTAL WEIGHT") letti come righe, più nomi di fornitore letti dallo stesso documento (logo, blocco "remit to"), unità di misura letta solo quando la colonna ha un'etichetta riconoscibile. Il controllo esatto degli importi e il controllo quantità × prezzo le rendono visibili; la correzione resta umana.
- Una **fattura in più file** (es. pagina 1 e pagina 2 fotografate o scansionate separatamente) non può essere caricata come un'unica fattura: ogni file è un'acquisizione a sé (resta da completare in revisione).
- La lettura digitale (PDF con testo) non estrae il destinatario ("Bill to/Ship to"); termini e scadenza solo se etichettati. Textract li estrae.
- Subtotale, imposte, sconto, trasporto, supplementi, pagato e saldo sono conservati con l'acquisizione (`data/document_acquisitions.db`) e consultabili/correggibili in revisione, ma non hanno colonne nel Purchase Fact canonico (fuori perimetro dell'acquisizione).
- Un codice articolo fornitore letto crea il Supplier Product in Purchased; un articolo non classificato rende HUMAN il documento (regola di Purchased).
- `/review/login` non è un login reale (Identity & Access congelato): registra solo nome e ruolo dichiarati.
- Il parsing delle righe digitali resta euristico (espressioni regolari); il `line_type` (Prodotto/Supplemento/Sconto) è proposto per parole chiave e correggibile in revisione.
- Non fa normalizzazione in grammi/costo per grammo né mapping verso gli Ingredienti; nessuna selezione del Restaurant (multi-tenant); un solo utente alla volta.
