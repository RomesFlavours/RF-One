# MyRF — Restaurant — Server Tablet

**Versione:** Draft 0.1
**Stato:** Bozza — non approvata
**Modulo:** Restaurant Domain / MyRF / Server Tablet

---

## Scopo

MyRF è l'estensione cognitiva di RF-One che affianca le persone e adatta il supporto al loro contesto.

Questa documentazione definisce il primo perimetro operativo di MyRF per i server del dominio Restaurant: consultazione del menu, supporto alla vendita e acquisizione degli ordini da tablet, con integrazione Clover.

Il modello generale di MyRF comprende la gestione delle attività aziendali come progetti. Questi documenti descrivono la sua applicazione operativa al servizio di sala.

---

## Documenti

| # | Documento | Contenuto | Natura |
|---|---|---|---|
| 1 | [01-Accesso-e-Menu.md](01-Accesso-e-Menu.md) | Accesso del server, ricostruzione del menu da Clover, schermata menu, modale dettagli | Definizioni concordate |
| 2 | [02-Vini.md](02-Vini.md) | Schermata vini, abbinamenti ai piatti del menu, ordine al bicchiere / in bottiglia | Definizioni concordate (con un requisito da verificare) |
| 3 | [03-Tavolo-e-Percorso-Ordine.md](03-Tavolo-e-Percorso-Ordine.md) | Selezione tavolo, composizione, invio a Clover, stati dell'invio, ordinazioni successive | Definizioni concordate |
| 4 | [04-Responsabilita-e-Tracciabilita.md](04-Responsabilita-e-Tracciabilita.md) | Responsabile del conto, chi incassa, chi inserisce; passaggio tra server; registrazione delle operazioni | Definizioni concordate |
| 5 | [05-Verifiche-Integrazione-Clover.md](05-Verifiche-Integrazione-Clover.md) | Elenco delle capacità Clover da verificare e prova di accettazione futura | **Verifiche da svolgere — non capacità accertate** |

---

## Definizioni concordate e capacità Clover da verificare

I documenti 01–04 contengono **definizioni concordate** del comportamento atteso di MyRF lato server.

Dove queste definizioni dipendono da ciò che Clover consente effettivamente (lettura del catalogo, conti, comande cucina/bar, correzioni, autore delle modifiche, ecc.), la capacità tecnica **non è da considerarsi accertata**. Tutte queste dipendenze sono raccolte nel documento 05 come verifiche da svolgere. Nessuna di esse è stata ancora superata.

Nei documenti 01–04 i punti che dipendono da una verifica sono indicati con il rimando *(verifica: 05)*.

---

## Documenti correlati (esistenti)

- [../../Sales/Clover/README.md](../../Sales/Clover/README.md) — analisi esistente dell'API e della mappatura dati Clover (incluso [KnownLimitations.md](../../Sales/Clover/KnownLimitations.md))
- [../../Commercial Catalog/README.md](../../Commercial%20Catalog/README.md) — catalogo commerciale canonico (Item, Modifier, Price, Availability)
- [../../Service Copilot/README.md](../../Service%20Copilot/README.md) — assistenza in tempo reale al server durante il servizio

La relazione formale tra MyRF e questi moduli non è definita in questa bozza.
