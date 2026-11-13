// Italian UI for the Bank "Rules and profiles" page and its rule/profile editor (UI_DEVELOPMENT_LANGUAGE_001,
// `03 Software/Shared UI/Development Language Policy.md`). The source strings stay English (shared/production
// default); this file translates them only when the page is rendered with <html lang="it"> — set by the local
// launcher through RFONE_UI_LANGUAGE=it.
//
// Safety rules:
//  - only a WHOLE text node (trimmed), a whole line of it, or a whole " · "-separated segment of it is replaced,
//    and only when it equals a dictionary key or matches an anchored pattern: stored facts (WHO/merchant names,
//    descriptions, account names, amounts, IDs, status codes) are never partially rewritten;
//  - user/AI conversation text and rule definitions (.flow-chat-text), anything inside [translate="no"] (stored
//    titles, descriptions, catalog names), <textarea>, <script> and <style> are never touched;
//  - WHO, WHY, WHAT, WHOM and Source are RF-One terms and stay as they are.
// Loaded with `defer` BEFORE flow.js, so the observer is in place before flow.js renders anything.
(function(){
'use strict';

const EXACT={
 // ---- Page (bank_flow.html) -------------------------------------------------------------------------
 'Rules and profiles · Bank · RF-One':'Regole e profili · Bank · RF-One',
 'Bank rules':'Regole Bank',
 'AI rules → extracted WHO → recognition profile → WHY and WHAT · WHOM from Source. Unrecognized transactions return to you for review.':'Regole AI → WHO estratto → profilo di riconoscimento → WHY e WHAT · WHOM dalla Source. I movimenti non riconosciuti tornano a te per la verifica.',
 'Breadcrumb':'Percorso',
 'Bank Reconciliation':'Riconciliazione bancaria',
 'Bank Reconciliation sections':'Sezioni di riconciliazione bancaria',
 'Rules and profiles':'Regole e profili',
 'Monthly bank and card reconciliation.':'Riconciliazione mensile di conti e carte.',
 'Import and Review':'Importa e verifica',
 'Review Transactions':'Controlla movimenti',
 'Monthly Export':'Esportazione mensile',
 'Configuration':'Configurazione',
 'Instructions':'Istruzioni',
 'AI rules and recognition profiles':'Regole AI e profili di riconoscimento',
 'Define how to read transactions and choose their purpose and recipient.':'Definisci come leggere i movimenti e sceglierne scopo e destinatario.',
 'WHO Rules':'Regole WHO',
 'History and rollback':'Cronologia e ripristino',
 'FIND WHY DIRECTLY':'TROVA IL WHY DIRETTAMENTE',
 'WHY patterns':'Pattern WHY',
 'Discover WHY Patterns':'Scopri i pattern WHY',
 'The AI reads every description format, proposes rules that determine WHY and joins formats that share the same conditions. Every proposal is tested on the whole history first. Only the rules you approve become active, and they run without AI. Human decisions are never changed.':'L’AI legge ogni formato di descrizione, propone regole che determinano il WHY e unisce i formati che condividono le stesse condizioni. Ogni proposta viene prima provata su tutta la cronologia. Diventano attive solo le regole che approvi, e funzionano senza AI. Le decisioni umane non vengono mai modificate.',
 'Approved WHY rules':'Regole WHY approvate',
 'READ THE DESCRIPTION':'LEGGI LA DESCRIZIONE',
 'AI rules':'Regole AI',
 'Find standard formats':'Trova i formati standard',
 '+ AI rule':'+ Regola AI',
 'Extract WHO only. Review and approve each suggested format.':'Estrai solo il WHO. Verifica e approva ogni formato suggerito.',
 'Search rules':'Cerca regole',
 'CHOOSE WHY AND WHAT':'SCEGLI WHY E WHAT',
 'Recognition profiles':'Profili di riconoscimento',
 '+ Recognition profile':'+ Profilo di riconoscimento',
 'For each WHO: possible WHY and WHAT values, selection criteria and sources to check. Uncertain transactions remain for review.':'Per ogni WHO: possibili valori WHY e WHAT, criteri di scelta e fonti da controllare. I movimenti incerti restano da verificare.',
 'Search profiles':'Cerca profili',
 'WHO or profile name':'WHO o nome del profilo',
 'Transactions to review':'Movimenti da verificare',
 'Research suggests a WHO. You decide until a profile also determines WHY and WHOM.':'La ricerca suggerisce un WHO. Decidi tu finché un profilo non determina anche WHY e WHOM.',
 'Open transactions':'Apri i movimenti',

 // ---- Dialogs (_bank_flow_rule_dialogs.html) ---------------------------------------------------------
 'Discuss':'Discuti',
 'Delete':'Elimina',
 'Close':'Chiudi',
 'How Works':'Come funziona',
 'How the rule and profile editor works':'Come funziona l’editor di regole e profili',
 'How renaming and deleting work':'Come funzionano rinomina ed eliminazione',
 'How history and rollback work':'Come funzionano cronologia e ripristino',
 'How creating a catalog entry works':'Come funziona la creazione di una voce di catalogo',
 'Current transaction':'Movimento corrente',
 'Back to transaction':'Torna al movimento',
 'This format already has rules. Choose which one to update.':'Questo formato ha già delle regole. Scegli quale aggiornare.',
 'Research online':'Ricerca online',
 'WHAT follows the chosen WHY: only the WHAT of the selected WHY values can be chosen. One WHY/WHAT pair becomes the profile default. Multiple choices require conditions in this profile. Leave WHAT empty only when WHY settles a balance-sheet account. WHOM defaults to the Source owner and can be changed on the transaction before confirmation.':'Il WHAT segue il WHY scelto: si può scegliere solo il WHAT dei WHY selezionati. Una coppia WHY/WHAT diventa il valore predefinito del profilo. Più scelte richiedono condizioni in questo profilo. Lascia vuoto il WHAT solo quando il WHY chiude un conto patrimoniale. WHOM è predefinito dal titolare della Source e si può cambiare sul movimento prima della conferma.',
 'Use these choices':'Usa queste scelte',
 'Save draft':'Salva bozza',
 'Preview':'Simula',
 'Explain how to decide':'Spiega come decidere',
 'Describe the format or explain when to choose WHY and WHOM':'Descrivi il formato o spiega quando scegliere WHY e WHOM',
 'Send':'Invia',
 'Save and apply':'Salva e applica',
 'Save and apply to the current record':'Salva e applica al movimento corrente',
 'Save and apply to all repository records':'Salva e applica a tutti i movimenti del repository',
 'Save':'Salva',
 'Review the preview, then confirm. Only matching records still to reconcile are included.':'Verifica la simulazione, poi conferma. Sono inclusi solo i movimenti corrispondenti ancora da riconciliare.',
 'Name':'Nome',
 'Cancel':'Annulla',
 'Confirm':'Conferma',
 'Rollback restores only transactions that still match the application result. Later changes are preserved and reported.':'Il ripristino riporta indietro solo i movimenti che corrispondono ancora al risultato dell’applicazione. Le modifiche successive sono conservate e segnalate.',
 'Full application history':'Cronologia completa delle applicazioni',
 'New entry':'Nuova voce',
 'Accounting destination':'Destinazione contabile',
 'Legal name, only for a new company':'Ragione sociale, solo per una nuova società',
 'Confirm and create':'Conferma e crea',

 // ---- flow.js: lists ---------------------------------------------------------------------------------
 'Operation could not be completed.':'Operazione non completata.',
 'Paused':'In pausa',
 'Active for future imports':'Attiva per le importazioni future',
 'Inactive for new imports':'Non attiva per le nuove importazioni',
 'Rename':'Rinomina',
 'Previous text retained in history':'Testo precedente conservato nella cronologia',
 'No matching AI rules.':'Nessuna regola AI corrispondente.',
 'Edit draft':'Modifica bozza',
 'Saved changes':'Modifiche salvate',
 'Drafts':'Bozze',
 'Complete WHY and WHOM':'Completa WHY e WHOM',
 'Refine this WHO’s cases':'Affina i casi di questo WHO',
 'Define WHY and WHOM in chat':'Definisci WHY e WHOM in chat',
 'Rename profile':'Rinomina profilo',
 'Delete profile and cases':'Elimina profilo e casi',
 'Incomplete: this profile cannot reconcile transactions yet.':'Incompleto: questo profilo non può ancora riconciliare movimenti.',
 'No matching profiles.':'Nessun profilo corrispondente.',
 'Awaiting automatic reconciliation':'In attesa di riconciliazione automatica',
 'Research to review':'Ricerca da verificare',
 'Transaction changed: review needed':'Movimento modificato: serve una verifica',
 'Needs clarification':'Serve un chiarimento',
 'Processing incomplete':'Elaborazione incompleta',
 'Review transaction':'Verifica movimento',
 'Discuss / Recognition profile':'Discuti / Profilo di riconoscimento',
 'No new transactions to review.':'Nessun nuovo movimento da verificare.',

 // ---- flow.js: editor ----------------------------------------------------------------------------------
 'Date':'Data',
 'Amount':'Importo',
 'Account':'Conto',
 'Owner':'Titolare',
 'No description':'Nessuna descrizione',
 'Source owner':'Titolare della Source',
 'Choose WHOM…':'Scegli WHOM…',
 'This choice applies only to this transaction.':'Questa scelta vale solo per questo movimento.',
 'From the Source or your existing manual choice.':'Dalla Source o dalla tua scelta manuale esistente.',
 'The Source has no owner. Choose WHOM to continue.':'La Source non ha un titolare. Scegli WHOM per continuare.',
 'WHOM · current transaction':'WHOM · movimento corrente',
 'Updating the preview…':'Aggiornamento della simulazione…',
 'New AI rule':'Nuova regola AI',
 'New recognition profile':'Nuovo profilo di riconoscimento',
 'Explain the merchant and payment purpose. I will prepare WHO and WHY together.':'Spiega il commerciante e lo scopo del pagamento. Preparerò WHO e WHY insieme.',
 'Research WHO and choose WHY and WHAT. WHOM defaults to the Source.':'Ricerca il WHO e scegli WHY e WHAT. WHOM predefinito: dalla Source.',
 'Choose the rule to update':'Scegli la regola da aggiornare',
 'You':'Tu',
 'Example:':'Esempio:',
 'Transaction values:':'Valori del movimento:',
 'Explain when to use these values.':'Spiega quando usare questi valori.',
 'Save for future records':'Salva per i movimenti futuri',
 'Explain when to use the selected WHY and WHAT':'Spiega quando usare WHY e WHAT selezionati',
 'Explain who was paid and when each payment purpose applies':'Spiega chi è stato pagato e quando vale ogni scopo di pagamento',
 'Review and create':'Verifica e crea',
 'Researching WHO and catalog choices…':'Ricerca del WHO e delle scelte di catalogo…',
 'Review the proposal and choose the catalog entries.':'Verifica la proposta e scegli le voci del catalogo.',
 'Choose WHO, WHY and WHAT from the available lists.':'Scegli WHO, WHY e WHAT dagli elenchi disponibili.',
 'Preparing profile…':'Preparazione del profilo…',
 'Preview the real transactions before saving.':'Simula sui movimenti reali prima di salvare.',
 'Explain when each selected WHY and WHAT applies in the chat.':'Spiega in chat quando vale ciascun WHY e WHAT selezionato.',
 'Review the preview, then confirm save and apply.':'Verifica la simulazione, poi conferma salvataggio e applicazione.',
 'Preparing your instructions and preview…':'Preparazione delle istruzioni e della simulazione…',
 'Answer the question in chat before saving. Your instructions are kept.':'Rispondi alla domanda in chat prima di salvare. Le tue istruzioni sono conservate.',
 'Clarifying the instructions…':'Chiarimento delle istruzioni…',
 'Saving…':'Salvataggio…',
 'Draft saved. Active rule unchanged.':'Bozza salvata. La regola attiva non è cambiata.',
 'Selecting rule…':'Selezione della regola…',
 'Existing rule selected. Save the draft, then preview.':'Regola esistente selezionata. Salva la bozza, poi simula.',
 'Send your message first.':'Invia prima il tuo messaggio.',
 'Checking real transactions. No changes are being made…':'Controllo dei movimenti reali. Nessuna modifica in corso…',
 'Sending your text to the AI first…':'Invio prima del tuo testo all’AI…',
 'Your instructions are kept. Clarify the remaining question above, then preview again.':'Le tue istruzioni sono conservate. Chiarisci la domanda rimasta qui sopra, poi simula di nuovo.',
 'Review the results, then choose where to apply.':'Verifica i risultati, poi scegli dove applicare.',
 'Extracted WHO':'WHO estratto',
 'Opening recognition profile…':'Apertura del profilo di riconoscimento…',
 'Define this profile, preview it, then save it to return to the list.':'Definisci questo profilo, simulalo, poi salvalo per tornare all’elenco.',
 'Profile saved. Continue with the next transaction.':'Profilo salvato. Continua con il movimento successivo.',
 'Back to the extraction preview.':'Ritorno alla simulazione di estrazione.',

 // ---- flow.js: preview ---------------------------------------------------------------------------------
 'Not configured':'Non configurato',
 'Left undecided:':'Non decisi:',
 'Prepared WHO and WHY':'WHO e WHY preparati',
 'WHO and WHY prepared together':'WHO e WHY preparati insieme',
 'Current WHY':'WHY attuale',
 'Proposed WHY':'WHY proposto',
 'Review these classifications before saving. Conversation and Preview have not changed them.':'Verifica queste classificazioni prima di salvare. Conversazione e simulazione non le hanno modificate.',
 'WHAT comes from WHY; the Source owner stays unchanged.':'Il WHAT deriva dal WHY; il titolare della Source resta invariato.',
 'Preview on real transactions':'Simulazione sui movimenti reali',
 'Current rule':'Regola attuale',
 'Draft':'Bozza',
 'Edit instructions':'Modifica istruzioni',
 'This preview shows the last saved version, not your latest request:':'Questa simulazione mostra l’ultima versione salvata, non la tua ultima richiesta:',
 'the AI did not accept it. Continue the conversation (Edit) until the AI restates the complete rule, then preview again.':'l’AI non l’ha accettata. Continua la conversazione (Modifica) finché l’AI non riformula la regola completa, poi simula di nuovo.',
 'Save this profile to return to the transaction list. Existing transactions stay unchanged until you apply the extraction rule.':'Salva questo profilo per tornare all’elenco dei movimenti. I movimenti esistenti restano invariati finché non applichi la regola di estrazione.',
 'Save profile':'Salva profilo',
 'Photo':'Foto',
 'Check highlighted name':'Controlla il nome evidenziato',
 'Not extracted':'Non estratto',
 'Split':'Ripartito',
 'Source owner not configured':'Titolare della Source non configurato',
 'WHOM: Choose above':'WHOM: Scegli sopra',
 'WHY: — (needs a profile)':'WHY: — (serve un profilo)',
 'No assignment':'Nessuna assegnazione',
 'WHO and WHY prepared':'WHO e WHY preparati',
 'Ready to apply · confirmation required':'Pronto da applicare · conferma richiesta',
 'Ready to reconcile':'Pronto da riconciliare',
 'WHO recognised by this rule':'WHO riconosciuto da questa regola',
 'Choose WHOM above':'Scegli WHOM sopra',
 'Needs review':'Da verificare',
 'Review the Source classifications above; human movement decisions stay protected.':'Verifica le classificazioni della Source qui sopra; le decisioni umane sui movimenti restano protette.',
 'To reconcile it, its WHY comes from the WHO profile (Photo).':'Per riconciliarlo, il WHY viene dal profilo del WHO (Foto).',
 'Saved':'Salvato',
 'Transaction':'Movimento',
 'Before':'Prima',
 'Proposed WHO / WHY / WHAT':'WHO / WHY / WHAT proposti',
 'Result':'Esito',
 'Save the WHO rule and the exact WHO + Source classifications listed above. Confirmed movement decisions stay protected.':'Salva la regola WHO e le classificazioni esatte WHO + Source elencate sopra. Le decisioni confermate sui movimenti restano protette.',
 'Save and apply to future imports':'Salva e applica nel futuro',
 'Save and apply to existing':'Salva e applica agli esistenti',
 'Edit':'Modifica',
 'Current record only':'Solo il movimento corrente',
 'All matching repository records still to reconcile':'Tutti i movimenti corrispondenti del repository ancora da riconciliare',
 'Future records only':'Solo i movimenti futuri',
 'Confirm save':'Conferma salvataggio',
 'Confirm save and apply':'Conferma salvataggio e applicazione',
 'Confirmation also saves this profile for future imports. Applied changes can be rolled back.':'La conferma salva anche questo profilo per le importazioni future. Le modifiche applicate si possono ripristinare.',
 'Save updates this profile for future imports and reconciles only this transaction. Rollback is available in reconciliation history.':'Il salvataggio aggiorna questo profilo per le importazioni future e riconcilia solo questo movimento. Il ripristino è disponibile nella cronologia della riconciliazione.',
 'Save profile and reconcile this transaction':'Salva profilo e riconcilia questo movimento',
 'Save rule':'Salva regola',
 'activates it at once: WHO Search Text and the reconciliation engine read the WHO of every matching transaction, past and future, with this rule.':'la attiva subito: WHO Search Text e il motore di riconciliazione leggono con questa regola il WHO di ogni movimento corrispondente, passato e futuro.',
 'Save and apply to existing transactions':'Salva e applica ai movimenti esistenti',
 'also reconciles now those that are ready (WHO, WHY and WHOM complete) and queues the others for automatic reconciliation; it can be rolled back.':'riconcilia subito anche quelli pronti (WHO, WHY e WHOM completi) e mette in coda gli altri per la riconciliazione automatica; si può ripristinare.',
 'Save publishes this version for future imports. Save and apply to repository also updates existing transactions. Applied changes can be rolled back without overwriting later edits.':'Salva pubblica questa versione per le importazioni future. Salva e applica al repository aggiorna anche i movimenti esistenti. Le modifiche applicate si possono ripristinare senza sovrascrivere le modifiche successive.',
 'Saving for future imports…':'Salvataggio per le importazioni future…',
 'Applying preview results…':'Applicazione dei risultati della simulazione…',
 'Profile saved and transaction reconciled.':'Profilo salvato e movimento riconciliato.',
 'Rule saved and active for future imports.':'Regola salvata e attiva per le importazioni future.',

 // ---- flow.js: format search, manage, history, catalog -----------------------------------------------
 'Looking for recurring formats across all transactions…':'Ricerca dei formati ricorrenti su tutti i movimenti…',
 'One format · extraction variants to clarify in chat':'Un formato · varianti di estrazione da chiarire in chat',
 'Discuss and preview on real transactions':'Discuti e simula sui movimenti reali',
 'Change the name only.':'Cambia solo il nome.',
 'Discard this proposed format or draft?':'Scartare questo formato proposto o questa bozza?',
 'Delete this profile, its knowledge and all its cases? Transactions and rollback history are retained.':'Eliminare questo profilo, le sue conoscenze e tutti i suoi casi? I movimenti e la cronologia dei ripristini sono conservati.',
 'Delete this rule from automatic processing? Transactions and rollback history are retained.':'Eliminare questa regola dall’elaborazione automatica? I movimenti e la cronologia dei ripristini sono conservati.',
 'Save name':'Salva nome',
 'Delete permanently':'Elimina definitivamente',
 'Enter a name.':'Inserisci un nome.',
 'Name updated.':'Nome aggiornato.',
 'Entry deleted.':'Voce eliminata.',
 'Loading history…':'Caricamento della cronologia…',
 'already rolled back':'già ripristinata',
 'Roll back this application':'Ripristina questa applicazione',
 'No applications recorded.':'Nessuna applicazione registrata.',
 'New WHY':'Nuovo WHY',
 'New WHOM':'Nuovo WHOM',
 'Without a legal name, this creates a virtual recipient. Enter a legal name only to create a new company.':'Senza ragione sociale si crea un destinatario virtuale. Inserisci una ragione sociale solo per creare una nuova società.',
 'Choose an existing accounting destination or set it later.':'Scegli una destinazione contabile esistente o impostala più tardi.',
 'To be defined':'Da definire',
 'Entry created. Continue the chat to use it in the profile conditions.':'Voce creata. Continua la chat per usarla nelle condizioni del profilo.',
 'Propose the Recognition Profile of this WHO from its Labels, its approved WHYs and its history. Ask me what is still unclear.':'Proponi il Profilo di riconoscimento di questo WHO a partire dalle sue etichette, dai suoi WHY approvati e dalla sua cronologia. Chiedimi ciò che non è ancora chiaro.',
 'Some groups could not be analyzed. Run the search again.':'Alcuni gruppi non sono stati analizzati. Ripeti la ricerca.',

 // ---- who_review.js (format review under "Find standard formats") ------------------------------------
 'WHO coverage':'Copertura WHO',
 'Description structures examined (not read by an approved rule)':'Strutture di descrizione esaminate (non lette da una regola approvata)',
 'Proposed WHO rules':'Regole WHO proposte',
 'Movements selected by the proposed rules (each counted once)':'Movimenti selezionati dalle regole proposte (ciascuno contato una volta)',
 'Distinct WHO extracted':'WHO distinti estratti',
 'Movements read differently by two proposed rules (to resolve in the review)':'Movimenti letti in modo diverso da due regole proposte (da risolvere nella verifica)',
 'Movements with one single proposed WHO':'Movimenti con un solo WHO proposto',
 'Recognitions marked wrong':'Riconoscimenti segnati come errati',
 'Verified recognitions (rule reviewed, not marked wrong)':'Riconoscimenti verificati (regola verificata, non segnati come errati)',
 'Already recognized by approved WHO rules':'Già riconosciuti da regole WHO approvate',
 'Recognized by approved or proposed rules':'Riconosciuti da regole approvate o proposte',
 'Movements without a recognized WHO':'Movimenti senza WHO riconosciuto',
 '…of which the AI says the description names no counterparty (transfers, checks, interest, fees)':'…di cui, secondo l’AI, la descrizione non nomina alcuna controparte (bonifici, assegni, interessi, commissioni)',
 'Recognized among movements whose description names a counterparty':'Riconosciuti tra i movimenti la cui descrizione nomina una controparte',
 'Proposed = what the rules would extract. Verified = you reviewed the rule and did not mark the movement as wrong.':'Proposto = ciò che le regole estrarrebbero. Verificato = hai verificato la regola e non hai segnato il movimento come errato.',
 'WHO changes':'Il WHO cambia',
 'No longer selected':'Non più selezionato',
 'Newly selected':'Selezionato ora',
 'Change':'Variazione',
 'Description':'Descrizione',
 'WHO before':'WHO prima',
 'WHO now':'WHO ora',
 'Corrected rule tested on the whole history:':'Regola corretta provata su tutta la cronologia:',
 'observed once: candidate, not recurring':'osservato una volta: candidato, non ricorrente',
 'reviewed':'verificato',
 'Tick only the movements whose WHO is wrong. Ticks are review notes: they change no WHO and no classification.':'Spunta solo i movimenti con il WHO errato. Le spunte sono note di verifica: non cambiano alcun WHO né alcuna classificazione.',
 'Wrong':'Errato',
 'WHO extracted':'WHO estratto',
 'Save review':'Salva verifica',
 'What is wrong (optional)':'Cosa è errato (facoltativo)',
 'E.g. the city is included in the name':'Es. la città è inclusa nel nome',
 'Correct the rule with AI':'Correggi la regola con l’AI',
 'Review saved. Nothing was changed in Bank.':'Verifica salvata. Nulla è stato modificato in Bank.',
 'The AI is correcting the rule; RF-One then tests it on every movement…':'L’AI sta correggendo la regola; RF-One la prova poi su ogni movimento…',
 'Corrected rule proposed. Nothing is active until you approve it.':'Regola corretta proposta. Nulla è attivo finché non la approvi.',
 'Loading the movements this rule selects…':'Caricamento dei movimenti selezionati da questa regola…',
 'Loading…':'Caricamento…',

 // ---- Server messages shown by flow.js (JSON `error`, preview notes, blocking reasons) -----------------
 // bank_flow_routes.py
 'Conversation or preview unavailable.':'Conversazione o simulazione non disponibile.',
 'Draft deleted.':'Bozza eliminata.',
 'The preview expired. Run it again on current transactions.':'La simulazione è scaduta. Ripetila sui movimenti attuali.',
 'This saved rule has no executable interpretation.':'Questa regola salvata non ha un’interpretazione eseguibile.',
 'Enter WHO before saving the profile.':'Inserisci il WHO prima di salvare il profilo.',
 'This WHO has multiple current profiles. Choose and consolidate them before saving.':'Questo WHO ha più profili attuali. Sceglili e consolidali prima di salvare.',
 'The transaction changed. Reopen the research from that row.':'Il movimento è cambiato. Riapri la ricerca da quella riga.',
 'The extraction rule changed. Return to its preview.':'La regola di estrazione è cambiata. Torna alla sua simulazione.',
 'The extraction rule is not ready.':'La regola di estrazione non è pronta.',
 'Keep the WHO selected by the extraction rule. Return to the rule to change it.':'Mantieni il WHO scelto dalla regola di estrazione. Torna alla regola per cambiarlo.',
 'Bank context sharing with ChatGPT has not been approved. No data was sent.':'La condivisione del contesto Bank con ChatGPT non è stata approvata. Nessun dato è stato inviato.',
 'The rule changed or was deleted. Reopen it.':'La regola è cambiata o è stata eliminata. Riaprila.',
 'Operation could not be completed. Your conversation is preserved. Please try again.':'Operazione non completata. La conversazione è conservata. Riprova.',
 'Transaction unavailable.':'Movimento non disponibile.',
 'Invalid type.':'Tipo non valido.',
 'Rule unavailable.':'Regola non disponibile.',
 'Choose a transaction from the extraction preview.':'Scegli un movimento dalla simulazione di estrazione.',
 'The extraction preview changed. Refresh it first.':'La simulazione di estrazione è cambiata. Aggiornala prima.',
 'The transaction changed. Refresh the extraction preview.':'Il movimento è cambiato. Aggiorna la simulazione di estrazione.',
 'No WHO was extracted from this transaction.':'Da questo movimento non è stato estratto alcun WHO.',
 'WHO unavailable.':'WHO non disponibile.',
 'Format unavailable. Refresh the search results.':'Formato non disponibile. Aggiorna i risultati della ricerca.',
 'Format deleted.':'Formato eliminato.',
 'Open a transaction profile for this guided run.':'Apri un profilo dal movimento per questa riconciliazione guidata.',
 'This conversation concerns a different instruction type.':'Questa conversazione riguarda un altro tipo di istruzione.',
 'The conversation changed. Reopen it before continuing.':'La conversazione è cambiata. Riaprila prima di continuare.',
 'Confirm creation of this entry.':'Conferma la creazione di questa voce.',
 'Invalid name.':'Nome non valido.',
 'Invalid entry type.':'Tipo di voce non valido.',
 'Clarify the extraction variants in chat before previewing the draft.':'Chiarisci in chat le varianti di estrazione prima di simulare la bozza.',
 'Save a draft with your extraction instructions first.':'Salva prima una bozza con le tue istruzioni di estrazione.',
 'The draft needs clarification.':'La bozza ha bisogno di chiarimenti.',
 'Preview requires WHO extraction instructions.':'La simulazione richiede istruzioni di estrazione del WHO.',
 'Choose a transaction before setting WHOM.':'Scegli un movimento prima di impostare WHOM.',
 'Choose an active WHOM from the list.':'Scegli un WHOM attivo dall’elenco.',
 'Choose the existing rule to update first.':'Scegli prima la regola esistente da aggiornare.',
 'Resolve the questions in chat before previewing.':'Risolvi le domande in chat prima di simulare.',
 'Invalid profile save scope.':'Ambito di salvataggio del profilo non valido.',
 'Choose a transaction first.':'Scegli prima un movimento.',
 'Choose current transaction or repository for this run.':'Scegli movimento corrente o repository per questa esecuzione.',
 'This transaction is already reconciled. Reopen the pending queue.':'Questo movimento è già riconciliato. Riapri la coda dei movimenti in attesa.',
 'Check WHO: the final number may belong to the merchant name. No automatic assignment.':'Controlla il WHO: il numero finale potrebbe far parte del nome del commerciante. Nessuna assegnazione automatica.',
 'Choose an accounting destination before reconciling.':'Scegli una destinazione contabile prima di riconciliare.',
 'Confirm the profile to reconcile this transaction.':'Conferma il profilo per riconciliare questo movimento.',
 'No complete transaction to apply. Edit the profile or save for future records.':'Nessun movimento completo da applicare. Modifica il profilo o salva per i movimenti futuri.',
 'Complete Source ownership before saving WHO and WHY.':'Completa il titolare delle Source prima di salvare WHO e WHY.',
 'No reviewed WHO + Source assignment; left unchanged.':'Nessuna assegnazione WHO + Source verificata; lasciato invariato.',
 'Open a recognition profile for this research.':'Apri un profilo di riconoscimento per questa ricerca.',
 'Choose WHO or start from a transaction.':'Scegli il WHO o parti da un movimento.',
 'The profile or catalogs changed. Retry research.':'Il profilo o i cataloghi sono cambiati. Ripeti la ricerca.',
 'Start profile research first.':'Avvia prima la ricerca del profilo.',
 'Research concerns this profile WHO. Open a different WHO to rename it.':'La ricerca riguarda il WHO di questo profilo. Apri un altro WHO per rinominarlo.',
 'Choose WHY from Configuration.':'Scegli il WHY dalla Configurazione.',
 'Choose WHAT from Configuration.':'Scegli il WHAT dalla Configurazione.',
 'WHAT derives from WHY: choose only the WHAT of the selected WHY values.':'Il WHAT deriva dal WHY: scegli solo il WHAT dei WHY selezionati.',
 'Choose WHAT from Configuration for these WHY values.':'Scegli il WHAT dalla Configurazione per questi WHY.',
 'Use the accounting destination linked to WHY':'Usa la destinazione contabile collegata al WHY',
 'Choose the rule to update.':'Scegli la regola da aggiornare.',
 'Delete the published rule instead.':'Elimina invece la regola pubblicata.',
 'This format was published. Reopen its rule.':'Questo formato è stato pubblicato. Riapri la sua regola.',
 'Keep your message within 8,000 characters.':'Scrivi un messaggio entro 8.000 caratteri.',
 'This save action is for AI rules.':'Questa azione di salvataggio vale per le regole AI.',
 'Choose future only, or all transactions and future.':'Scegli solo il futuro, oppure tutti i movimenti e il futuro.',
 'Choose a transaction profile first.':'Scegli prima un profilo dal movimento.',
 'Save this profile first. Apply existing transactions from the extraction rule preview.':'Salva prima questo profilo. Applica i movimenti esistenti dalla simulazione della regola di estrazione.',
 'The save scope differs from the preview. Preview the chosen scope first.':'L’ambito di salvataggio è diverso da quello simulato. Simula prima l’ambito scelto.',
 'Preview the current transaction first.':'Simula prima il movimento corrente.',
 'A transaction was already reconciled. Refresh the preview.':'Un movimento è già stato riconciliato. Aggiorna la simulazione.',
 'The current transaction needs a definite profile choice. Edit and preview again.':'Il movimento corrente richiede una scelta definita del profilo. Modifica e simula di nuovo.',
 'No complete transaction to apply.':'Nessun movimento completo da applicare.',
 'The preview is no longer valid. Run it again.':'La simulazione non è più valida. Ripetila.',
 'Transactions changed. Run the preview again.':'I movimenti sono cambiati. Ripeti la simulazione.',
 'Choose future records or existing records.':'Scegli movimenti futuri o movimenti esistenti.',
 'Review and confirm both WHO and WHY before saving.':'Verifica e conferma sia WHO sia WHY prima di salvare.',
 'Preview WHO and WHY first.':'Simula prima WHO e WHY.',
 'A profile for this WHO was created or changed. Reopen it before saving; no copy was created.':'Un profilo per questo WHO è stato creato o modificato. Riaprilo prima di salvare; non è stata creata alcuna copia.',
 'This extraction rule already exists for this format. Reopen the format and choose which rule to update; no copy was saved.':'Questa regola di estrazione esiste già per questo formato. Riapri il formato e scegli quale regola aggiornare; non è stata salvata alcuna copia.',
 'Enter a valid name.':'Inserisci un nome valido.',
 'Profile unavailable.':'Profilo non disponibile.',
 'Profile deleted.':'Profilo eliminato.',
 // bank_conversation_intent.py
 'Name the merchant for the WHO and WHY proposal.':'Indica il commerciante per la proposta di WHO e WHY.',
 'Explain when each WHY applies.':'Spiega quando vale ciascun WHY.',
 'Use distinct, supported Source conditions for each WHY.':'Usa condizioni di Source distinte e supportate per ciascun WHY.',
 'Choose an active WHY from Configuration.':'Scegli un WHY attivo dalla Configurazione.',
 'Name the WHY to use in each case.':'Indica il WHY da usare in ciascun caso.',
 'These Source conditions overlap. Explain which one takes precedence.':'Queste condizioni di Source si sovrappongono. Spiega quale prevale.',
 'Source owner is not configured.':'Il titolare della Source non è configurato.',
 'More than one WHY matches a Source. Clarify the conditions.':'Più di un WHY corrisponde a una Source. Chiarisci le condizioni.',
 'No requested case covers this Source.':'Nessun caso richiesto copre questa Source.',
 'Exact WHO + Source pairs for the Sources listed here. New Sources require their own classification.':'Coppie esatte WHO + Source per le Source elencate qui. Le nuove Source richiedono una propria classificazione.',
 'The WHO + Source classifications changed. Preview again before saving.':'Le classificazioni WHO + Source sono cambiate. Simula di nuovo prima di salvare.',
 'No configured Source can receive this classification. Complete Source ownership first.':'Nessuna Source configurata può ricevere questa classificazione. Completa prima il titolare delle Source.',
 'Human decision protected.':'Decisione umana protetta.',
 'Possible duplicate requires review.':'Possibile duplicato da verificare.',
 'Split allocations require review.':'Le ripartizioni richiedono una verifica.',
 'Choose WHOM: Source ownership is missing for this transaction.':'Scegli WHOM: per questo movimento manca il titolare della Source.',
 'Choose an active accounting destination first.':'Scegli prima una destinazione contabile attiva.',
 'Ready to apply the reviewed WHO and WHY.':'Pronto ad applicare WHO e WHY verificati.',
 // rfone_data_store/bank_reconciliation/flow.py
 'Invalid proposal. Continue the conversation.':'Proposta non valida. Continua la conversazione.',
 'An AI rule extracts WHO only.':'Una regola AI estrae solo il WHO.',
 'Name the literal merchant to read from the description.':'Indica il commerciante esatto da leggere nella descrizione.',
 'Clarify where WHO begins and ends.':'Chiarisci dove inizia e finisce il WHO.',
 'Invalid start of WHO.':'Inizio del WHO non valido.',
 'The whole description is not a WHO: say where WHO ends, or add a prefix.':'L’intera descrizione non è un WHO: indica dove finisce il WHO o aggiungi un prefisso.',
 'Only {date}, {number} and {code} may stand for the variable parts.':'Solo {date}, {number} e {code} possono indicare le parti variabili.',
 'The end delimiter for WHO is missing.':'Manca il delimitatore finale del WHO.',
 'Invalid delimiter.':'Delimitatore non valido.',
 'Invalid numeric suffix policy.':'Regola del suffisso numerico non valida.',
 'Invalid name cleanup.':'Pulizia del nome non valida.',
 'Invalid delimiters.':'Delimitatori non validi.',
 'The profile must identify a WHO.':'Il profilo deve identificare un WHO.',
 'Define the allowed WHY and WHOM values.':'Definisci i valori WHY e WHOM ammessi.',
 'A WHY or WHOM is missing or inactive. Create it before approving the profile.':'Un WHY o WHOM manca o non è attivo. Crealo prima di approvare il profilo.',
 'The profile still has unresolved questions.':'Il profilo ha ancora domande irrisolte.',
 'Define when each WHY and WHOM should be chosen.':'Definisci quando scegliere ciascun WHY e WHOM.',
 'Choices must belong to the profile’s allowed WHY and WHOM values.':'Le scelte devono appartenere ai valori WHY e WHOM ammessi dal profilo.',
 'WHOM comes from the Source, not the profile.':'WHOM viene dalla Source, non dal profilo.',
 'Select WHAT from Configuration.':'Seleziona il WHAT dalla Configurazione.',
 'A balance-sheet destination must be linked to WHY; it is not a WHAT.':'Una destinazione patrimoniale deve essere collegata al WHY; non è un WHAT.',
 'Invalid conditions.':'Condizioni non valide.',
 'Clarify the profile condition.':'Chiarisci la condizione del profilo.',
 'Invalid condition list.':'Elenco di condizioni non valido.',
 'Invalid criterion.':'Criterio non valido.',
 'The required source is not connected. Define where the data is and how to retrieve it. This profile remains incomplete.':'La fonte richiesta non è collegata. Definisci dove si trovano i dati e come recuperarli. Questo profilo resta incompleto.',
 'Rules extract different WHO values.':'Le regole estraggono WHO diversi.',
 'This transaction is split between multiple WHOM values. Edit its allocations in Review.':'Questo movimento è ripartito tra più WHOM. Modifica le ripartizioni in Controlla movimenti.',
 'Choose WHOM for this transaction. The Source has no owner.':'Scegli WHOM per questo movimento. La Source non ha un titolare.',
 'Profile proposes WHY and WHAT; confirm the transaction in Review.':'Il profilo propone WHY e WHAT; conferma il movimento in Controlla movimenti.',
 'Profile matched with definite WHY and WHOM.':'Profilo applicabile con WHY e WHOM definiti.',
 'No profile, insufficient information or ambiguous choices.':'Nessun profilo, informazioni insufficienti o scelte ambigue.',
 'Profile no longer available.':'Profilo non più disponibile.',
 'WHY or WHOM no longer available.':'WHY o WHOM non più disponibile.',
 'Multiple allocations require manual review.':'Più ripartizioni richiedono una verifica manuale.',
};

const SEARCH_STATE={'complete':'completata','partially complete':'completata in parte','incomplete':'incompleta'};

// Anchored patterns for text whose variable part is data (counts, ids, names). Replacement: $n = the captured
// data unchanged; {tn} = the captured part translated when it is itself a known message (else unchanged).
const PATTERNS=[
 [/^Version (\d+)$/,'Versione $1'],
 [/^Existing default WHY for this WHO: ([\s\S]+)$/,'WHY predefinito esistente per questo WHO: $1'],
 [/^Show (\d+) more profiles$/,'Mostra altri $1 profili'],
 [/^Suggested WHO: ([\s\S]+)$/,'WHO suggerito: $1'],
 [/^Default: ([\s\S]+)$/,'Predefinito: {t1}'],
 [/^Current transaction #(\S+)$/,'Movimento corrente #$1'],
 [/^Transaction #(\S+)$/,'Movimento #$1'],
 [/^Recognition profile · ([\s\S]+)$/,'Profilo di riconoscimento · $1'],
 [/^Current rule definition: ([\s\S]+)$/,'Definizione attuale della regola: $1'],
 [/^Suggested new (WHY|WHOM|WHAT):$/,'Nuovo $1 suggerito:'],
 [/^Profile saved\. Refresh the rule preview: ([\s\S]+)$/,'Profilo salvato. Aggiorna la simulazione della regola: {t1}'],
 [/^([\s\S]+) WHAT comes from WHY; the Source owner stays unchanged\.$/,'{t1} Il WHAT deriva dal WHY; il titolare della Source resta invariato.'],
 [/^(\d+) matching$/,'$1 corrispondenti'],
 [/^(\d+) with WHO and WHY prepared$/,'$1 con WHO e WHY preparati'],
 [/^(\d+) ready to apply$/,'$1 pronti da applicare'],
 [/^(\d+) need your input$/,'$1 richiedono il tuo intervento'],
 [/^Source default: ([\s\S]+)$/,'Predefinito della Source: $1'],
 [/^(\d+) transactions updated\. Profile saved\. Rollback is available in history\.$/,'$1 movimenti aggiornati. Profilo salvato. Il ripristino è disponibile nella cronologia.'],
 [/^WHO rule and (\d+) Source classifications saved\.$/,'Regola WHO e $1 classificazioni della Source salvate.'],
 [/^Search in progress: (\d+) transactions examined, (\d+) of (\S+) groups analyzed\.$/,'Ricerca in corso: $1 movimenti esaminati, $2 di $3 gruppi analizzati.'],
 [/^Search (complete|partially complete|incomplete): (\d+) transactions examined\.\s*([\s\S]*)$/,(m,t)=>`Ricerca ${SEARCH_STATE[m[1]]}: ${m[2]} movimenti esaminati. ${t(m[3])}`.trim()],
 [/^Some groups could not be analyzed\. Run the search again\.\s+([\s\S]+)$/,'Alcuni gruppi non sono stati analizzati. Ripeti la ricerca. {t1}'],
 [/^Rename: ([\s\S]+)$/,'Rinomina: $1'],
 [/^Delete: ([\s\S]+)$/,'Elimina: $1'],
 [/^Application #(\S+)$/,'Applicazione #$1'],
 [/^(\d+) transactions updated$/,'$1 movimenti aggiornati'],
 [/^(\d+) transactions restored; (\d+) kept because they were changed later\.$/,'$1 movimenti ripristinati; $2 mantenuti perché modificati in seguito.'],
 [/^I created (WHY|WHOM) "([\s\S]*)"\. Use it in the agreed cases\.$/,'Ho creato $1 "$2". Usalo nei casi concordati.'],
 [/^Unable to load Bank: ([\s\S]+)$/,'Impossibile caricare Bank: {t1}'],
 // server messages with a variable part
 [/^This extraction rule already exists: ([\s\S]+) \(#(\d+)\)\. Open that rule to edit it\.$/,'Questa regola di estrazione esiste già: $1 (#$2). Apri quella regola per modificarla.'],
 [/^Choose or create the exact WHY “([\s\S]+)”; no unrelated WHY was substituted\.$/,'Scegli o crea esattamente il WHY “$1”; nessun altro WHY è stato sostituito.'],
 [/^Complete WHAT for WHY “([\s\S]+)” in Configuration first\.$/,'Completa prima il WHAT del WHY “$1” in Configurazione.'],
 // who_review.js
 [/^(\S+) seen only once$/,'$1 viste una sola volta'],
 [/^(\S+) search passes$/,'$1 passaggi di ricerca'],
 [/^(\S+): (\S+) recurring$/,'$1: $2 ricorrenti'],
 [/^(\S+) observed once \(candidates\)$/,'$1 osservate una volta (candidate)'],
 [/^(\S+) general \(WHO opens the description, used only where no specific rule reads\)$/,'$1 generali (il WHO apre la descrizione, usate solo dove nessuna regola specifica legge)'],
 [/^(\S+) of (\S+) \((\S+)%\)$/,'$1 di $2 ($3%)'],
 [/^(\S+) rules reviewed$/,'$1 regole verificate'],
 [/^(\S+) \((\S+) rules\)$/,'$1 ($2 regole)'],
 [/^(\S+) \((\S+) structures\) — proposed, not verified$/,'$1 ($2 strutture) — proposto, non verificato'],
 [/^(\S+) selected before, (\S+) now$/,'$1 selezionati prima, $2 ora'],
 [/^(\d+) unchanged$/,'$1 invariati'],
 [/^(\d+) with a different WHO$/,'$1 con un WHO diverso'],
 [/^(\d+) no longer selected$/,'$1 non più selezionati'],
 [/^(\d+) newly selected$/,'$1 selezionati ora'],
 [/^(\S+) of (\S+) marked wrong are fixed$/,'$1 dei $2 segnati come errati sono corretti'],
 [/^(\d+) marked wrong$/,'$1 segnati come errati'],
 [/^Movements selected by this rule(?: \((\d+)\))?$/,m=>'Movimenti selezionati da questa regola'+(m[1]!=null?` (${m[1]})`:'')],
 [/^General rule \(the WHO opens the description\): it reads only the movements no more specific rule reads(?: — (\S+) more are read by more specific rules and are not listed here)?\.$/,
  m=>'Regola generale (il WHO apre la descrizione): legge solo i movimenti che nessuna regola più specifica legge'+(m[1]!=null?` — altri ${m[1]} sono letti da regole più specifiche e non sono elencati qui`:'')+'.'],
 [/^WHO wrong for movement (\S+)$/,'WHO errato per il movimento $1'],
];

const own=Object.prototype.hasOwnProperty;
function exact(s){return own.call(EXACT,s)?EXACT[s]:null;}

// One whole message (already trimmed): exact key, then anchored patterns. null = not a known UI message.
function message(text){
 if(!text)return null;
 const hit=exact(text);if(hit!=null)return hit;
 for(const [re,rep] of PATTERNS){
  const m=text.match(re);if(!m)continue;
  const t=g=>{if(!g)return g||'';const v=translateLine(g.trim());return v==null?g:v;};
  return typeof rep==='function'?rep(m,t):rep.replace(/\{t(\d)\}|\$(\d)/g,(all,ti,di)=>{const g=m[Number(ti||di)];return ti?t(g):(g==null?'':g);});
 }
 return null;
}

// A trimmed line: whole message, else its " · " segments (each one whole, an optional final "." kept).
function translateLine(text){
 const whole=message(text);if(whole!=null)return whole;
 if(text.indexOf('·')<0)return null;
 const parts=text.split(/(\s*·\s*)/);let changed=false;
 const out=parts.map((part,i)=>{
  if(i%2||!part)return part;
  let v=message(part);
  if(v==null&&part.endsWith('.')){const inner=message(part.slice(0,-1));if(inner!=null)v=inner+'.';}
  if(v==null)return part;changed=true;return v;
 });
 return changed?out.join(''):null;
}

// Any string: keeps surrounding whitespace; multi-line text is translated line by line. null = unchanged.
function translate(value){
 if(typeof value!=='string')return null;
 const m=value.match(/^(\s*)([\s\S]*?)(\s*)$/);if(!m[2])return null;
 let v=translateLine(m[2]);
 if(v==null&&m[2].indexOf('\n')>=0){
  let changed=false;
  v=m[2].split('\n').map(line=>{const lm=line.match(/^(\s*)(.*?)(\s*)$/);const t=lm[2]?translateLine(lm[2]):null;if(t==null)return line;changed=true;return lm[1]+t+lm[3];}).join('\n');
  if(!changed)v=null;
 }
 return v==null?null:m[1]+v+m[3];
}
function t(value){const v=translate(value);return v==null?value:v;}

if(typeof document==='undefined'){ // Node: used by the coverage check, never in the browser.
 if(typeof module!=='undefined')module.exports={EXACT,PATTERNS,translate,t};
 return;
}
const active=document.documentElement.lang==='it';
window.rfT=active?t:(value=>value);
if(!active)return;

const ATTRS=['placeholder','title','aria-label','alt'];
function protectedText(node){
 const parent=node.parentElement;if(!parent)return true;
 if(/^(SCRIPT|STYLE|TEXTAREA)$/.test(parent.nodeName))return true;
 // Stored data (titles, descriptions, catalog names) is marked translate="no" by its renderer.
 if(parent.closest('[translate="no"]'))return true;
 // Conversation messages, rule texts and summaries are user/AI content, never UI labels.
 const chatText=parent.closest('.flow-chat-text');
 return !!chatText&&chatText.id!=='published-definition';
}
function translateTextNode(node){
 if(protectedText(node))return;
 const v=translate(node.nodeValue);if(v!=null&&v!==node.nodeValue)node.nodeValue=v;
}
function translateAttribute(element,name){
 const old=element.getAttribute(name);if(old==null)return;
 const v=translate(old);if(v!=null&&v!==old)element.setAttribute(name,v);
}
function translateTree(root){
 if(root.nodeType===3){translateTextNode(root);return;}
 if(root.nodeType!==1)return;
 const elements=[root,...root.querySelectorAll('['+ATTRS.join('],[')+']')];
 elements.forEach(e=>ATTRS.forEach(a=>{if(e.hasAttribute&&e.hasAttribute(a))translateAttribute(e,a);}));
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
 while((n=walker.nextNode()))translateTextNode(n);
}
const title=translate(document.title);if(title!=null)document.title=title;
translateTree(document.body);
new MutationObserver(records=>{
 for(const r of records){
  if(r.type==='characterData')translateTextNode(r.target);
  else if(r.type==='attributes')translateAttribute(r.target,r.attributeName);
  else r.addedNodes.forEach(translateTree);
 }
}).observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:ATTRS});
// Native dialogs: translate their message the same way (none is used today; kept for safety).
['alert','confirm','prompt'].forEach(name=>{const original=window[name];if(typeof original!=='function')return;window[name]=function(message,...rest){return original.call(window,t(String(message??'')),...rest);};});
})();
