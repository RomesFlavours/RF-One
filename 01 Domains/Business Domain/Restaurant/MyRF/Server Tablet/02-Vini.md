# 02 — Vini

**Versione:** Draft 0.1
**Stato:** Bozza — non approvata
**Modulo:** Restaurant Domain / MyRF / Server Tablet

[← README](README.md)

---

## 1. Schermata vini

- Colonna stretta a sinistra con categorie verticali: Rossi, Bianchi, Sparkling.
- Elenco dei vini nella parte destra.

## 2. Abbinamenti

- Gli abbinamenti fanno riferimento ai piatti effettivi del menu aziendale; non sono suggerimenti generici.
- Gli abbinamenti sono cliccabili e consentono di consultare il piatto collegato.

## 3. Dettaglio del vino

- Il dettaglio del vino mostra tutte le informazioni disponibili e approvate.
- Consultare il dettaglio non aggiunge automaticamente il vino all'ordine.

## 4. Ordine al bicchiere e in bottiglia

| Tasto | Disponibilità | Collegamento |
|---|---|---|
| Simbolo del bicchiere | Solo se esiste la corrispondente voce con prezzo in Clover | Voce Clover "bicchiere" del vino |
| Simbolo della bottiglia | Per ordinare la bottiglia | Voce Clover "bottiglia" del vino |

- Quantità e formato selezionato devono risultare chiaramente nel riepilogo.

## 5. Requisito da verificare

- **Da verificare:** la mappatura effettiva delle voci bicchiere/bottiglia nel catalogo Clover (vedi [05-Verifiche-Integrazione-Clover.md](05-Verifiche-Integrazione-Clover.md)). Finché la verifica non è svolta, la struttura del catalogo Clover per i vini non è da considerarsi nota.
