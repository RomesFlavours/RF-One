# Compensation — Confini operativi e dipendenze
**Data:** 2026-11-22  
**Stato:** integrazione decisioni funzionali al README draft e alle specifiche `COMPENSATION_AND_INCOME_COMPOSITION_001.md`, `OVERTIME_RULE_MATRIX_001.md`, `PAYROLL_HANDOFF_CONNECTOR.md`.

## 1. Distinzione fondamentale
Compensation governa quanto è maturato, le componenti economiche, l'approvazione e il passaggio al provider payroll. Non è il processore fiscale dei pagamenti ADP e non sostituisce il payroll provider.

## 2. Dati e confini
- Persona canonica riutilizzata da Registry.
- Compenso e paga oraria dipendono dai **termini retributivi approvati** per persona, periodo ed Entity, non dal semplice cambio di ruolo Clover.
- Le componenti di mance arrivano da **Tips finalizzato**, senza doppio calcolo del medesimo importo.
- Lavoro su più sedi appartenenti alla stessa Entity richiede il consolidamento delle ore senza duplicazione; distinguere ristorante, sede ed Entity legale.
- Il ruolo/reparto FOH/BOH può fornire classificazione organizzativa, **non modifica automaticamente** importi di compenso.
- I dati ADP possono essere acquisiti come evidenza/report del provider. Non inferire dalla loro presenza un'integrazione API o la responsabilità di Compensation sui pagamenti bancari.

## 3. Integrità
- Termine retributivo con date di validità e audit.
- Snapshot di approvazione e periodi approvati protetti da mutazioni retroattive automatiche.
- Correzioni successive richiedono percorso esplicito e tracciabilità.
- Import e riferimenti esterni restano separati dal modello canonico RF-One.

## 4. Verifiche
Condizioni per sede e per Entity, caso dipendente su più sedi, cambi ruolo, differenti periodi Tips, mancate conferme, payroll handoff, import ADP, permessi. Questa specifica non prova che Compensation sia già multisede né che il connettore payroll sia attivo.
