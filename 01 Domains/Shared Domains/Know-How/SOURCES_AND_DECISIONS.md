# Fonti e decisioni

## Fonti disponibili

**S1 — Richiesta corrente dell'utente, 2026-11-01.** È la fonte diretta dei requisiti elencati sotto e dell'autorizzazione a creare questa sola cartella. La richiesta impone di distinguere decisioni, proposte e punti non definiti e vieta commit e push in questa fase.

**S2 — Conversazione C-Domain Management**, ID `6ad726d7-29cc-83e8-8b09-2f562bf105d4`, [riferimento](chatgpt-conversation://6ad726d7-29cc-83e8-8b09-2f562bf105d4). Consultata tramite `read_thread`, con `turnLimit: 10`. Il risultato contiene cinque turni utente («si», «ok», «si», «si», richiesta di creare la cartella e successivo push), nessun allegato e nessun cursore ulteriore. Le risposte assistant sono soltanto marcatori `chatgpt-content-reference`, senza contenuto consultabile. Non è quindi disponibile il testo delle decisioni precedenti né delle proposte assentite. L'assenso finale alla produzione documentale è visibile; la richiesta corrente sospende espressamente commit e push.

**S3 — Contesto locale, consultato il 2026-11-01:**

- [Tassonomia dei Domains](../../README.md): collocazione canonica in Shared Domains, distinta da `_Shared` e Business Domain.
- [Management](../Management/README.md): People, Organization, Project Manager; stato specifico dei componenti.
- [Selection](../Selection/README.md): dominio specialistico riutilizzabile e confini con Training.
- [Training Service](../TRAINING_SERVICE_001.md): servizio interno e responsabilità sul ciclo formativo.
- [Operational Knowledge](../Operational%20Knowledge/README.md): patrimonio operativo recuperabile; relazione documentata con Training.

S3 descrive il working tree locale, che presenta modifiche preesistenti. Questi riferimenti non provano decisioni della conversazione S2 e non vengono modificati.

## Registro dei requisiti espliciti

Tutte le righe hanno stato **APPROVATO-RICHIESTA**, fonte S1. I dettagli attuativi non esplicitati restano aperti.

| ID | Requisito | Documento |
|---|---|---|
| KH-01 | Acquisizione universale, incluse elaborazioni RF1 | Functional Reference |
| KH-02 | Interview engine comune | Functional Reference |
| KH-03 | Rete di conoscenze ed evidenze | Functional Reference |
| KH-04 | Basket di esperienze positive e negative, anche dell'AI | Functional Reference |
| KH-05 | Stati e versioni | Knowledge Lifecycle |
| KH-06 | Validazione e governance umana | Governance and Access |
| KH-07 | Approvazioni differenziate | Governance and Access |
| KH-08 | Condivisione interaziendale: doppia autorizzazione ai massimi livelli e revoca | Governance and Access |
| KH-09 | Limitazioni individuali configurate dal solo Admin Management | Governance and Access |
| KH-10 | Accessi | Governance and Access |
| KH-11 | Proattività | Functional Reference |
| KH-12 | Notifiche | Functional Reference |
| KH-13 | Misurazione dell'efficacia | Functional Reference |
| KH-14 | Collegamenti a Training, Selection, Management e RFCore | Integrations |
| KH-15 | Limiti di autonomia | Governance and Access |

## Limite di completezza

Il pacchetto copre tutti i temi esplicitati in S1. Non può attestare di contenere tutte le decisioni storiche di S2 finché il testo integrale non è disponibile. Nessuna proposta ulteriore viene presentata come approvata mediante gli assensi isolati.
