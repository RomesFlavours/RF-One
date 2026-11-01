# RF1 Motore comune per le interviste

Aggiornamento per S. e richiesta di parere · 1 novembre 2026

Ciao S., ti aggiorno sulla direzione che abbiamo concordato per l'acquisizione del Know-How. Vorrei partire da un motore di intervista generico, comune a RF1, che i diversi domini possano utilizzare specializzandone i contenuti e la direzione. Know-How sarebbe la prima applicazione concreta. Prima dell'implementazione, mi interessa sapere cosa ne pensi.

## Un motore comune guidato dai domini

Il motore gestisce il dialogo: formula domande, comprende risposte, chiede chiarimenti, conserva il contesto e permette di interrompere e riprendere. Il dominio stabilisce cosa conoscere, perché approfondirlo, quali evidenze cercare e quando gli obiettivi dell'intervista sono sufficientemente coperti.

La specializzazione deve guidare anche gli approfondimenti durante la conversazione, in base a ciò che emerge. Non basta una lista iniziale di domande.

- Know-How lo usa per ricostruire esperienze, metodi, successi ed errori e ricavarne conoscenza riutilizzabile.
- Selection lo usa per approfondire esperienze e capacità rispetto ai requisiti di un ruolo.
- Management lo usa per chiarire responsabilità, processi e problemi organizzativi.

La competenza e le conclusioni specialistiche restano al dominio. La capacità conversazionale è comune.

## Voce e testo fin dall'inizio

Il parlato è un requisito, insieme al testo. Una versione soltanto testuale non risponde all'obiettivo. L'esperienza proposta permette di parlare con RF1, ascoltare le domande, interrompere l'AI e riprendere, anche passando alla scrittura nella stessa intervista.

La tecnologia vocale resta da scegliere. Dobbiamo definire anche come correggere la trascrizione e se conservare l'audio, con quali autorizzazioni, accessi e tempi. Supportare la voce non implica registrare e conservare tutto.

## Interviste programmate e richieste dall'AI

Le due modalità utilizzano lo stesso motore. Nel secondo caso l'AI individua qualcosa da chiarire e richiede un'intervista. La richiesta va distinta dall'autorizzazione a contattare la persona: chi approva, chi riceve l'invito, quando e attraverso quale canale sono ancora da definire.

## Cognito e componenti esistenti

Questa separazione è coerente con il ruolo documentato per Cognito: capacità conversazionale trasversale al servizio del ragionamento specialistico dei domini. Resta da tradurla in componenti software e responsabilità tecniche.

La collocazione proposta per il codice è `03 Software/RF-One Data Store/rfone_data_store/interviews/`, seguendo l'organizzazione attuale dei servizi Python. È una proposta, non una collocazione già approvata. Il motore non diventerebbe proprietario delle conoscenze dei domini.

La ricerca ha individuato componenti utili: AI Organization gestisce sessioni, revisioni e approvazioni; Selection contiene piani, domande standard e dinamiche ed evidenze. La proposta è generalizzare i componenti pertinenti, conservando le regole specialistiche nei rispettivi domini. Non abbiamo scelto un nuovo framework o un servizio gestito.

## La prima applicazione in Know How

Il risultato dell'intervista alimenta conoscenza candidata, collegata alle risposte e alle evidenze da cui deriva. Deve poter essere rivisto e corretto, con validazione e approvazioni separate dalla conduzione del dialogo. Confermare che una sintesi rappresenta bene ciò che si è detto non equivale ad approvarne ogni utilizzo.

Il patrimonio comprende esperienze positive e negative, anche dell'AI, e contributi dalle elaborazioni RF1. Restano validi stati, versioni, accessi e governo umano, la doppia autorizzazione ai massimi livelli per la condivisione interaziendale e la revoca. Le limitazioni individuali sono configurate dal solo Admin Management. I dettagli attuativi restano da definire.

## Su cosa vorrei il tuo parere

1. Ti convince la separazione tra capacità conversazionale comune e direzione specialistica del dominio? Vedi sovrapposizioni o responsabilità mancanti?
2. Come collocheresti il motore rispetto a Cognito e ai servizi RF1? Quali componenti esistenti riutilizzeresti o generalizzeresti?
3. Cosa dovrebbe fornire un dominio per guidare davvero l'intervista, anche quando le risposte cambiano il percorso?
4. Come realizzeresti il parlato e la continuità con il testo? Quali decisioni prenderesti prima su audio e trascrizione?
5. Come distingueresti richiesta AI, autorizzazione al contatto, conferma del contenuto e validazione per il riuso?
6. Quale primo caso Know-How useresti per verificare approfondimenti, continuità e utilità della conoscenza raccolta?

Mi interessa capire se questa base ti sembra corretta e quali modifiche faresti prima di tradurla in una specifica di implementazione.

Riferimento di dettaglio: [Common Interview Service](../INTERVIEW_SERVICE_001.md).
