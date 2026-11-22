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
