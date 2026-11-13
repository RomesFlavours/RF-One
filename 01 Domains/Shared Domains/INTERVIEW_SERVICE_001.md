# RF1 Common Interview Service

**Versione:** 0.1 · **Data:** 2026-11-01

**Stato:** architettura funzionale concordata nella conversazione corrente; dettagli tecnici proposti e decisioni aperte indicati separatamente. Servizio non ancora implementato da questa consegna.

## Decisioni esplicite

L'utente ha confermato la direzione: «facciamo subito il motore, che di per se è generico, poi i vari domini ne specializzano sia i contenuti che la direzione che deve prendere l'intervista». Ha inoltre precisato: «Io non voglio solo testo, serve anche parlato». Il requisito iniziale comprende interviste programmate e richieste dall'AI.

Il motore è comune a RF1. Know-How è la prima applicazione concreta; Selection e Management sono utilizzatori previsti del medesimo servizio, con specializzazioni proprie. Il servizio non è un nuovo Shared Domain né un motore esclusivo di Know-How. Questa collocazione documentale segue il precedente del [Training Service](TRAINING_SERVICE_001.md).

## Responsabilità

The approved 2026-11-03
[Person Organizational Applicability contract](PERSON_ORGANIZATIONAL_APPLICABILITY_001.md)
governs employee recipients across Interviews and all other modules. Interviews
reads applicability and active status through shared Anagrafica services and
revalidates them before a new request. It must not independently restrict
applicability to the requester's workplace or maintain a separate scope
configuration. Group-wide applicability is explicit; it is not an absent site.
Account access and historical interview visibility remain separately authorized.
This rule does not assert that all existing prototype implementations comply.

| Livello | Responsabilità funzionale |
|---|---|
| Interazione comune | Comprensione ed espressione attraverso voce e testo, gestione del dialogo e delle interruzioni |
| Motore di intervista | Contesto della sessione, domande, chiarimenti e approfondimenti, avanzamento, pausa e ripresa |
| Dominio utilizzatore | Scopo, contenuti e direzione dell'intervista, aspetti da approfondire, evidenze pertinenti e criteri specialistici di completamento |
| Governo delle azioni | Accessi, autorizzazioni, validazione e approvazioni previste per il caso d'uso; nessuna autorità nasce dal solo dialogo |

La specializzazione non è soltanto una lista iniziale di domande: il dominio guida gli approfondimenti in base alle risposte. Il motore sostiene questa direzione senza assumere le conclusioni professionali del dominio.

## Voce e testo

**DECISO:** entrambi i canali sono requisiti del motore fin dall'inizio; una versione solo testuale non soddisfa la richiesta.

**COMPORTAMENTO PROPOSTO:** parlare e ascoltare le domande, interrompere la risposta parlata dell'AI, sospendere e riprendere, passare tra voce e scrittura nella stessa sessione mantenendo il contesto. La trascrizione dovrebbe rendere verificabile l'origine delle unità estratte; un errore di riconoscimento va distinto da una dichiarazione della persona.

**APERTO:** architettura vocale, riconoscimento e sintesi separati oppure interazione audio in tempo reale, lingue, dispositivi, latenza, gestione del turno, correzione delle trascrizioni e identificazione del parlante. Non è scelto alcun provider. Registrazione e conservazione dell'audio, consenso, tempi, cancellazione e accessi richiedono decisioni esplicite. Supportare la voce non implica conservare l'audio né analizzare emozioni.

## Origine delle sessioni

**DECISO:** sessioni programmate e sessioni richieste dall'AI usano il medesimo motore.

**PROPOSTA:** una richiesta AI espone la lacuna da chiarire, il contesto e l'utilità attesa. Richiesta, autorizzazione al contatto, invito, accordo sull'appuntamento e svolgimento sono passaggi distinti. Le regole per effettuarli non sono ancora definite: l'iniziativa AI non costituisce una delega generale a contattare persone.

**APERTO:** chi programma, ricorrenze, destinatari, approvatori, canali, rinvii, rifiuti, notifiche e solleciti. Uno scheduler avvia un processo nel tempo; non sostituisce l'accordo con la persona. I vincoli storici dei singoli prototipi non diventano automaticamente divieti del nuovo servizio.

## Cognito e collocazione tecnica

**CONTESTO-REPOSITORY:** [Cognito, sezioni 3, 4 e 9](../../00%20Core/ConceptualArchitecture/14_Cognito_RF-One_Cognitive_Intelligence.md) assegna a Cognito capacità conversazionali comuni e ai domini il ragionamento specialistico; distingue Attention Management per destinatari, priorità, momento e canale. La definizione concettuale non identifica un runtime già pronto.

**PROPOSTA:** realizzare il servizio comune in `03 Software/RF-One Data Store/rfone_data_store/interviews/`, coerentemente con l'organizzazione attuale dei servizi Python. Il percorso è proposto, non una decisione di implementazione già approvata; non viene creata una cartella di codice vuota. La responsabilità funzionale nel quadro Cognito è distinta dalla collocazione tecnica del pacchetto. Il motore non possiede la conoscenza dei domini.

## Output e validazione

Per Know-How l'output alimenta conoscenza candidata e rete di evidenze; per Selection contribuisce alle evidenze di selezione; per Management al chiarimento organizzativo. Non è approvato un divieto generale di impiegare le risposte nella valutazione delle persone: finalità e autorizzazioni dipendono dal dominio.

**PROPOSTA:** distinguere risposte originali, interpretazioni AI, unità candidate e contenuti validati; mantenere riferimenti alle fonti e revisioni delle correzioni. Conferma della fedeltà di una sintesi, validazione della conoscenza e approvazione per un impiego sono atti diversi. Schema dati, immutabilità del transcript, confidenza numerica e trattamento delle contraddizioni restano aperti.

Il dominio definisce quando l'obiettivo è sufficientemente coperto; il software ne applicherà i criteri. Non sono approvati un massimo di tre approfondimenti, un numero fisso di turni o una chiusura affidata senza vincoli al modello. Modalità di interruzione e chiusura devono rendere visibili gli aspetti non esplorati.

## Ricerca e proposta di realizzazione

La ricerca locale ha esaminato AI Organization (`ai_organization.py`), i servizi Phone e In-Person di Selection, il workspace Selection e il template storico Legacy. Sono componenti e pattern riutilizzabili, non prova di un motore comune già realizzato. AI Organization comprende anche comportamento dimostrativo; la generazione di domande dal CV non dimostra un'intervista adattiva turno per turno.

**PROPOSTA:** generalizzare persistenza, revisioni e gestione delle evidenze pertinenti, conservando le policy specialistiche nei domini. Iniziare con conduzione semistrutturata adattiva; per le esperienze concrete valutare Critical Decision Method e ricostruzione di episodi. Nessun framework o modello è selezionato e nessun benchmark è stato eseguito.

| Opzione studiata | Capacità documentata | Limite rispetto a RF1 |
|---|---|---|
| Orchestrazione RF1 | Riuso dei componenti locali | Il servizio comune va costruito |
| Pydantic AI | Output strutturati e tool differiti con approvazioni | Governance RF1 e programmazione da integrare |
| LangGraph | Stato, checkpoint, sospensione e ripresa | Flussi e autorizzazioni del dominio da definire |
| Rasa | Flussi espliciti e gestione delle deviazioni | Da valutare per interviste esplorative |
| OpenAI Agents SDK | Sessioni e approvazioni riprendibili | La validazione della conoscenza resta applicativa |
| Claude Managed Agents | Sessioni gestite e avvii ricorrenti | Dipendenza dal servizio; verificare condizioni correnti |
| Temporal | Workflow, messaggi esterni e avvii temporizzati | Complemento operativo, non metodo d'intervista |

Fonti ufficiali consultate nella ricerca del 2026-11-01: [Pydantic AI](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/), [LangGraph](https://docs.langchain.com/oss/python/langgraph/interrupts), [Rasa](https://rasa.com/docs/reference/primitives/flows), [OpenAI](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals), [Claude](https://platform.claude.com/docs/en/managed-agents/scheduled-deployments), [Temporal](https://docs.temporal.io/schedule), [Critical Decision Method](https://ieeexplore.ieee.org/abstract/document/31053/authors). La tabella è una comparazione documentale, non una certificazione o una graduatoria sperimentale.

L'intervista può usare un modello generale; non è stato stabilito che occorra acquistare un'AI specializzata. Costi di sviluppo, consumo AI e servizi vocali o gestiti sono distinti e non ancora quantificati.

**PROPOSTA DI VERIFICA:** confrontare casi ordinari, esperienze positive e negative, testimonianze discordanti e ripresa dopo interruzione. Misurare copertura, ripetizioni, provenienza verificabile, correzioni del validatore, utilità della conoscenza e costo/tempo per intervista. Per la voce aggiungere comprensibilità, errori di trascrizione e gestione delle interruzioni. Soglie e protocollo restano aperti.

## Provenienza e decisioni ancora necessarie

Fonte primaria delle decisioni: messaggi utente della conversazione corrente successivi alla creazione di Know-How. Il report di Claude incollato dall'utente è materiale di confronto, non approvazione automatica delle sue proposte. L'inclusione delle esperienze AI nel basket era già richiesta; non è una questione da riaprire. Le affermazioni normative del report non sono adottate qui come policy.

Restano da concordare: contratto di specializzazione dei domini, responsabilità tecniche, criteri di completamento, approvazioni, accessi, programmazione e contatto, architettura vocale e conservazione dei dati. Per Know-How restano validi gli [open decisions del dominio](Know-How/OPEN_DECISIONS.md), inclusa la ricostruzione storica incompleta di S2.

Il [documento per S.](Know-How/ARCHITECTURE_UPDATE_FOR_S.md) chiede un parere su questa direzione; non attesta un suo assenso e non viene inviato automaticamente.

## S5 — Primo flusso richiesto e implementazione locale

**Decisione utente successiva, 2026-11-01:** una pagina generica permette all'admin di selezionare la persona e spiegare la finalità all'AI; la persona trova l'intervista richiesta nella home MyRF; a conclusione l'admin apre una pagina separata con le risultanze dall'elenco delle interviste. Non viene assegnato un nome commerciale al motore.

Il codice locale realizza questo primo flusso nel pacchetto proposto `rfone_data_store/interviews/` e nelle pagine RF-One Web. La specializzazione iniziale è Know-How; il motore separa la sua direzione dall'orchestrazione. Voce e testo sono disponibili attraverso i controlli browser nei browser compatibili, con riconoscimento e sintesi, senza persistenza dell'audio. La sessione viene indirizzata a un account RF1 attivo esistente. Per questa versione l'admin che la richiede ne vede le risultanze, il destinatario ne svolge il dialogo; non viene concessa condivisione ad altri utenti.

Il completamento è esplicito e le risultanze restano candidate. Nuovi stati tecnici e schema della sessione sono dettagli della prima implementazione, non una definizione definitiva del ciclo di vita universale della conoscenza. Scheduling temporale, richieste autonome AI, validazione e condivisione interaziendale non sono implementati da questo flusso.

Il supporto vocale dipende dalle capacità e dai servizi del browser: non certifica compatibilità universale o trattamento locale dell'audio. L'adozione di un provider vocale server resta aperta. La migrazione è additiva e non viene eseguita all'avvio o sul database operativo durante lo sviluppo. Vedere [runtime e verifica](../../03%20Software/RF-One%20Web/INTERVIEWS.md) per limiti e attivazione.

## S6 — Risultanze e anagrafica unica

**Decisione utente successiva, 2026-11-01:** completare la pagina dei risultati e collegare le tre pagine del prototipo all'anagrafica. L'utente chiarisce: «L'anagrafica incorpora tutti i dipendenti e gli esterni, inutile avere 2 diverse anagrafiche».

L'implementazione locale riusa i record persona già presenti nel database, senza creare una seconda tabella di nomi. I record dipendente e gli account RF1 sono collegamenti espliciti alla persona; l'account fornisce l'accesso a MyRF. La richiesta seleziona la persona, il dialogo identifica la stessa persona e le risultanze rimandano alla sua scheda, dalla quale si consulta lo storico delle interviste del richiedente. Un esterno può essere registrato senza account; per consegnargli un'attività MyRF occorre un account attivo collegato.

I record preesistenti non collegati restano visibili nell'unica anagrafica e richiedono riconciliazione esplicita. Nessuna omonimia fonde automaticamente storici o concede accessi. La scelta tecnica di riusare l'identità fisica storicamente chiamata `CandidatePerson` è documentata nel [runtime](../../03%20Software/RF-One%20Web/PEOPLE_DIRECTORY.md); non modifica le valutazioni specialistiche di Selection e non afferma che tutte le identità storiche siano già state riconciliate. Il database operativo non viene migrato nello sviluppo del prototipo.
