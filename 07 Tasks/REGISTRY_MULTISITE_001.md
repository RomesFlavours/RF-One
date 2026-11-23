# REGISTRY_MULTISITE_001 — New multi-site Registry

Status: approved specification (Product Owner with ChatGPT), supplied in chat on 2026-11-22 and recorded
here verbatim so that implementation and independent review refer to the same text. Implementation:
branch `feature/registry-multisite`. AWS switch-over requires the Product Owner's authorization.

## Commands that preceded the specification (verbatim)

> Parti dalla specifica appena redatta e da una base locale aggiornata di RF‑One. Implementa il nuovo
> Registry multisede con inserimento manuale e tramite Training. Usa i rami di rilascio AWS come
> riferimento per ricostruire lo schema attuale, la catena delle migrazioni e le associazioni da
> preservare. Verifica in sola lettura se il problema MD nasce dalla lettura o dai dati salvati. Prepara e
> prova in locale la migrazione dei dati esistenti, includendo i controlli su WP, MD, Training e storico
> Tips. Consegna il diff, l’esito delle prove e la procedura di passaggio e ripristino per la revisione
> indipendente di Codex. Fermati prima di qualsiasi modifica su AWS.

> Elimina dal nuovo Registry le procedure che leggono da Clover l’elenco delle persone e che propongono,
> creano o aggiornano schede anagrafiche a partire dai dati Clover. Elimina anche la coda delle proposte,
> le schermate e i pulsanti di conferma, le relative API e ogni job o trigger dedicato a quel flusso. Se un
> job è condiviso con altri domini, rimuovi solo il passaggio che alimenta Registry.
>
> Le schede Registry si creano solo tramite inserimento manuale o tramite Training. Conserva gli
> identificativi Clover già associati alle persone dove servono a riconciliare lo storico di Tips.
>
> Nella procedura di rilascio, indica quali componenti del vecchio flusso vanno disattivati al passaggio su
> AWS. Nelle prove locali dimostra che un nuovo nominativo su Clover non crea, non aggiorna e non propone
> alcuna scheda in Registry, e che l’inserimento manuale e quello da Training funzionano per la sede
> corretta. Consegna diff e risultati a Codex per la verifica prima di intervenire su AWS.

## Specification (verbatim)

**Specifica RF‑One — Nuovo Registry multisede**

**1. Identità e sedi**

Registry è l’anagrafica delle persone di RF‑One. Ogni persona ha una sola identità RF‑One e può essere
assegnata a una o più sedi.

Il filtro di sede usa le assegnazioni esplicite a ristorante/sede in Anagrafica. L’appartenenza a
un’azienda, i collegamenti Clover e il campo sede della scheda non determinano chi compare nella lista. Una
persona assegnata a entrambe le sedi compare in entrambe con lo stesso ID RF‑One.

Se l’utente seleziona MD, Registry mostra esclusivamente le persone assegnate a MD. Se MD è accessibile e
priva di assegnazioni, mostra una lista vuota. Se MD non è accessibile, segnala che la sede non è
disponibile. In nessuno dei due casi la pagina ripiega su WP.

**2. Inserimento manuale e da Training**

- Manuale. L’operatore autorizzato crea la scheda e indica esplicitamente la sede. Per aggiungere una
  persona già registrata a un’altra sede, assegna la nuova sede alla scheda esistente.
- Training. Un invito diretto o il comando Send to Training da Selection crea o riutilizza la scheda per la
  sede del training. Un nuovo ingresso viene registrato come Trainee. Ripetere l’operazione deve
  riutilizzare la stessa identità ed evitare un secondo invito automatico. Un Employee già registrato
  conserva il suo stato.
- Conferma dell’assunzione. Il flusso Confirm Hire aggiorna a Employee la stessa scheda, registrando chi ha
  confermato e quando. Mantieni le condizioni e l’eventuale eccezione motivata dell’Owner già previste dal
  flusso Training.

**3. Eliminazione del flusso Clover → Registry**

Rimuovi i percorsi che leggono i nominativi Clover per alimentare Registry, inclusi quelli che li ricavano
dallo storico dei turni. Elimina la creazione e l’aggiornamento delle schede da dati Clover, la coda delle
proposte e le relative azioni di conferma.

Rimuovi da Registry Identità Clover da confermare e da Anagrafica Collegamenti da riconciliare e
Sincronizza ora per questo flusso. Elimina anche le relative route e il passaggio che alimenta Registry nei
job condivisi. Mantieni l’acquisizione Clover di turni e dati operativi usati da Tips.

**4. Collegamento POS per Tips**

Sulla scheda di una persona già esistente, un operatore autorizzato può inserire manualmente il POS ID per
la sede cui la persona è assegnata. Tips usa la coppia sede + POS ID per associare i dati Clover
all’identità RF‑One. Blocca il riutilizzo dello stesso POS ID per due persone nella stessa sede.

Il POS ID è facoltativo per creare la scheda e per iniziare Training. Se un turno arriva senza un
collegamento valido, Tips lo mantiene da riconciliare. Il turno non genera una proposta in Registry.
Conserva le associazioni esistenti e verifica che una correzione del POS ID non riattribuisca lo storico
già consolidato. La creazione automatica della persona in Clover resta nel perimetro di OQ‑7.

**5. Base di lavoro, migrazione e consegna**

Parti da una base locale aggiornata. Prima di scegliere il ramo, verifica quali modifiche di
feature/clover-multisite-registry servono effettivamente a Training e a OQ‑7. Porta nel nuovo ramo quelle
necessarie, evitando di trascinare il vecchio flusso Clover. Preserva il lavoro OQ‑7 non ancora salvato. Usa
i rami di rilascio AWS per ricostruire lo schema esistente e la catena di migrazioni, inclusa a1c220261121.

Leggi AWS in sola lettura per stabilire se MD mostra WP per effetto della selezione di sede, delle
assegnazioni salvate o di entrambi. Prepara e prova in locale la migrazione su una copia dei dati. Conserva
le identità, le assegnazioni WP verificabili, le assegnazioni MD verificabili e i collegamenti allo storico
Tips. Elenca i casi dubbi per verifica prima del passaggio. L’elenco WP non va replicato in MD.

Consegna a Codex il diff, gli esiti delle prove e la procedura di backup, migrazione, passaggio,
disattivazione del vecchio flusso e ripristino. Le prove devono coprire WP e MD, una persona assegnata a
entrambe, MD vuota, l’inserimento manuale, entrambi gli ingressi da Training, il collegamento POS di un
nuovo assunto e la continuità dello storico Tips. Dimostra anche che un nuovo nominativo Clover, rilevato
nell’elenco del personale o nei turni, non crea, aggiorna o propone alcuna scheda.

Fermati dopo la consegna per la revisione indipendente di Codex. Il passaggio su AWS richiede
l’autorizzazione di Pino.

## Correction — Product Owner, 2026-11-22 (verbatim)

> Parti da 816000a e correggi la specifica e il codice.
>
> 1. I ruoli risiedono nel catalogo unico di Registry e sono comuni a tutte le sedi. WP e MD sono assegnazioni
>    di lavoro della persona. Verifica come allineare il catalogo esistente a questa regola preservando
>    assegnazioni e permessi effettivi.
>
> 2. L’invito a Training è associato alla persona. Elimina la sede dai requisiti di creazione, reinvio e
>    attivazione dell’invito. Applica la stessa regola a Selection, all’invito diretto e al Server Course.
>    Anche una persona senza sede deve poter ricevere l’invito e iniziare Training. Se il corso indica il ruolo
>    Server, usa quello del catalogo unico. L’invito non assegna una sede né concede permessi operativi.
>
> 3. Rendi utilizzabili anche i codici già emessi senza sede e conserva gli inviti attivi. Mantieni un solo
>    invito per persona e la protezione del link precedente se il reinvio fallisce.
>
> 4. Rimuovi dal piano il passo 2a come prerequisito per Training. Prova il flusso per una persona senza sede,
>    una assegnata a WP e una assegnata a MD. Consegna il nuovo SHA e l’esito delle prove. Nessuna modifica su
>    AWS e nessun deploy.

### Specification as corrected (English, supersedes the Training bullet of §2 above)

- **Role catalog.** Roles live in Registry's one catalog and are common to every site. WP and MD are the
  person's work assignments (Registry card → site + role), never a property of the role. Every Registry role
  choice (manual entry, new site on a card, Training) offers the whole active catalog.
- **Training invitation.** The invitation belongs to the person. Creating, resending and activating it needs
  no site — direct invitation, Selection (arrival confirmation) and Server Course alike. A person without any
  site can be invited and start Training. The invitation creates or reuses the person's Registry card as
  Trainee (an Employee keeps the status) **without assigning a site**, and grants no operational permission
  (activation gives Training only). The role the person trains for is optional; when given (Invite student)
  or indicated by the course (Server Course → «Server»), it is the catalog role, noted on the card history
  (`TRAINING_ROLE`), not a work assignment.
- **Codes and invitations already issued.** Server Course codes issued without a site (or with the former
  site field) are accepted; active invitations stay valid. One live invitation per person; on a resend the
  link already received stays valid until the email service accepts the new email.
- Unchanged: Confirm Hire needs the Registry card; «Resolve card and site» still records a site explicitly for
  a legacy Trainee without a card (it is not an invitation).

### Catalog alignment (verified, not applied to data)

Registry now reads the catalog as common to all sites (`employee_directory.catalog_role_choices`; the stored
`restaurant_roles.restaurant_id` is ignored by Registry), so on AWS the five roles stored with restaurant 1
(Manager, Team Leader, Server, Busser-Runner, Host) are offered at MD too **with no data change**: no
assignment, mapping, role permission or account row is written, so assignments and effective permissions are
unchanged by construction. Aligning the stored column too (`restaurant_id = NULL` on those five roles; names
are unique, so the catalog constraint holds) is **not** done here: Tips still reads it — role lists per
restaurant (`Tips/app.py` 1625, 1816; `tips/rule_ai_authoring.py` 559) and the rule check
`tips/distribution_rule_service.py` 311 (`role.restaurant_id != restaurant_id` → refused). Changing the data
first would empty WP's Tips role lists and refuse WP rules; it needs Tips to read the catalog first (separate
decision). If applied later, `registry_multisite_migration_check.py snapshot/compare` proves assignments and
effective permissions unchanged (`test_registry_multisite_permissions.py` test 4).
