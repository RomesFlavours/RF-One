# Invoice Intake (prototipo)

**Nota canonica (TASK_PURCHASING_004):** a partire da questo task, il salvataggio finale avviene nel **RF-One Data Store** (`03 Software/RF-One Data Store/`), che implementa persistentemente il modello canonico `01 Domains/Restaurant/Purchasing/` (Purchase Document / Purchase Line, con `line_type` PRODUCT/SURCHARGE/DISCOUNT e Merchandise/Economic Classification). Il file Excel (`data/PurchaseDocuments.xlsx`) resta disponibile solo come copia di debug/esportazione secondaria — non è più lo store canonico. Vedi `03 Software/RF-One Data Store/PURCHASING.md` per i dettagli implementativi.

Piccola web app locale per validare il flusso: carichi una fattura (foto o PDF), l'app la legge, tu correggi/completi i dati (incluso il tipo di riga: Prodotto/Supplemento/Sconto) in una schermata di revisione, e alla conferma il documento viene registrato nel RF-One Data Store come Purchase Document/Purchase Line canonici.

## Come funziona la lettura

- **PDF con testo digitale** (fatture generate al computer): il testo viene estratto direttamente, in modo pulito e affidabile.
- **Foto/scansioni** (jpg, png, PDF scansionati): viene usato OCR locale (Tesseract), gratuito e offline. Su foto storte, sbiadite o con tabelle complesse la qualità di lettura è limitata — è normale dover correggere diversi campi a mano nella schermata di revisione. Per questo la revisione è un passaggio obbligato, non opzionale: coerente con il principio "human validation always prevails" del modulo Purchasing.

Testato con i due esempi in `01 Domains/Restaurant/Assets/ReferenceDocuments/`: la fattura PDF digitale (`Invoice 6855.pdf`) viene letta quasi perfettamente (fornitore, numero, data, totale, tutte le righe); le foto scattate al telefono vengono lette solo parzialmente e richiedono correzioni manuali.

## Requisiti

- Python 3.10 o superiore
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installato (su Windows: scarica l'installer, e assicurati che `tesseract.exe` sia nel PATH di sistema)
- Facoltativo: [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases) se vuoi che funzioni anche il fallback OCR per PDF scansionati (non serve per PDF con testo digitale)
- Le dipendenze di `03 Software/RF-One Data Store/` (SQLAlchemy, Alembic — vedi il suo `requirements.txt`), poiché `purchasing_bridge.py` importa `rfone_data_store` da lì

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

Poi apri il browser su **http://127.0.0.1:5000**

## Dove finiscono i dati

Ogni fattura confermata viene salvata nel RF-One Data Store (SQLite locale per default: `03 Software/RF-One Data Store/data/rfone.db`, creato/aggiornato automaticamente tramite le migration Alembic esistenti — vedi `03 Software/RF-One Data Store/README.md`). La schermata finale mostra il `PurchaseDocumentId` canonico assegnato.

`data/PurchaseDocuments.xlsx` continua a essere aggiornato come copia di debug/esportazione secondaria ad ogni salvataggio (append, non sovrascrive) — utile per un controllo visivo rapido, ma non è più la fonte di verità. Se il file è aperto in Excel al momento del salvataggio, il salvataggio canonico nel RF-One Data Store avviene comunque; solo la copia Excel potrebbe fallire silenziosamente (messaggio informativo nella schermata di conferma).

Le immagini/PDF caricati restano salvati in `uploads/` per tracciabilità. **Nota:** `uploads/` e `data/PurchaseDocuments.xlsx` contengono documenti fornitore reali/dati generati e non sono tracciati da Git (vedi `.gitignore` alla radice del repository) — solo i placeholder `.gitkeep` restano versionati.

## Limiti noti di questo prototipo

- Il parsing delle righe (descrizione/quantità/prezzo/importo) è basato su euristiche ed espressioni regolari, non su un modello AI: funziona bene su testo pulito, meno su OCR rumoroso.
- Il `line_type` (Prodotto/Supplemento/Sconto) viene proposto con un'euristica su parole chiave nella descrizione (es. "surcharge", "fee" → Supplemento; "discount", "credit" → Sconto) ma è sempre correggibile dall'utente prima del salvataggio.
- L'OCR/parser non estrae ancora un codice articolo fornitore strutturato, quindi le righe PRODUCT create da qui non alimentano ancora la "Supplier Product memory" (riconoscimento automatico dello stesso Supplier Product a fatture successive) — il modello e il repository lo supportano già pienamente quando un codice è disponibile (es. da Physical Receiving); vedi `03 Software/RF-One Data Store/PURCHASING.md`, "Remaining gaps".
- Non fa ancora normalizzazione in grammi/costo per grammo né mapping automatico verso gli Ingredienti — è il passo successivo naturale, coerente con `01 Domains/Restaurant/Purchasing/DataDictionary.md`.
- Non offre ancora una selezione del Restaurant/organizzazione (multi-tenant); riusa l'unico Restaurant esistente nello store o ne crea uno placeholder.
- Un solo utente alla volta (nessuna gestione concorrenza sul salvataggio).
