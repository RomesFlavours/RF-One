# 03 — Tavolo e Percorso dell'Ordine

**Versione:** Draft 0.1
**Stato:** Bozza — non approvata
**Modulo:** Restaurant Domain / MyRF / Server Tablet

[← README](README.md)

---

## 1. Percorso

1. Selezione del tavolo.
2. Se nuovo: inserimento del numero di persone tramite tasti 1–6 e Altro.
3. Se già aperto: recupero del conto Clover associato e delle ordinazioni esistenti. *(verifica: 05)*
4. Composizione delle nuove ordinazioni.
5. Riepilogo in basso con nuove voci modificabili o eliminabili prima dell'invio.
6. Ordinazioni già inviate consultabili e separate dalle nuove voci.
7. Tasto "Invia ordine", con conferma di tavolo, persone e nuove voci.
8. Invio tramite connettore al conto Clover corretto. *(verifica: 05)*
9. Registrazione della conferma di ricezione restituita da Clover.
10. Instradamento della comanda verso cucina/bar, subordinato alla verifica dell'integrazione. *(verifica: 05)*
11. Ordinazioni successive aggiunte allo stesso conto attraverso lo stesso percorso.

## 2. Regole

### Persone e tavolo

- Il numero di persone è correggibile.
- Il cambio di tavolo sul tablet non deve perdere le nuove voci ancora da inviare.

### Invio

- Ogni invio deve essere identificato univocamente per evitare duplicazioni.
- In caso di esito incerto, verificare quanto ricevuto prima di consentire un nuovo invio.
- Ricezione in Clover e invio della comanda in cucina/bar sono eventi distinti: non dichiarare il secondo sulla sola base del primo.

### Stati minimi di un invio

| Stato | Significato |
|---|---|
| Da inviare | Nuove voci composte, non ancora inviate |
| Invio in corso | Invio avviato, esito non ancora noto |
| Ricevuto da Clover | Clover ha restituito conferma di ricezione |
| Errore | Invio non riuscito |
| Esito da verificare | Esito incerto: occorre verificare quanto ricevuto da Clover prima di un nuovo invio |

L'elenco rappresenta il minimo richiesto ("almeno"); non esclude ulteriori stati.

**Decisione vigente OQ-5 ([RF1_OPERATIONAL_DATABASE_001, decisioni correnti](../../../../../10%20System/Operational%20Database%20and%20Data%20Governance/README.md#current-decisions)).** Le prove sono limitate all'**inserimento in Clover degli ordini del Server Tablet** per la sede selezionata. Altri tipi di dati, e modifiche o annullamenti dopo l'accettazione, sono rinviati. **L'invio degli ordini di prova resta da implementare.** Il modello di stato per l'inserimento resta da definire in progettazione, dopo le verifiche Clover (decisione di riferimento §12, G-6). *(La decisione originale del 2026-11-21 — registrazione come «in attesa», verifica prima del reinvio, tre eventi distinti invio/ricezione/inoltro in cucina — è riportata in [§11 OQ-5](../../../../../10%20System/Operational%20Database%20and%20Data%20Governance/README.md#oq-5) solo per tracciabilità, dove la decisione vigente la supera.)*

### Dopo l'invio

- Dopo l'invio, correzioni e annullamenti sono operazioni esplicite soggette alle autorizzazioni definite.
- Correzioni e annullamenti devono essere comunicati anche alla destinazione operativa quando necessario.

### Pagamento e chiusura

- Per il primo rilascio, pagamento e chiusura del conto avvengono su Clover.
- MyRF deve riconoscere la chiusura del conto prima di associare una nuova visita allo stesso tavolo. *(verifica: 05)*
