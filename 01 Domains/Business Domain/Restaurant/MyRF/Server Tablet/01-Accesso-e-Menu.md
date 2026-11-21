# 01 — Accesso e Menu

**Versione:** Draft 0.1
**Stato:** Bozza — non approvata
**Modulo:** Restaurant Domain / MyRF / Server Tablet

[← README](README.md)

---

## 1. Accesso

- Il server si identifica tramite firma/accesso personale.
- All'accesso sceglie se utilizzare l'auricolare.
- Se opera come FOH, accede al POS remoto.
- Il tablet viene utilizzato in orientamento portrait.

## 2. Ricostruzione del menu

- Alla firma il menu semplificato viene ricostruito dai dati Clover. *(verifica: 05)*
- Durante il turno devono essere gestiti aggiornamenti di disponibilità, prezzi e menu. *(verifica: 05)*

## 3. Schermata menu

- Categorie nella colonna sinistra; piatti nella parte destra della stessa schermata.
- Ogni piatto mostra nome, prezzo e breve descrizione di vendita.
- L'ordine corrente rimane visibile nella parte bassa.

### Comandi per ciascun piatto

| Comando | Comportamento |
|---|---|
| Foto | Visualizzazione a tutto schermo; X in alto a destra per tornare al menu |
| Ascolto ricetta | Riproduce l'ascolto della ricetta |
| Dettagli | Apre una finestra modale con informazioni estese e possibilità di aggiungere il piatto all'ordine |

## 4. Modale dettagli

- Nella modale si impostano:
  - quantità;
  - varianti/modificatori previsti da Clover *(verifica: 05)*;
  - note per la cucina.
- Dalla modale il piatto può essere aggiunto all'ordine corrente.

## 5. Contenuti

- Foto, ricette e descrizioni devono essere collegate alle rispettive voci Clover e provenire da contenuti aziendali approvati.
- Se un contenuto manca, il relativo comando risulta indisponibile.
- Le informazioni sugli allergeni devono provenire da dati verificati: non inferirle dalla sola descrizione commerciale.
