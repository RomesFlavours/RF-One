# RFBank — Specifica funzionale WHO

> **Canonical WHO design / 2026-11-22.** This document records the Product Owner's approved WHO decisions from the RFBank design conversation. It supersedes conflicting WHO recognition behavior described in October-era Bank documents, but does not supersede their historical facts or approve implementation. The WHAT / WHY / export phases remain outside the current implementation scope. Imported from `rfbank/main:docs/RFBANK_WHO_SPEC_DECISIONS_20261122.md` @ `c5b43b7`.

**Versione:** 1.0 — Decisioni approvate fino al 22 novembre 2026  
**Stato:** specifica funzionale approvata nel dialogo; **non** implica implementazione o collaudo del software  
**Ambito:** esclusivamente riconoscimento, anagrafica e gestione dei WHO. Motore WHY, export e contabilità saranno specificati e collaudati separatamente.  
**Base applicativa:** RFBank; nessuna nuova versione parallela.

## 1. Obiettivo e confini
Il motore WHO identifica **con chi** è avvenuta l'operazione. Non determina WHY, WHAT o allocazioni contabili, non modifica l'Entity e non crea direttamente nuovi WHO sulla sola base di un risultato AI.

La Source di conto/carta determina l'Entity in modo vincolante. Import conti/carte rimane separato dall'import arricchitori. Il matching dei documenti esterni avviene nella fase di importazione e ne memorizza gli esiti; il motore WHO legge informazioni già disponibili, senza ripetere il matching.

I giroconti e i pagamenti carte seguono un matching dedicato **prima** del motore WHO. Se manca una contropartita, il movimento rimane in attesa e il matching si riprova all'arrivo di nuovi statement. La mancanza di statement non blocca il motore WHO sugli altri movimenti.

## 2. Tre categorie WHO (D28)
Le categorie sono **mutuamente esclusive**:
1. **Univoco** — Identità WHO riconosciuta; il suo WHY unico verrà trattato dalla fase WHY.
2. **Plurimo** — Identità WHO riconosciuta; il WHY verrà determinato in una fase separata da regole approvate.
3. **Di gruppo** — Si riconosce una identità reale (es. Hillstone), ma il **WHO operativo della transazione** è il gruppo (es. Restaurants). L'identità reale riconosciuta va sempre conservata e collegata alla transazione per ricerca, audit e futuri riconoscimenti.

Un WHO può appartenere a **un solo gruppo** (D27); può anche non appartenere a nessun gruppo. I gruppi sono categorie di controparti economiche (Restaurants, Gas Stations, Hotels, Retail Stores), **non** reparti FOH/BOH. L'appartenenza e le definizioni dei gruppi si amministrano in Bank, non in Registry (D23). FOH/BOH, quando usati per analisi gestionali RF-One, non modificano di per sé il WHY.

Le regole Gruppo + Source → WHY sono state discusse (D26) ma la loro implementazione appartiene alla successiva specifica WHY. Non introdurre assegnazione WHY nel motore WHO.

## 3. Pipeline di riconoscimento WHO (D3, D18, D19, D20)
Per ogni movimento ordinario (o dettaglio economico pertinente, quando il modello aggregato lo richiede):
1. **Testuale:** cerca WHO e alias con normalizzazione e confronto robusto; termini generici come `PAYMENT` non devono diventare una controparte certa solo perché compaiono nel testo.
2. **Regole WHO:** soltanto per record irrisolti o ambigui. Sono regole **testuali semplici**, con Source opzionale. Producono esclusivamente un WHO, mai WHY.
3. **AI:** soltanto per record ancora irrisolti o ambigui. Può assegnare automaticamente un WHO **già esistente** solo quando l'identificazione è affidabile, registrando motivazione, evidenza e provenienza. Non può modificare Entity o WHY.
4. **Riconcilio manuale:** se permane ambiguità o manca un WHO attendibile.

Se il riconoscimento testuale presenta più candidati, **non** usare automaticamente il nome più lungo o il primo match: passa a regole, poi AI e infine al Riconcilio se necessario (D18). Non inferire un WHO certo da un livello di confidence inventato: il criterio misurabile di affidabilità sarà definito nei test.

Il motore WHO salva il riconoscimento anche se WHY è mancante e lo riutilizza alle successive esecuzioni. Una nuova informazione può motivare una rivalutazione, ma una conferma umana non può essere sovrascritta automaticamente (D21).

## 4. Nuovi WHO, WHO di gruppo e alias (D3, D24, D29, D30)
**WHO nuovo ordinario:** l'AI propone identità e dati di riconoscimento; la creazione avviene solo dopo conferma nel Riconcilio (D3).

**WHO di gruppo nuovo:**
- Se identificato e assegnato **manualmente**, la scelta del gruppo è immediatamente valida.
- Se proposto dall'**AI**, l'identità e il gruppo vengono registrati come **DA CONFERMARE**: nessuna classificazione definitiva prima della conferma umana (D29).
- Dopo conferma, il nome reale rimane nella rubrica come membro del gruppo e può essere riconosciuto in futuro; sulla transazione si conserva la coppia **identità riconosciuta + WHO operativo di gruppo** (D28).
- Per WHO **già esistenti**, Bank può assegnare automaticamente un gruppo se l'identificazione dell'appartenenza è certa (D24), con audit e senza cancellare verifiche precedenti. Questo non autorizza la creazione autonoma di nuovi WHO da parte dell'AI.

**Alias:** varianti certe sono aggiunte automaticamente al WHO esistente, con provenienza e verifica di assenza di collisioni; varianti dubbie richiedono conferma (D30). Un alias non deve risolvere automaticamente a due identità distinte.

## 5. Gruppi e correzioni (D23, D25, D27, D31)
- Ogni WHO appartiene a zero o **un solo** gruppo; tutti i gruppi sono gestiti in Bank.
- L'appartenenza è una **configurazione corrente**, senza una tabella di storicizzazione della membership come requisito autonomo (D25).
- Le modifiche a WHO, gruppo e alias possono riflettersi sui movimenti preesistenti, anche passati, ma occorrono **simulazione, approvazione e tracciabilità**. Decisioni umane protette non vengono sovrascritte in automatico.
- Le correzioni su movimenti di periodi **chiusi** o **già esportati** devono produrre voci di Tabella Modifiche, con stato prima/dopo e riferimento all'export originario (D31–D32). I dettagli di WHAT, QBO/CSV e del Bookkeeper sono **fuori ambito** della fase WHO: qui si richiede soltanto di emettere eventi/audit sufficienti, senza implementare export.
- Non modificare silenziosamente classificazioni storiche in caso di cambio gruppo.

## 6. Esecuzione e stato (D6, D7, D14, D21)
- La riconciliazione automatica si avvia **manualmente** dopo i caricamenti, non parte ad ogni importazione (D14).
- Il WHO risolto può essere persistito e riutilizzato indipendentemente dal WHY (D21).
- Un movimento senza WHO certo resta aperto o con proposta da verificare; non si crea un WHO artificiale.
- I risultati automatici possono essere rivalutati con audit. Le conferme umane restano protette e ogni modifica richiede procedura autorizzata.
- In questa fase **non** si definisce come WHO/WHY producano uno stato contabile finale: sarà oggetto del ciclo di test e della fase WHY.

## 7. Interfaccia WHO / Riconcilio: comportamento minimo
- Selezione rapida dei tre tipi WHO: univoco, plurimo, di gruppo.
- Distinzione visiva tra identità riconosciuta e WHO operativo (gruppo).
- Proposte AI di nuovi WHO/gruppi marcate **Da confermare**, con approvazione o correzione manuale.
- Gestione degli alias certi e dubbi, con controllo collisioni.
- In caso di WHO sconosciuto, l'utente può creare/associare manualmente l'identità senza fare dipendere la registrazione del WHO dalla disponibilità del WHY.
- Tracciabilità di riconoscimento testuale / regola / AI / utente e relativo motivo.

## 8. Prova e criteri di accettazione (prima di WHY)
Sulla medesima baseline di movimenti, confrontare:
- WHO riconosciuti da testo, da regole e da AI;
- ambigui risolti e irrisolti;
- WHO nuovi proposti e confermati;
- collisioni alias e falsi positivi (in particolare token generici);
- membri di gruppo riconosciuti con **identità reale preservata** e **WHO operativo corretto**;
- WHO parziali salvati e riutilizzati al secondo giro;
- nessuna variazione di Entity, WHY, decisioni umane protette o movimenti bancari;
- idempotenza a seconda esecuzione e audit di ogni modifica.

Solo dopo simulazione e revisione Codex si decide se modificare il modello WHO. **Nessun lavoro sul WHY o export prima di chiudere questo collaudo.**

## 9. Decisioni correlate rinviate
Sono state discusse decisioni su WHY, ADP/Amazon, rettifiche ed export (D4–D17 e D31–D35), ma **non costituiscono mandato di sviluppo in questa fase**. La domanda WHAT/export è stata espressamente sospesa. Le eventuali precedenze generiche delle regole WHY (D16) dovranno essere riallineate, in fase WHY, alla successiva scelta esplicita sulle categorie WHO e sui gruppi (D26–D28).

## 10. Sequenza di lavoro
1. Documentazione WHO approvata.
2. Implementazione Claude nella base RFBank, senza duplicare il motore.
3. Verifica tecnica indipendente Codex.
4. Simulazione sui movimenti reali in copia isolata.
5. Revisione dei risultati e, se necessario, correzioni del modello.
6. Solo allora progettazione WHY.

**Stato:** documento di decisioni funzionali, non dichiarazione di codice implementato.
