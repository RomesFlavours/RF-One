# C-Bank — Functional Specification v1

RF-One | 21 ottobre 2026 | Stato: specifica approvata, non implementata

> Copia del documento fornito dal Product Owner il 2026-10-21 (sorgente di autorità del C-Bank Prototype).

## 1. Obiettivo e confini

Sanare i movimenti 1 gennaio–31 ottobre 2026, includendo pagamenti personali e business utilizzati promiscuamente, identificando origine del pagamento, beneficiario economico, controparte, natura e destinazione gestionale/contabile. Consegnare Excel separati per LLC con rapporti reciproci e anomalie, e alimentare un futuro dominio Management Control. Prevenire il ripetersi delle commistioni mediante controlli automatici ex post.

Fonte dei requisiti: 58 scelte esplicite dell’utente durante l’intervista. Il documento descrive comportamento desiderato; non certifica che il software attuale lo realizzi.

## 2. Modello dati concettuale

- Bank Transaction: identificativo stabile, fonte import, conto/carta, titolare del conto, data, importo, segno, descrizione, valuta, hash/dedup, originale immutabile.
- Entity: LLC/persona con identificativo canonico; Account/Card appartenente a Entity. Beneficiary Entity attribuito separatamente dalla fonte.
- WHO: controparte canonica; WHY: natura economica; Category RF-One: categoria gestionale; QB Account: mappatura contabile; WHAT legacy corrisponde a accounting_classification_id, da verificare nella migrazione.
- Operation Type: operating expense/income, capital asset, financing, inter-account transfer, card settlement, inter-entity advance/repayment, investment, other patrimonial operation.
- Classification Decision: valori, stato, metodo (rule/AI/human), evidenze, confidenza giustificata, timestamp, versione e storico.
- Recognition Profile: uno per WHO, condizioni per LLC e contesto, più branche WHY/WHAT; regole di estrazione WHO tenute distinte dai profili.
- Inter-entity ledger: soggetto pagante, beneficiario, credito/debito proposto, riferimenti ai movimenti e abbinamenti dei rimborsi; qualificazione contabile soggetta a verifica.
- Accounting import/match: GL/COA QuickBooks importati, corrispondenze, differenze, eccezioni; nessuna scrittura su QB.
- Period close: anno-mese, esito, approvazione, snapshot immutabile, esportazioni, rettifiche successive registrate a parte.

## 3. Processo unico AI — comportamento target

1. Importare senza duplicare e conservare sempre l’originale; far partire automaticamente la riconciliazione dei nuovi movimenti.
1. Applicare regole WHO esistenti e memoria; risolvere conflitti con AI solo su evidenze adeguate; in dubbio chiedere.
1. Determinare beneficiario indipendentemente dal mezzo di pagamento; verificare natura dell’operazione e WHO contestuale.
1. Applicare Recognition Profile unico per WHO con branche condizionali per beneficiario e contesto; trovare WHY, categoria RF-One e corrispondenza QB.
1. Se informazioni incomplete, investigare in gruppi con storico, ricevute e altri domini autorizzati; modale con campi e conversazione libera e domande mirate.
1. Se classificazione sufficientemente supportata, registrarla come automatica e auditabile; decisioni umane protette.
1. Proporre regole nuove e correzioni retroattive ma richiedere approvazione; nuova conoscenza rivaluta subito soltanto movimenti irrisolti.
1. Abbinare trasferimenti e pagamenti carte senza doppia contabilizzazione; annotare anticipazioni fra soggetti e proporre compensazioni.
1. Marcare Reconciled al completamento dei campi pertinenti, senza attendere QuickBooks; chiusura mensile solo con tutti i movimenti Reconciled e conferma del titolare.

## 4. Inventario decisioni approvate (1–58)

01. Attribuzione. Ogni costo attribuito al beneficiario economico; se pagato da altro soggetto nasce un credito verso il beneficiario.
02. Un solo beneficiario. Ogni movimento bancario ha un solo beneficiario; ripartizioni eventuali mediante rettifiche separate.
03. Beneficiario AI. Beneficiario identificato da conto, WHO, descrizione, storico, regole e contesto; chiedere in caso incerto.
04. Recognition Profiles intelligenti. Un WHO può avere più classificazioni WHY/WHAT condizionate da contesto, descrizione e storico.
05. Autonomia AI. Classificare anche casi nuovi quando le evidenze sono sufficientemente affidabili.
06. Correzioni retroattive. Individuare movimenti analoghi e proporre correzioni retroattive, applicabili solo con approvazione.
07. Rimborsi. Riconoscere trasferimenti di rimborso e proporre estinzione del credito/debito, senza nuovi costi.
08. Confronto QuickBooks. Classificazioni Bank confrontate con registrazioni QB; evidenziare omissioni, discrepanze e duplicati.
09. Categorie due livelli. Categorie gestionali RF-One dettagliate mappate al Chart of Accounts di QuickBooks.
10. Integrazione RF-One. Bank può consultare Invoice Intake, MyRF Projects e altri domini pertinenti.
11. Investigazione prima di chiedere. Esaminare autonomamente evidenze e fare solo domande mirate sul non risolto.
12. Apprendimento approvato. Memorizzare spiegazioni; proporre regole permanenti da approvare prima di attivarle.
13. Export completo. Excel con transazioni, anomalie, divergenze QB, anticipazioni.
14. Rapporti reciproci. Gestire anticipazioni in entrambe le direzioni LLC↔persone e LLC↔LLC, con proposte di compensazione.
15. Documenti come evidenza. Distinguere spese personali/aziendali anche tramite fatture, ricevute e altri domini.
16. Controllo ex post. Controllare automaticamente incongruenze conto-beneficiario dopo import; gestire eccezioni.
17. Dashboard eccezioni. Dashboard delle eccezioni e accesso all’intero elenco movimenti.
18. Gruppi di eccezioni. Raggruppare problemi analoghi e consentire approvazione selettiva.
19. Anagrafica centrale. Anagrafica unica di LLC/persone e mappa dei conti/carte al titolare.
20. QuickBooks in fasi. Inizialmente import di GL e Chart of Accounts Excel/CSV, successivamente API read-only.
21. Perimetro completo. Tutti i movimenti: operativi, trasferimenti, prestiti, anticipazioni, investimenti, patrimonio; senza dettaglio Clover.
22. Pagamento carte. Collegare pagamento del conto ad accredito sulla carta, senza duplicare i costi.
23. Documenti non obbligatori. Classificare anche senza ricevute o fatture; verifica fiscale esterna.
24. Due modalità un motore. Historical Cleanup (gen–ott 2026) e Daily Operations con identico motore.
25. Stato Reconciled. Reconciled quando Bank ha classificato tutti i dati pertinenti; confronto QB separato.
26. Export per LLC. Excel separati per LLC più prospetto rapporti economici reciproci e differenze/anomalie pertinenti.
27. Chiusura periodo. Periodi chiusi protetti; correzioni dopo chiusura tracciate separatamente.
28. Chiusura mensile. Bank propone chiusura mensile; solo il titolare conferma.
29. Management Control separato. Bank alimenta dominio dedicato al controllo gestionale senza assorbirne le funzioni.
30. Audit decisionale. Conservare movimento immutabile, classificazione, autore/mezzo, evidenze e storia delle correzioni.
31. Classificazione economico-contabile. Attribuire natura economica e destinazione contabile insieme; chiedere nei casi incerti.
32. Import CSV poi feed. Bonifica con CSV/estratti conto; successivamente collegamenti bancari automatici.
33. Modalità assistita. Modali con campi strutturati e conversazione AI libera.
34. AI dopo import. Avviare la riconciliazione automaticamente al termine di ogni importazione.
35. Incassi. Stesso motore per accrediti, distinguendo ricavi da finanziamenti/trasferimenti/patrimonio.
36. WHO contestuale. WHO controparte identificabile in base alla natura dell’operazione, senza inventarne uno.
37. Trasferimenti. Abbinare automaticamente le due gambe dei trasferimenti, preservando i movimenti.
38. Decisioni umane protette. Modifiche AI a decisioni umane solo tramite proposte e approvazione.
39. Catalogo categorie AI. AI propone e aggiorna gerarchia gestionale; approvazione necessaria per modifiche strutturali.
40. Chiusura senza sospesi. Chiusura permessa solo quando tutte le transazioni del periodo sono Reconciled; QB non vincolante.
41. Commissioni. Ricostruire lordo/fee quando esistono evidenze, senza alterare netto bancario e senza bloccare.
42. Profilo unico per WHO. Un Recognition Profile per WHO con condizioni differenziate per LLC.
43. WHO ibrido. Regole testuali approvate prima, AI per descrizioni nuove/ambigue, proposte nuove regole approvate.
44. Ambiguità profili. Investigazione AI, poi domanda mirata con alternative.
45. Indagine per gruppi. Una investigazione AI condivisa per movimenti analoghi, valutazione individuale di ciascuno.
46. Apprendimento immediato. Nuova conoscenza rielabora automaticamente soltanto gli irrisolti; retroattivo separato.
47. Correzione WHO. Rivalutare campi dipendenti dal WHO, proteggendo scelte umane.
48. Conflitti regole. AI risolve se evidenze sufficienti; altrimenti conferma umana; non cambia regole permanenti da sola.
49. Memoria condivisa. Conoscenza e spiegazioni accessibili agli altri domini autorizzati.
50. AI a livelli. Regole e memoria prima; modelli economici per semplici, modelli avanzati per complessi.
51. Provider AI. Servizio AI centralizzato RF-One con più modelli OpenAI.
52. Ricerca cross-domain. AI può cercare autonomamente nei domini permessi, senza modificarne i dati.
53. Nuovo motore. Un motore nuovo unico, riuso dati compatibili, isolamento motori precedenti.
54. Validazione parallela. Nuovo motore dry-run senza scrittura operativa, confronto risultati prima dell’attivazione.
55. Revisione legacy. AI analizza regole/profili esistenti, propone conservare/modificare/disattivare, con approvazione.
56. Prototipo end-to-end. Prima percorso completo ridotto, poi estendere funzionalità.
57. Modulo isolato. C-Bank Prototype separato con lettura sola dei dati Bank operativi; risultati sperimentali separati.
58. Esecutore. Claude sviluppa; definizioni e accettazione dell’utente, nessuna reinterpretazione arbitraria.

## 5. MVP: primo prototipo verificabile

Ambiente C-Bank Prototype separato. Lettura sola dei movimenti Bank esistenti. Output, configurazioni e audit sperimentali su archivio distinto; nessuna scrittura nel Bank operativo. Nessun deploy AWS o modifica dei motori legacy.

- Percorso completo su un campione di movimenti reali già importati: conto/carta → titolare → beneficiario → WHO → WHY → categoria RF-One → proposta categoria QB → stato → anteprima export LLC.
- Casi minimi: spesa persona→LLC, LLC→persona, LLC→LLC, acquisto business ordinario, ricavo, operazione patrimoniale, trasferimento, pagamento carta, WHO sconosciuto, WHO ambiguo, profilo con più esiti per LLC.
- Provare flusso regola esistente e flusso AI assistito; motivazione e origine dei dati visibili; modale per le eccezioni con campo strutturato e testo libero.
- Confronto read-only fra esiti del prototipo e classificazioni correnti. Nessuna applicazione retroattiva ai dati operativi.
- Esportazione dimostrativa per LLC e prospetto inter-entity, marcati chiaramente come risultati sperimentali.
- Criterio di accettazione: ogni caso di test è riproducibile e auditabile; mai scritture sui dati Bank; nessuna classificazione umana alterata.

## 6. Dopo MVP (non richiesto nel primo incremento)

Estensione all’intero storico gennaio–ottobre, dashboard e raggruppamento eccezioni in scala, correzioni retroattive con conferma, integrazione completa cross-domain, import QuickBooks e matching, chiusure mensili, automatic bank feed, gestione avanzata trasferimenti e rapporti reciproci, gestione permanente del catalogo e delle regole. Non anticipare queste funzioni se non indispensabili al percorso dimostrativo.

## 7. Vincoli di sviluppo e non-regressione

- Nessuna modifica al database produttivo o alle funzioni Bank attuali senza nuova autorizzazione.
- Separare esplicitamente WHO-identification, Profile classification, beneficiary attribution, accounting mapping e matching dei trasferimenti; un orchestratore unico, non motori in competizione.
- Verificare nomenclatura WHAT/WHOM del DB legacy: non rinominare automaticamente i campi o perdere reporting_entity_id.
- Non assumere che ogni pagamento a favore di una LLC sia costo P&L: beni capitalizzabili e operazioni patrimoniali hanno percorso distinto.
- Una transazione ha un solo beneficiario, ma i due lati di un trasferimento restano movimenti separati abbinati; correggere tramite rettifiche separate ove occorra.
- Proposte AI e classificazioni sperimentali devono essere distinte da operazioni approvate e contabilizzazioni definitive.
- Qualsiasi incongruenza delle 58 decisioni va segnalata con proposta mirata, non risolta arbitrariamente.

## 8. Consegne richieste a Claude

1. Mappa componenti legacy riutilizzabili e punti di accesso in lettura, senza variazioni al vecchio Bank.
1. Design concettuale essenziale e piani dei casi di prova del prototipo.
1. Implementazione locale isolata e avviabile, completa del primo percorso end-to-end.
1. Report sintetico dei casi verificati, gap residui e dimostrazione che il Bank operativo è rimasto invariato.
