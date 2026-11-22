# Kitchen, Visual Menu e Kitchen Call — Confini funzionali
**Data:** 2026-11-22  
**Stato:** ricognizione di decisioni funzionali, con implementazione da verificare separatamente.

## 1. Kitchen
- Domini e pagine operative: ricette, opzioni, impiattamento, configurazione e menu.
- Le fotografie private e la documentazione di impiattamento sono evidenze operative con accessi appropriati, non semplice contenuto pubblico.
- Una verifica HTTP 200 prova il raggiungimento delle route, **non** ogni funzione autenticata o workflow.

## 2. Visual Menu
- Deve poter utilizzare le informazioni approvate di Kitchen e dei cataloghi senza duplicare arbitrariamente ricette o dati di prodotto.
- I contenuti pubblici e le informazioni interne riservate sono distinti; permessi e controllo accesso da verificare.
- La funzionalità autenticata di Visual Menu non può essere dichiarata funzionante soltanto perché il collegamento da Kitchen risponde.

## 3. Kitchen Call / MyRF
- Il Kitchen Call discusso è una PWA per tablet con interazione rapida e possibile smartwatch.
- Una chiamata resta evidente e con segnale acustico fino all'azione **Coming** o altro riscontro approvato; la ricezione e la conferma devono essere auditabili nel modello operativo appropriato.
- Tablet, smartwatch e sincronizzazione sono mezzi tecnici: nessun dispositivo particolare è parte del modello concettuale.

## 4. Confini e verifiche
Non confondere le istruzioni di servizio in sala con l'origine dei dati di cucina, ricette o menu. Verificare accesso autenticato, versioni dei contenuti, disponibilità media, PWA, segnali, azioni simultanee e recupero delle chiamate in caso di interruzione. Nessun rilascio è implicito.
