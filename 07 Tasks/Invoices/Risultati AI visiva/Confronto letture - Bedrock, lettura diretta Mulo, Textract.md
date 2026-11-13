# Confronto letture fatture — Bedrock, lettura diretta del Mulo, Textract

Aggiornato: 2026-09-27. Prova isolata, nessuna integrazione in RF-One.

**Riferimento:** gli originali, letti a vista ad alta risoluzione. La lettura diretta del Mulo è una ulteriore lettura, verificata con controlli aritmetici, non una verità assoluta.

**Fonti**
| Fonte | Keith | Gordon | Cheney |
|---|---|---|---|
| Bedrock (lettura AI indipendente) | Claude Opus 4.6, completa | Claude Sonnet 4.6, **incompleta** (troncata) | Claude Sonnet 4.6, completa |
| Lettura diretta Mulo (senza chiamate esterne) | — | completa, 16 righe | — |
| Textract AnalyzeExpense (risposte già salvate) | sì | sì | sì |

**Classificazione usata**
- **Letto** = valore stampato nell'originale.
- **Inferenza** = dedotto (da calcoli, simboli o contesto), mai presentato come stampato.
- **Omesso** = presente nell'originale ma non restituito.
- **Campo generico** = testo letto ma senza significato (Textract `OTHER`).
- **Errore** = valore o significato sbagliato.

---

## Keith — Ben E. Keith, 08/26/2026, pagina 1 di 2

| Dato | Originale | Bedrock (Opus 4.6) | Textract |
|---|---|---|---|
| Supplier | logo KEITH; "Ben E. Keith Foods" nel testo | Letto: "Ben E. Keith Co." | Letto, ma VENDOR_NAME doppio: "Ben E. Keith Lockbox," / "KEITH CO." |
| Data | 08/26/2026 | Letto ✔ | Letto ✔ |
| 9 articoli: casse o pkgs, confezione, costo, importo | stampati | Letti 9/9 ✔ | Letti 9/9 ✔; confezione in campo generico |
| Yeast: 1 in colonna Pkgs | stampato | Letto ✔ (distinto dalle casse) | Letto ✔ (QUANTITY con etichetta Pkgs) |
| Base del prezzo | **non stampata** | Non determinata ✔ (moltiplicazioni dichiarate come calcolate) | assente |
| Fuel Charge +8.75 | stampato | Letto come charge ✔ | Campo generico (summary OTHER) |
| Subtotali di sezione | stampati | Esclusi ✔ | **Errore:** "Cooler 296.85" e "Dry 125.69" restituiti come righe articolo |
| Pagina 2 | "Page 1 of 2", "Continued" | Segnalata ✔ | Campo generico, non interpretato |

- **Bedrock, inferenze fuori luogo:** dubbio che la data 2026 sia un refuso. È un pregiudizio del modello; il valore riportato resta quello stampato.
- **Bedrock, dati inventati:** nessuno.

## Gordon — Gordon Food Service, 08/26/2026, pagina 1 di 2

| Dato | Originale / Lettura diretta Mulo | Bedrock (Sonnet 4.6) | Textract |
|---|---|---|---|
| Supplier / data | Gordon Food Service Inc. / 08/26/2026 | Letti ✔ | Letti ✔ (VENDOR_NAME doppio) |
| Articoli | **16** righe stampate | Letti 15 ✔; **omesso** 256463 Rinse Aid 209.49 (troncamento) | Letti 16/16 ✔ |
| Q.tà ordinata / consegnata | stampate, distinte | Lette ✔ | Lette ✔, ma tipizzazione incoerente (Qty Ord in OTHER nelle prime 10 righe, QUANTITY nelle altre) |
| Casse | Unit = CS stampato → casse = Q.tà cons. | **Omesso:** campo casse vuoto nonostante CS | QUANTITY + Unit in OTHER |
| Pezzi, peso effettivo | **non stampati** | Non determinati ✔ | assenti ✔ |
| Base del prezzo | **non dichiarata**; "per CS" è un'**inferenza** (Unit = CS e Q.tà × costo = importo) | "per CS, as indicated by 'CS' in the Unit column": l'inferenza è presentata come indicazione del documento | assente |
| Inv Value | stampato, significato non stampato | Tenuto separato; relazione presentata come calcolata ✔ | **Errore:** tipizzato UNIT_PRICE in 7 righe → due prezzi per riga (es. 5.00 e 59.99) |
| Promo 34.65 già inclusa (672312) | stampata sotto la riga | Letta, non risottratta ✔ | **Omessa** nella riga |
| Charges | **nessuno stampato a pagina 1**; pagina 2 non determinabile | Omessi (troncamento) | nessuno ✔ |
| Pagina 2 | "Page 1 of 2" | **Omesso** nella risposta (visto solo nel ragionamento) | Campo generico; "Page Total 1004.30" tipizzato TOTAL (fuorviante) |

- **Controllo della lettura diretta:** in tutte le 16 righe Q.tà × costo unitario = importo; 197.86 + 596.95 + 209.49 = 1004.30 = Page Total. Sono calcoli, non dati stampati.
- **Bedrock, dati inventati:** nessuno.

## Cheney — Cheney Brothers, 08/19/26

| Dato | Originale | Bedrock (Sonnet 4.6) | Textract |
|---|---|---|---|
| Supplier | Cheney Brothers | Letto ✔ | Letto ✔ ("C-B-I Cheney Brothers") |
| Data | caselle MO/DAY/YR: 08 / 19 / 26 | Letto ✔ | **Omesso come data:** tre campi OTHER separati; "SALESPERSON = DUE: 08/27/2026" etichettato male |
| Olio: 4 casse, 002/1 GAL, 120.88, 483.52 | stampati | Letti ✔ | Letti ✔ |
| Olio: base del prezzo | "CS" stampato dopo 120.88 | Letto: per cassa ✔ | **Omesso** ("CS" fuso nel brand "FRONTE CS p") |
| Olio: peso | **65.00, unità non stampata** | "65.00 lb": **inferenza presentata come valore letto** → *corretta nella presentazione* (65.00, unità non determinata) | 65.00 in campo generico ✔ senza unità |
| Salame: 2 casse, 003/2.5 # AVG, 16.08, 8.98, 144.40 | stampati | Letti ✔ | Letti ✔ (peso in campo generico) |
| Salame: base del prezzo | "#" stampato dopo 8.98 | Letto il simbolo; "per lb" = interpretazione standard di "#" | **Omesso** ("#" perso) |
| Salame: unità del peso | **non stampata** accanto a 16.08 | "16.08 lb": inferenza (da "#") → *indicata come inferenza nella presentazione* | assente |
| Pesi 8.15 / 7.93 | stampati | Letti; "per cassa" = inferenza, dichiarata come tale (8.15 + 7.93 = 16.08) ✔ | Letti in campo generico ("ck'd by") |
| Fuel surcharge +7.00 | stampato | Letto come un solo charge ✔; riepilogo escluso ✔ | Campo generico, **più** "TOTAL DISCOUNT/SURCHARGE 7.00" tipizzato **DISCOUNT** (segno e doppio conteggio a rischio) |

- **Correzione di presentazione:** la risposta originale del modello è intatta in `Risposte modello/Cheney_answer.txt`. Il PDF Bedrock mostra in rosso il valore corretto e sotto il valore restituito dal modello.
- **Bedrock, dati inventati:** nessuno.

---

## Sintesi

| | Bedrock | Textract |
|---|---|---|
| Errori sui valori stampati | nessuno | nessuno sui numeri degli articoli |
| Omissioni | Gordon: 1 riga, charges e pagina mancante (troncamento), campo casse; nient'altro | base del prezzo (Cheney), promo (Gordon), data Cheney come data |
| Inferenze presentate come lette | 2 unità di peso "lb" (Cheney, corrette in presentazione); base "per CS" su Gordon formulata come indicazione del documento | nessuna (Textract non inferisce) |
| Errori di significato / tipizzazione | nessuno | subtotali come articoli (Keith), due prezzi per riga (Gordon), supplemento come DISCOUNT (Cheney), Page Total come TOTAL |
| Dati in campi generici | — | confezione, peso, fuel charge, pagine, parti della data |

**Interpretazione:** entrambe le letture automatiche riportano correttamente i numeri stampati. Bedrock aggiunge il significato (base del prezzo, subtotali, segni, sconti già inclusi). Il suo rischio è di formulare come lettura qualche inferenza e di troncare l'output. Textract non inventa nulla, ma lascia molto in campi generici e sbaglia alcune classificazioni con impatto contabile.
