# Tips — Registro ruoli da Registry e validità delle regole
**Decisioni approvate e riscontri del 20–21 novembre 2026**  
**Stato:** allineamento funzionale/documentale; distinguere il report di correzione dati AWS dal codice Tips non ancora pubblicato alla data delle prove riportate.  
**Non è una modifica del motore né autorizzazione a deploy o pagamenti.**

## 1. Autorità dei dati
- **Registry** è l'unica fonte ufficiale della corrispondenza `Clover role → RF-One role`, per ristorante/sede e validità.
- La tabella storica Tips `source_role_mappings` non deve essere usata come seconda fonte. Il codice del branch `feature/tips-registry-roles` la marca dismessa ma **non la cancella**.
- Tips rimane proprietario di regole, percentuali, criteri di eleggibilità, calcoli, conferme, esecuzione pagamenti e audit.
- La storia osservata Clover documenta il ruolo che la persona aveva nel momento considerato; un ruolo attuale **non** può essere proiettato su un periodo passato senza evidenza.

## 2. Validità storica e ambiguità
- La prima versione di una corrispondenza ruolo Clover → ruolo RF-One in Registry può essere trattata come applicabile a periodi anteriori alla creazione della tabella, **salvo contraddizione con assegnazione MANUAL confermata e valida per quella data**.
- Prima della prima osservazione Clover, usare una assegnazione Registry documentata e valida alla data, senza retrodatare assegnazioni create successivamente.
- Se manca ruolo/assegnazione o esistono due assegnazioni incompatibili: eccezione esplicita; il motore non indovina né paga.
- La sola esistenza del reparto FOH/BOH non sostituisce la mappatura di un ruolo specifico necessario al calcolo Tips.

## 3. Regole di distribuzione e periodi finalizzati
- Le regole sono **temporalmente valide**. La disattivazione di una regola corrente **non deve cancellare il suo effetto storico**.
- Da report del 21/11: la regola Host **#2**, riattivata su AWS, vale fino all'8/11/2026 09:00 UTC **escluso**; regola **#3** attiva da quell'istante. Nessuna doppia quota Host; il report conferma cinque calcoli definitivi settembre–ottobre invariati al centesimo.
- Questo risultato è confermato dai report operativi e **non** implica che il controllo UI per terminare le regole sia già stato implementato o distribuito.
- Periodi definitivi, entitlement e pagamenti sono immutabili per effetto automatico. Un calcolo esplorativo non modifica un periodo finale.

## 4. Stato implementativo e limiti riferiti
- Branch `feature/tips-registry-roles` (`d71808d` al momento della verifica) contiene la modifica che legge Registry, non il mapping Tips; i test riportati: 13 su 15 giorni recenti sbloccati, 8 e 11 novembre ancora privi di ruoli storici documentati.
- Dal report del 21/11: alcuni casi relativi a ruoli storici richiedono evidenze documentate nei periodi interessati; non assegnare ruoli fittizi. I dettagli nominativi restano nei report operativi riservati, non nella specifica pubblica.
- Il piano `feature/clover-multisite-registry:.../CLOVER_MULTISITE_RELEASE_PLAN.md` del 21/11 include una versione di Tips per WP/MD, ma `PLAN ONLY` non prova il deploy.
- La verifica della correttezza reale degli importi di ogni singolo pagamento resta distinta dal superamento di test simulati.

## 5. Verifiche di accettazione
Confronto per importo **e per persona** sui periodi definitivi, assicurando:
1. ruoli risolti da Registry per data e sede;
2. nessun mapping alternativo Tips consultato;
3. periodi chiusi identici;
4. scelta di una sola regola Host valida in ogni istante;
5. pagamento impossibile se ruolo o eleggibilità incerti;
6. WP/MD isolati e nessuna attivazione implicita di MD.

## 6. Fonti tecniche
- `01 Domains/Business Domain/Restaurant/Tips/Tip Policy.md`
- `01 Domains/Business Domain/Restaurant/Tips/Finalized Tips Period.md`
- `feature/tips-registry-roles:03 Software/RF-One Data Store/rfone_data_store/tips/SOURCE_ROLE_MAPPING_RETIREMENT.md`
- `feature/clover-multisite-registry:03 Software/Infrastructure/deploy/CLOVER_MULTISITE_RELEASE_PLAN.md`
