# Invoice Intake (prototipo)

Piccola web app locale per validare il flusso: carichi una fattura (foto o PDF), l'app la legge, tu correggi/completi i dati in una schermata di revisione, e alla conferma vengono aggiunti a un file Excel (`data/PurchaseDocuments.xlsx`), con due fogli: `PurchaseDocuments` e `PurchaseLines`.

Le colonne seguono lo schema di `Purchasing/DataDictionary.md` nella Knowledge Repository (Purchase Document / Purchase Line), con qualche colonna extra per tracciabilità (`SourceFile`, `CreatedAt`).

## Come funziona la lettura

- **PDF con testo digitale** (fatture generate al computer): il testo viene estratto direttamente, in modo pulito e affidabile.
- **Foto/scansioni** (jpg, png, PDF scansionati): viene usato OCR locale (Tesseract), gratuito e offline. Su foto storte, sbiadite o con tabelle complesse la qualità di lettura è limitata — è normale dover correggere diversi campi a mano nella schermata di revisione. Per questo la revisione è un passaggio obbligato, non opzionale: coerente con il principio "human validation always prevails" del modulo Purchasing.

Testato con i due esempi nella Knowledge Repository: la fattura PDF digitale (`Invoice 6855.pdf`) viene letta quasi perfettamente (fornitore, numero, data, totale, tutte le righe); le foto scattate al telefono vengono lette solo parzialmente e richiedono correzioni manuali.

## Requisiti

- Python 3.10 o superiore
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installato (su Windows: scarica l'installer, e assicurati che `tesseract.exe` sia nel PATH di sistema)
- Facoltativo: [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases) se vuoi che funzioni anche il fallback OCR per PDF scansionati (non serve per PDF con testo digitale)

## Installazione

Apri un terminale nella cartella del progetto:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Avvio

```
python app.py
```

Poi apri il browser su **http://127.0.0.1:5000**

## Dove finiscono i dati

`data/PurchaseDocuments.xlsx` — si crea automaticamente al primo salvataggio e cresce ad ogni fattura successiva (append, non sovrascrive). Aprilo con Excel per controllare i dati in qualsiasi momento; l'app può restare aperta mentre lo consulti (chiudi il file in Excel prima di salvare una nuova fattura, altrimenti Windows potrebbe bloccarne la scrittura).

Le immagini/PDF caricati restano salvati in `uploads/` per tracciabilità.

## Limiti noti di questo prototipo

- Il parsing delle righe (descrizione/quantità/prezzo/importo) è basato su euristiche ed espressioni regolari, non su un modello AI: funziona bene su testo pulito, meno su OCR rumoroso.
- Non fa ancora normalizzazione in grammi/costo per grammo né mapping automatico verso gli Ingredienti — è il passo successivo naturale, coerente con `Purchasing/DataDictionary.md`.
- Un solo utente alla volta (nessuna gestione concorrenza sul file Excel).
