# Bank — cose da fare

Decisione del Product Owner, 2026-11-06. Prima rendere funzionante e verificare Bank nel percorso corrente; le attività future sotto non autorizzano implementazioni immediate.

Quando il Product Owner chiede il punto su Bank, includere anche le cose da fare, con tre righe descrittive per ciascuna. Distinguere lavoro in corso, da verificare e futuro; aggiornare gli stati solo sulla base di evidenze.

## In corso / da verificare

Riferimento aggiornato: [decisioni e passaggio di consegne del 6 novembre](BANK_SESSION_2026_11_06.md). I resoconti di C. non equivalgono a una verifica indipendente completa. Il Product Owner ha concluso per oggi la discussione sulle regole; questo elenco non avvia nuovi lavori.

### Configurazione WHY per WHO
Una configurazione per WHO, con WHY unico, Personale/Aziendale oppure da regola, è dichiarata realizzata da C.
Restano le decisioni su sette WHO e la verifica della coerenza con eccezioni, WHOM e vecchie coppie per carta.
Stato: implementazione riportata, verifica complessiva indipendente non conclusa.

### Pattern Training e proposta AI
Ricerca dei gruppi e proposta AI all'apertura di Definisci regola dichiarate realizzate e provate da C. su ACH e PayPal.
Restano non provate la correzione via chat e l'applicazione agli esistenti; completamento dell'ordine di priorità non verificato.
Stato: accettato fermarsi qui per oggi; il confronto fra campi dei sette PayPal dubbi è una simulazione dell'assistente, non una modifica al motore.

### Finestra delle occorrenze affiancabile
Ultima richiesta: aprire da Definisci regola una seconda finestra spostabile, con prime 50 occorrenze e Carica tutte.
Il colore delle righe dovrebbe riflettere la simulazione; significati dei colori e ridimensionamento sono nella proposta documentata.
Stato: richiesta registrata, realizzazione non riportata; supera il precedente elenco interno alla modale.

### Modale Completa e verifica del flusso
La modale unica e le operazioni su duplicati, abbinamenti e WHOM sono dichiarate implementate da C.
Da verificare i casi rapporto tra titolari, stato Completato, WHOM nelle applicazioni multiple e valute mancanti sugli strumenti.
Stato: audit indipendente incompleto per blocco Computer Use; nessuna modifica dei dati autorizzata da questo promemoria.

## Attività future già discusse

### Inizializzazione assistita da AI con template
Partire da tipo di attività e paese, importando il piano dei conti esistente oppure proponendo un template verificato di categorie WHAT.
L'AI propone WHY logici per il business, già collegati ai WHAT, e usa i movimenti caricati per proporre associazioni WHO e disambiguazioni da verificare per gruppi.
Stato: logica concordata e documentata; implementazione rinviata a dopo il funzionamento del Bank corrente.

### Disambiguazione di assegni e casi specifici RF
Il solo formato CHECK e il numero dell'assegno non identificano il beneficiario.
Il confronto con ulteriori evidenze e la gestione dei casi specifici RF saranno discussi separatamente.
Stato: esplicitamente rinviato, senza nuove regole implementate in questa analisi.

### P/L per periodo e stampa/PDF nel Pannello
Realizzare il conto economico per periodo selezionato previsto nel Pannello.
Consentirne la stampa e il PDF; il solo spazio nel layout non costituisce una funzione completata.
Stato: previsto, non implementato secondo l'ultimo resoconto disponibile.

## Logica dell'inizializzazione assistita

Obiettivo: un nuovo utente non deve costruire manualmente WHAT, WHY e tutti i collegamenti prima di usare Bank, anche quando carica sei mesi di movimenti.

1. L'utente indica attività e paese. Se possiede un piano dei conti, ad esempio QBO, lo importa; altrimenti RF1 propone un template pertinente.
2. RF1 prepara le categorie contabili WHAT dal piano importato o dal template.
3. L'AI propone i WHY utili per la gestione di quell'attività, già associati ai WHAT. Più WHY possono riferirsi allo stesso WHAT.
4. Sui movimenti caricati RF1 riconosce i WHO e propone associazioni e regole di disambiguazione usando il catalogo preparato.
5. L'utente verifica le proposte per gruppi e interviene sulle ambiguità e sulle informazioni non deducibili. I movimenti reali affinano la configurazione iniziale.

I template sono basi verificate e versionate. L'AI adatta e propone: non inventa liberamente categorie contabili o trattamenti fiscali e non presenta le proposte come già approvate.

Esempio: per un ristorante, “Pulizia cappa” e “Pulizia locali” possono essere WHY distinti collegati alla medesima categoria contabile di pulizia.

Questa nota documenta una direzione futura, non avvia il lavoro e non modifica motori, cataloghi o dati.
