# 05 — Verifiche Integrazione Clover

**Versione:** Draft 0.1
**Stato:** Bozza — non approvata
**Modulo:** Restaurant Domain / MyRF / Server Tablet

[← README](README.md)

---

> **Questo documento contiene verifiche da svolgere, non capacità già accertate.**
> Nessuna delle verifiche elencate è stata ancora svolta o superata.

---

## 1. Verifiche da svolgere

| # | Verifica | Riferimento | Esito |
|---|---|---|---|
| V1 | Lettura di catalogo, categorie, prezzi, modificatori e disponibilità | [01](01-Accesso-e-Menu.md) | Da verificare |
| V2 | Origine dell'elenco tavoli e gestione del numero di persone | [03](03-Tavolo-e-Percorso-Ordine.md) | Da verificare |
| V3 | Associazione tra tavolo, visita e conto Clover | [03](03-Tavolo-e-Percorso-Ordine.md) | Da verificare |
| V4 | Creazione del conto e aggiunta di nuove voci a un conto esistente | [03](03-Tavolo-e-Percorso-Ordine.md) | Da verificare |
| V5 | Mappatura dei vini al bicchiere e in bottiglia | [02](02-Vini.md) | Da verificare |
| V6 | Trasmissione di quantità, modificatori e note | [01](01-Accesso-e-Menu.md), [03](03-Tavolo-e-Percorso-Ordine.md) | Da verificare |
| V7 | Prevenzione dei duplicati e recupero degli invii con esito incerto | [03](03-Tavolo-e-Percorso-Ordine.md) | Da verificare |
| V8 | Effettiva generazione e destinazione delle comande cucina/bar | [03](03-Tavolo-e-Percorso-Ordine.md) | Da verificare |
| V9 | Gestione di correzioni e annullamenti dopo l'invio | [03](03-Tavolo-e-Percorso-Ordine.md) | Da verificare |
| V10 | Rilevazione delle modifiche esterne e della chiusura del conto | [03](03-Tavolo-e-Percorso-Ordine.md), [04](04-Responsabilita-e-Tracciabilita.md) | Da verificare |
| V11 | Disponibilità di dati sull'autore delle operazioni Clover | [04](04-Responsabilita-e-Tracciabilita.md) | Da verificare |

Materiale esistente utile come punto di partenza (non costituisce verifica): [../../Sales/Clover/CloverAPIAnalysis.md](../../Sales/Clover/CloverAPIAnalysis.md), [../../Sales/Clover/KnownLimitations.md](../../Sales/Clover/KnownLimitations.md).

## 2. Prova di accettazione futura

Sequenza da eseguire end-to-end, una volta svolte le verifiche:

1. Accesso del server.
2. Selezione tavolo e persone.
3. Ordine di un piatto con modificatore e di un vino.
4. Ricezione sul conto Clover corretto.
5. Comanda cucina/bar.
6. Seconda ordinazione senza duplicati.
7. Passaggio esplicito del server.
8. Chiusura su Clover e riconoscimento in MyRF.

Esito: **non ancora eseguita.**
