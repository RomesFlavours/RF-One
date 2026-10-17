# 04 — Responsabilità e Tracciabilità

**Versione:** Draft 0.1
**Stato:** Bozza — non approvata
**Modulo:** Restaurant Domain / MyRF / Server Tablet

[← README](README.md)

---

## 1. Ruoli distinti

Il responsabile del conto Clover, chi incassa e chi inserisce/modifica le singole voci sono concetti distinti.

| Concetto | Nota |
|---|---|
| Responsabile del conto Clover | L'assegnazione operativa in MyRF non implica automaticamente un suo cambio |
| Chi incassa | Può essere diverso dal server che prende gli ordini |
| Chi inserisce/modifica le voci | Tracciato da MyRF per le operazioni effettuate tramite MyRF |

- Non assumere che Clover permetta di identificare l'autore di ogni modifica. *(verifica: 05)*

## 2. Abilitazione per tavolo (primo rilascio)

- Nel primo rilascio, un solo server alla volta è abilitato a inserire ordini tramite MyRF per ciascun tavolo.
- Il passaggio a un altro server deve essere esplicito e registrato.
- Gli altri server autorizzati possono consultare menu e informazioni.

## 3. Registrazione delle operazioni effettuate tramite MyRF

Per ogni operazione effettuata tramite MyRF registrare:

- identità del server;
- tavolo e identificativo del conto Clover;
- voce interessata;
- tipo di operazione e modifica effettuata;
- data e ora;
- identificativo dell'invio;
- esito e riferimenti restituiti da Clover.

## 4. Modifiche effettuate direttamente su Clover

Le modifiche effettuate direttamente su Clover:

- devono essere rilevate tramite sincronizzazione/confronto, nei limiti tecnici da verificare *(verifica: 05)*;
- se non è disponibile un'identità attendibile, vengono indicate come **"modifica esterna, autore non identificato"**;
- non devono essere attribuite automaticamente al responsabile del conto o a chi incassa.
