# Invoice Intake (prototipo)

**Nota canonica (Align legacy Invoice Intake with Purchased, evolve di TASK_PURCHASING_004):** Invoice Intake è il processo che alimenta **Purchased** (`01 Domains/Shared Domains/Purchased/README.md`), lo Shared Domain proprietario del Purchase Fact (capture + normalize + publish). Il salvataggio finale avviene nel **RF-One Data Store** (`03 Software/RF-One Data Store/`, tramite `purchased_bridge.py`), che persiste il Purchase Document / Purchase Line (`line_type` PRODUCT/SURCHARGE/DISCOUNT) — lo stesso schema introdotto da TASK_PURCHASING_004, riusato as-is (nessuna tabella nuova). **Restaurant/Purchasing consuma** questo Purchase Fact per le proprie decisioni (Purchase Order, Configured Expectation, Physical Receiving, Reconciliation, Alert) — non lo possiede più, e non è mai un prerequisito per crearlo. Il file Excel (`data/PurchaseDocuments.xlsx`) resta disponibile solo come copia di debug/esportazione secondaria. Vedi `03 Software/RF-One Data Store/PURCHASING.md` per i dettagli implementativi.

Piccola web app locale per validare il flusso: carichi una fattura (foto o PDF), l'app la legge, tu correggi/completi i dati (incluso il tipo di riga: Prodotto/Supplemento/Sconto) in una schermata di revisione, e alla conferma il documento viene registrato come Purchase Fact canonico. `purchased_bridge.py` calcola anche lo stato funzionale **NORMALIZED/HUMAN** (Purchased/README.md) e riconosce documenti duplicati/correzioni fornitore (Credit Memo, Corrected Invoice, ecc.) — vedi PURCHASING.md, §5.

**Acquisizione via email (`mailbox_acquisition/`):** oltre al caricamento manuale, Invoice Intake acquisisce fatture direttamente dalla casella **`invoices@romesflavours.com`** (mailbox operativa Aruba di Rome's Flavours) — un processo continuo/configurabile che scarica gli allegati documentali di ogni nuovo messaggio e li consegna a questa stessa pipeline (OCR/parser/`purchased_bridge.py`), senza saltarla. Vedi `mailbox_acquisition/README.md` per configurazione e comportamento (idempotenza, provenance, retry).

## Come funziona la lettura

- **PDF con testo digitale** (fatture generate al computer): il testo viene estratto direttamente, in modo pulito e affidabile.
- **Foto/scansioni** (jpg, png, PDF scansionati): viene usato OCR locale (Tesseract), gratuito e offline. Su foto storte, sbiadite o con tabelle complesse la qualità di lettura è limitata — è normale dover correggere diversi campi a mano nella schermata di revisione. Per questo la revisione è un passaggio obbligato, non opzionale: coerente con il principio "human validation always prevails" del modulo Purchasing.

Testato con i due esempi in `01 Domains/Cross Domain/Administration/Invoice Intake/Invoices/Raw/`: la fattura PDF digitale (`Invoice 6855.pdf`) viene letta quasi perfettamente (fornitore, numero, data, totale, tutte le righe); le foto scattate al telefono vengono lette solo parzialmente e richiedono correzioni manuali.

## Requisiti

- Python 3.10 o superiore
- **Tesseract OCR** — necessario per leggere JPG/PNG/TIFF e PDF scansionati (i PDF con testo digitale non ne hanno bisogno, vedi "PDF digitale vs PDF scansionato" sotto). Su Windows, via [winget](https://learn.microsoft.com/windows/package-manager/winget/):
  ```
  winget install --id UB-Mannheim.TesseractOCR
  ```
  oppure scarica l'installer da [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) — assicurati che `tesseract.exe` sia nel PATH di sistema (il pacchetto winget lo richiede esplicitamente in un secondo momento; se non lo fa in automatico, aggiungi `C:\Program Files\Tesseract-OCR` al PATH utente).
- **Poppler** — necessario per il fallback OCR sui PDF scansionati (rende ogni pagina come immagine prima di passarla a Tesseract; non serve per PDF con testo digitale). Su Windows, via winget:
  ```
  winget install --id oschwartz10612.Poppler
  ```
  oppure scarica da [oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases) — assicurati che la cartella `bin` (contiene `pdftoppm.exe`) sia nel PATH.
- Le dipendenze Python già in `requirements.txt` (`pytesseract`, `pdfplumber`, `pdf2image`, ecc.) — `pip install -r requirements.txt`.
- Le dipendenze di `03 Software/RF-One Data Store/` (SQLAlchemy, Alembic — vedi il suo `requirements.txt`), poiché `purchased_bridge.py` importa `rfone_data_store` da lì

### PDF digitale vs PDF scansionato

`ocr_engine.py` distingue sempre i due casi, senza bisogno di configurazione: un **PDF digitale** (testo incorporato, es. fatture generate al computer) viene letto direttamente con `pdfplumber` — veloce, accurato, non serve Tesseract/Poppler. Solo quando il testo incorporato è assente o insufficiente (**PDF scansionato/fotografato**) scatta il fallback: `pdf2image`/Poppler rasterizza le pagine, poi Tesseract le legge via OCR. Questo comportamento non è stato modificato da questo task.

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
python app.py
```

Poi apri il browser su **http://127.0.0.1:5000** — la vista `/mailbox` mostra le fatture acquisite via email.

## Avvio dell'acquisizione email (opzionale)

```
python run_mailbox_acquisition.py          # loop continuo (30–60s configurabile)
python run_mailbox_acquisition.py --once   # un solo ciclo, poi esce
```

Richiede `ARUBA_IMAP_USERNAME`/`ARUBA_IMAP_PASSWORD` (vedi `.env.example` alla radice del repository) — vedi `mailbox_acquisition/README.md`, inclusa la sezione su come vengono riconosciuti e ignorati logo/firme email inline (mai un vero allegato di fattura).

## Dove finiscono i dati

Ogni fattura confermata viene salvata nel RF-One Data Store (SQLite locale per default: `03 Software/RF-One Data Store/data/rfone.db`, creato/aggiornato automaticamente tramite le migration Alembic esistenti — vedi `03 Software/RF-One Data Store/README.md`). La schermata finale mostra il `PurchaseDocumentId` canonico assegnato e lo stato funzionale **NORMALIZED** o **HUMAN** (Purchased/README.md). **La lettura tramite OCR non implica più HUMAN di per sé** (dal task "Improve Generic Parser and Prepare Supplier Format Training") — la decisione dipende solo dalla completezza/coerenza dei campi estratti: fornitore riconosciuto, data riconosciuta, totale riconosciuto (un totale $0.00 non conta come riconosciuto), nessun totale in conflitto, righe che tornano aritmeticamente con il totale quando presenti. HUMAN quando anche uno solo di questi controlli fallisce, o quando l'identità fattura è in conflitto con un documento già registrato.

Una fattura già registrata, ricaricata di nuovo (stesso fornitore/numero/data/totale, magari da un altro canale), non crea un secondo Purchase Fact: viene riconosciuto come duplicato e restituito il `PurchaseDocumentId` esistente. Un Credit Memo/Corrected Invoice/Return Credit/Adjustment selezionato come "Tipo documento" viene invece registrato come nuovo documento collegato all'originale (correzione fornitore, mai una riscrittura del fatto precedente).

`data/PurchaseDocuments.xlsx` continua a essere aggiornato come copia di debug/esportazione secondaria ad ogni salvataggio (append, non sovrascrive) — utile per un controllo visivo rapido, ma non è più la fonte di verità. Se il file è aperto in Excel al momento del salvataggio, il salvataggio canonico nel RF-One Data Store avviene comunque; solo la copia Excel potrebbe fallire silenziosamente (messaggio informativo nella schermata di conferma).

Le immagini/PDF caricati restano salvati in `uploads/` per tracciabilità. **Nota:** `uploads/` e `data/PurchaseDocuments.xlsx` contengono documenti fornitore reali/dati generati e non sono tracciati da Git (vedi `.gitignore` alla radice del repository) — solo i placeholder `.gitkeep` restano versionati.

## Riconoscimento fornitore + Supplier Format Training (foundation)

`supplier_format_training.py` registra, per ogni coppia (Fornitore, formato sorgente — es. "OCR", "PDF-Text"), quanti documenti sono stati osservati e con quale esito NORMALIZED/HUMAN — un local store separato, solo osservativo. **Non valida ancora automaticamente nessun fornitore**: `trust_state` resta sempre `UNTRAINED`, nessuna soglia N è definita, nessuna promozione automatica esiste. È la base su cui una futura decisione di prodotto potrà costruire una vera fiducia per-fornitore/formato — vedi `03 Software/RF-One Data Store/PURCHASING.md`, §11.

Il riconoscimento del nome fornitore (`purchased_bridge._resolve_supplier_name`) preferisce sempre il testo del documento stesso; usa i Supplier già noti nel database solo per riconoscere alias dello stesso fornitore reale (es. "COSTCO" vs "Costco Wholesale #183"); usa il nome del file solo come **evidenza secondaria**, mai come fonte primaria, e non inventa mai un'identità fornitore che non sia già nota o presente nel testo.

## Limiti noti di questo prototipo

- **Il training dei fornitori (supplier training) viene dopo, non prima, di questo passo.** Questo prototipo diventa affidabile solo una volta che Tesseract/Poppler sono realmente installati (vedi "Requisiti" sopra) — senza di essi, ogni documento non digitale finisce comunque HUMAN, per mancanza di campi riconoscibili.
- Il parsing delle righe (descrizione/quantità/prezzo/importo) è basato su euristiche ed espressioni regolari, non su un modello AI: funziona bene su testo pulito, meno su OCR rumoroso. Lo stesso vale per fornitore/data/numero/totale: l'euristica generica riconosce bene i formati comuni osservati nei documenti reali, ma resta imperfetta su scansioni di bassa qualità o layout insoliti — corretto per design (HUMAN quando incerta), non un bug da correggere qui.
- Il `line_type` (Prodotto/Supplemento/Sconto) viene proposto con un'euristica su parole chiave nella descrizione (es. "surcharge", "fee" → Supplemento; "discount", "credit" → Sconto) ma è sempre correggibile dall'utente prima del salvataggio.
- L'OCR/parser non estrae ancora un codice articolo fornitore strutturato, quindi le righe PRODUCT create da qui non alimentano ancora la "Supplier Product memory" (riconoscimento automatico dello stesso Supplier Product a fatture successive) — il modello e il repository lo supportano già pienamente quando un codice è disponibile (es. da Physical Receiving); vedi `03 Software/RF-One Data Store/PURCHASING.md`, "Remaining gaps".
- Non fa ancora normalizzazione in grammi/costo per grammo né mapping automatico verso gli Ingredienti — è il passo successivo naturale, coerente con `01 Domains/Business Domain/Restaurant/Purchasing/DataDictionary.md`.
- Non offre ancora una selezione del Restaurant/organizzazione (multi-tenant); riusa l'unico Restaurant esistente nello store o ne crea uno placeholder.
- Un solo utente alla volta (nessuna gestione concorrenza sul salvataggio).
