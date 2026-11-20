# Prova estesa lettura diretta (2026-10-10)

Lettura diretta delle fatture scansionate in `AI-RF-ONE/Documents/Invoices/`, fatta dal Mulo nella sessione
Claude Code: pagine renderizzate in locale (pypdfium2), ruotate e ingrandite, lette a vista.
**Nessuna chiamata a Textract, Bedrock o altre API di riconoscimento; nessuna trascrizione precedente usata.**
Prova isolata: nulla è stato scritto nelle tabelle operative e il motore di Intake non è stato modificato.

## Contenuto della cartella

| File | Ruolo | In Git |
|---|---|---|
| `PDF/*.pdf` | **Risultato principale**: un PDF per fattura (pagine originali, dati estratti, dati mancanti/incerti, controlli) | no (`.gitignore`: contenuto di fatture reali) |
| `letture.json` | La lettura strutturata (campi coerenti con `purchase_lines` / PURCHASING.md §13, con riferimento a file e pagina) | no |
| `controlli.json` | Esito dei controlli calcolati da `make_pdfs.py` | no |
| `make_pdfs.py` | Rigenera PDF e controlli da `letture.json` + originali; nessuna chiamata esterna | sì |

Riprodurre: `python make_pdfs.py` (originali cercati in `<AI-RF-ONE>/Documents/Invoices`, oppure passare la
cartella come primo argomento).

## Convenzioni dei dati

- **Campi della riga** (stessi nomi di `purchase_lines`): solo valori **letti**. `null` = non stampato.
- `interpretations`: valori dedotti o incerti, mai scritti nei campi letti (nel PDF in blu, `[i]`).
- `calculations`: valori ottenuti con un calcolo da valori stampati (nel PDF in marrone, `[c]`).
- `flags.resolvable_by`: `PRODUCT_CARD` = la scheda prodotto potrebbe risolverlo; `PERSON` = serve una persona
  o il documento mancante.
- Confezione: la stringa stampata resta com'è (`2x2 LB`, `12/32 OZ`); pezzi per confezione e contenuto del pezzo
  sono la sua scomposizione. Quantità acquistata e contenuto della confezione non vengono mai moltiplicati.
- Charges: righe `SURCHARGE` (nome e importo con segno, come stampati); sconti già inclusi nella riga non sono
  charges e non vengono sottratti di nuovo.
- Nessun completamento dalla scheda prodotto.

## Campione

15 file, 18 pagine; 3 coppie di file identici byte per byte → 12 file distinti, 15 pagine distinte; 1 file
(Cheney, nuova scansione) è un duplicato di contenuto. **12 documenti distinti** (10 fatture, 2 scontrini),
125 righe articolo. Il file `Keith/2026-10-10_093150.pdf` contiene le pagine 1 di **due** fatture diverse.
Pagine mancanti: la pagina 2 di Gordon 9039354564, Keith 57978854, Keith 58188774, Keith 58049702.

## Esito sintetico

Tutti i controlli aritmetici possibili tornano (righe, subtotali di sezione, totali di pagina e di fattura,
quantità e pesi totali, imposte Gordon). Dove manca la pagina 2 il totale fattura non è verificabile.
Una somma che torna è un controllo di coerenza, non una garanzia: manca un confronto indipendente, quindi
nessuna accuratezza percentuale è dichiarata.
