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

### Dopo l'invio

- Dopo l'invio, correzioni e annullamenti sono operazioni esplicite soggette alle autorizzazioni definite.
- Correzioni e annullamenti devono essere comunicati anche alla destinazione operativa quando necessario.

### Pagamento e chiusura

- Per il primo rilascio, pagamento e chiusura del conto avvengono su Clover.
- MyRF deve riconoscere la chiusura del conto prima di associare una nuova visita allo stesso tavolo. *(verifica: 05)*
