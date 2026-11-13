# Prova estesa — lettura diretta delle fatture scansionate

**Eseguita:** 2026-10-11/12, sessione Claude Code (modello `claude-opus-5-5`). **Stato:** prova isolata — nessun dato
inserito nelle tabelle operative, motore di Intake non modificato.

## Metodo

* Originali: `AI-RF-ONE/Documents/Invoices/<Supplier>/` (15 file, 3 copie identiche per SHA-256 → 12 file distinti,
  15 pagine distinte), resi a 300 dpi con Poppler (`render_pages.py` → `pagine/`, `campione.json`).
* Lettura **diretta** delle pagine (intera, poi ritagli ingranditi e ruotati) da parte della sessione. **Nessuna**
  chiamata a Textract, Bedrock o altre API di riconoscimento; **nessuna** trascrizione precedente usata come input
  (la prova precedente del 2026-10-10 è conservata, non letta, in `_Esecuzione precedente 2026-10-10 (non usata)/`).
* Nessun completamento dalla scheda prodotto: si registra solo ciò che è stampato.
* `letture_dirette.py` contiene **solo valori letti** e, per ogni campo interpretato, il motivo (`uncertain`).
  `make_pdfs.py` calcola i controlli (valori **calcolati**, sempre etichettati), classifica le lacune (scheda
  prodotto / persona) e produce i risultati.

## Risultati

| File | Contenuto |
|---|---|
| `PDF/<Supplier> <numero> - <data>.pdf` | **Risultato principale**, uno per fattura: tabella dei dati letti (celle incerte evidenziate), charges con segno, righe non consegnate, dati mancanti o incerti con chi può risolverli, esito dei controlli, tutte le pagine originali (raddrizzate se scansionate ruotate). |
| `fatture.json` | Dati strutturati con i nomi dei campi dello schema Invoice Intake (`purchase_documents`, `purchase_lines`, `purchase_document_sources`, PURCHASING.md §13), riferimenti a file/pagina/SHA-256, controlli e lacune. |
| `campione.json` | Inventario del campione: file, duplicati, pagine. |

## Riprodurre

```powershell
python render_pages.py   # pagine/ e campione.json (richiede Poppler: pdfinfo, pdftoppm)
python make_pdfs.py      # fatture.json e PDF/ (richiede Pillow e Chrome o Edge per la stampa in PDF)
```

Le letture non si rigenerano da script: sono la lettura diretta della sessione, registrata in `letture_dirette.py`.
