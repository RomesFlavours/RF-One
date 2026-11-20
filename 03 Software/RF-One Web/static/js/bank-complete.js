// "Completa" (BANK_COMPLETE_MODAL_001, Product Owner, 2026-11-06) — ONE window to complete the movements still open.
// window.BankComplete.open(transactionId, {queue:[ids], onWritten(rows), onClose(changed, lastId)}).
// The person reasons on the movement; the server (bank_complete.py) reuses the engine and the existing services.
// Shown: the movement, what Bank recognised, what is missing, the proposal (never presented as approved). The person
// confirms, corrects (also in natural language, ChatGPT on request), goes to the next case or closes.
// Reuse: "only this movement" by default; a criterion that may apply to other movements is previewed first
// (before / after), then two explicit questions: apply to those movements, save the criterion for future ones.
// A rule that depends on each movement opens the existing WHO WHY rule editor. Local Italian, shared English.
(()=>{
const dlg=document.getElementById('bc-dialog');if(!dlg)return;
const $=id=>document.getElementById(id);
const IT=dlg.dataset.lang==='it';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>((v||0)/100).toLocaleString(IT?'it-IT':'en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const csrf=()=>(document.querySelector('meta[name="bank-csrf"]')||{}).content||'';
const S={
 title:['Complete','Completa'],close:['Close','Chiudi'],next:['Next case','Caso successivo'],confirm:['Confirm','Conferma'],
 confirmNext:['Confirm and go to the next','Conferma e passa al successivo'],help:['How Complete works','Come funziona Completa'],
 x:['Close','Chiudi'],loading:['Reading the movement (reconciliation engine, read-only)…','Lettura del movimento (motore di riconciliazione, sola lettura)…'],
 pos:['Case {0} of {1}','Caso {0} di {1}'],movement:['Movement','Movimento'],date:['Date','Data'],amount:['Amount','Importo'],
 description:['Description','Descrizione'],account:['Account or card','Conto o carta'],owner:['Owner at the date','Titolare alla data'],
 personal:['personal','personale'],company:['company','aziendale'],unknownOwner:['not configured','non configurato'],
 recognised:['What Bank has already recognised','Cosa Bank ha già riconosciuto'],nothing:['Nothing yet.','Ancora nulla.'],
 missing:['Why it is still open','Perché è rimasto fuori'],onlyConfirm:['Bank classified it by itself: only your confirmation is missing.','Bank l’ha classificato da sola: manca solo la tua conferma.'],history:['What was done','Cosa è stato fatto'],proposal:['Proposal','Proposta'],noProposal:['No proposal: choose the classification or ask the AI.','Nessuna proposta: scegli la classificazione o chiedi all’AI.'],
 yours:['Your classification','La tua classificazione'],who:['WHO','WHO'],why:['WHY','WHY'],what:['WHAT (from the WHY)','WHAT (dal WHY)'],
 whoPh:['Search or write the WHO','Cerca o scrivi il WHO'],newWho:['New WHO: it is created when you confirm.','Nuovo WHO: viene creato alla conferma.'],
 existingWho:['Existing WHO.','WHO già presente.'],choose:['— choose —','— scegli —'],
 askAi:['Ask the AI','Chiedi all’AI'],correct:['Correct or explain what you want','Correggi o spiega cosa desideri'],
 correctPh:['E.g. “it is a staff meal, on personal cards it is personal”','Es. «è un pasto del personale; sulle carte personali è personale»'],
 interpret:['Send to the AI','Invia all’AI'],aiWorking:['The AI is working (ChatGPT)… nothing is saved.','L’AI sta elaborando (ChatGPT)… nulla viene salvato.'],
 aiOff:['The AI is not authorised on this PC (Bank context sharing with ChatGPT): choose yourself.','L’AI non è autorizzata su questo PC (condivisione del contesto Bank con ChatGPT): scegli tu.'],
 question:['Question','Domanda'],sources:['Sources','Fonti'],
 scope:['Does it apply to other movements too?','Vale anche per altri movimenti?'],only:['Only this movement (no general rule is created)','Solo questo movimento (non viene creata una regola generale)'],
 single:['Every movement of {0}: one WHY on every account and card','Tutti i movimenti di {0}: un solo WHY su ogni conto e carta'],
 bySubject:['Movements of {0} by owner: a personal WHY and a company WHY','Movimenti di {0} per titolare: un WHY personale e un WHY aziendale'],
 personalWhy:['Personal WHY','WHY personale'],companyWhy:['Company WHY','WHY aziendale'],thisSide:['(this movement)','(questo movimento)'],
 excKept:['The company exceptions of this WHO are kept.','Le eccezioni per azienda di questo WHO restano invariate.'],
 excThis:['The owner {0} has its own exception for this WHO: the criterion updates that exception.','Il titolare {0} ha una propria eccezione per questo WHO: il criterio aggiorna quell’eccezione.'],
 text:['Recognise {0} in the next movements by the text','Riconosci {0} nei prossimi movimenti con il testo'],
 textCfg:['{0} has no WHO → WHY configuration: saving the criterion also sets the WHY chosen here for its movements with a {1} owner.','{0} non ha una configurazione WHO → WHY: salvando il criterio si imposta anche il WHY scelto qui per i suoi movimenti con titolare {1}.'],
 preview:['Show the movements that would change','Mostra i movimenti che cambierebbero'],previewing:['Preview in progress (engine evaluation, read-only; it can take ~20 s)…','Anteprima in corso (valutazione del motore, sola lettura; può richiedere ~20 s)…'],
 previewFirst:['Show the movements that would change before confirming.','Mostra i movimenti che cambierebbero prima di confermare.'],
 changes:['{0} other movement(s) would change','{0} altri movimenti cambierebbero'],noChanges:['No other movement would change.','Nessun altro movimento cambierebbe.'],
 summary:['Unchanged: {0} · still open: {1} · decided by a person, protected: {2}','Invariati: {0} · ancora aperti: {1} · decisi da una persona, protetti: {2}'],
 before:['Before','Prima'],after:['After','Dopo'],
 applyOthers:['Apply it also to these {0} movements (each becomes your decision)','Applicalo anche a questi {0} movimenti (ognuno diventa una tua decisione)'],
 saveCriterion:['Save the criterion for future movements','Salva il criterio per i movimenti futuri'],
 saveCfgNote:['Saving the criterion writes the WHO → WHY configuration of {0}: the engine uses it on the next movements and they stay proposals until confirmed. Movements decided by a person stay protected.','Salvare il criterio scrive la configurazione WHO → WHY di {0}: il motore la usa sui prossimi movimenti, che restano proposte fino alla conferma. I movimenti decisi da una persona restano protetti.'],
 saveTextNote:['Saving the criterion adds the text as an alias of the WHO: it recognises the next movements; nothing else is decided.','Salvare il criterio aggiunge il testo come alias del WHO: riconosce i prossimi movimenti; nient’altro viene deciso.'],
 neither:['Without these two choices only this movement is completed.','Senza queste due scelte viene completato solo questo movimento.'],
 rule:['The WHY of {0} depends on each movement: a reusable criterion needs a WHO WHY rule (simulated before it is saved).','Il WHY di {0} dipende dal singolo movimento: un criterio riutilizzabile richiede una regola WHO WHY (simulata prima del salvataggio).'],
 defineRule:['Define the rule','Definisci la regola'],ruleOnly:['Confirming here completes only this movement; the rule, once saved and active, applies to the next ones.','La conferma qui completa solo questo movimento; la regola, una volta salvata e attivata, vale per i successivi.'],ruleSaved:['Rule saved: the case is evaluated again.','Regola salvata: il caso viene rivalutato.'],
 info:['Information needed','Informazioni necessarie'],open:['Open','Apri'],
 infoNote:['Bank cannot complete this movement here without this information: nothing is forced.','Senza questa informazione Bank non può completare qui il movimento: nessuna classificazione viene forzata.'],
 done:['This movement is already resolved.','Questo movimento è già risolto.'],excluded:['Copy excluded from accounting: classify the canonical movement.','Copia esclusa dalla contabilità: classifica il movimento canonico.'],
 confirmQ:['Record this classification?','Registrare questa classificazione?'],
 saved:['Recorded: {0} → {1} ({2}).','Registrato: {0} → {1} ({2}).'],savedOthers:['Also recorded on {0} other movement(s).','Registrato anche su {0} altri movimenti.'],
 skipped:['Not changed (decided by a person in the meantime or incomplete): {0}.','Non modificati (decisi da una persona nel frattempo o incompleti): {0}.'],
 critCfg:['Criterion saved in the WHO → WHY configuration.','Criterio salvato nella configurazione WHO → WHY.'],critText:['Text saved to recognise the WHO.','Testo salvato per riconoscere il WHO.'],
 end:['No other open case in this list. You can close the window.','Nessun altro caso aperto in questo elenco. Puoi chiudere la finestra.'],
 chooseWhy:['Choose the WHY.','Scegli il WHY.'],chooseWho:['Choose or write the WHO.','Scegli o scrivi il WHO.'],
 ops:['To settle in this window','Da sistemare in questa finestra'],dup:['Possible duplicate of movement #{0}: same account, date, description and amount.','Possibile duplicato del movimento #{0}: stesso conto, data, descrizione e importo.'],distinct:['Distinct movements','Movimenti distinti'],isDup:['It is a duplicate','È un duplicato'],matchAmb:['Card payment with more than one possible counterpart: choose the right one.','Pagamento carta con più controparti possibili: scegli quella giusta.'],matchWait:['Card payment without its credit on the card. If the counterpart is listed, pair it; otherwise upload the missing card statement.','Pagamento carta senza l’accredito sulla carta. Se la controparte è in elenco abbinala; altrimenti carica l’estratto della carta mancante.'],matchMaybe:['Possible transfer between accounts or card payment: if it is, pair it with its counterpart.','Possibile giroconto o pagamento carta: se lo è, abbinalo alla sua controparte.'],noCand:['No counterpart among the uploaded movements.','Nessuna controparte tra i movimenti caricati.'],pair:['Confirm the pairing','Conferma l’abbinamento'],noCurrency:['To pair, the account or card needs its currency:','Per abbinare, il conto o la carta deve avere la valuta:'],setCurrency:['set it','impostala'],whomNeed:['WHOM (who the movement is for) is not set.','WHOM (per chi è il movimento) non è impostato.'],saveWhom:['Save WHOM','Salva WHOM'],opDone:['Saved. The case has been read again.','Salvato. Il caso è stato riletto.'],protectedNote:['A person already decided part of this movement: that decision stays protected.','Una persona ha già deciso parte di questo movimento: quella decisione resta protetta.'],
};
const O={RESEARCH:['Internet research (ChatGPT) of the last reconciliation — to verify','Ricerca internet (ChatGPT) dell’ultima riconciliazione — da verificare'],
 ENGINE:['Bank proposal','Proposta di Bank'],HISTORY:['WHY already confirmed {0} time(s) for this WHO with a {1} owner','WHY già confermato {0} volte per questo WHO con titolare {1}'],
 PAIRS:['From the former WHY per account or card of this WHO','Dal precedente WHY per conto o carta di questo WHO'],AI:['AI proposal (ChatGPT) — to verify','Proposta AI (ChatGPT) — da verificare']};
const WM={'RULE':['WHO rule','regola WHO'],'NAME/ALIAS':['name or alias in the description','nome o alias nella descrizione'],'HUMAN BANK':['decision of a person','decisione di una persona'],
 'CONTEXT':['transfer / card payment','giroconto / pagamento carta'],'WHO SINGLE WHY':['single WHY of the WHO','WHY unico del WHO'],'WHO PERSONAL WHY':['personal WHY of the WHO','WHY personale del WHO'],
 'WHO COMPANY WHY':['company WHY of the WHO','WHY aziendale del WHO'],'WHO EXCEPTION':['company exception of the WHO','eccezione per azienda del WHO'],
 'WHO + SOURCE':['WHY of the WHO for this account or card','WHY del WHO per questo conto o carta'],'WHO WHY RULE':['WHO WHY rule','regola WHO WHY']};
const C={WHO_UNKNOWN:['WHO not recognised: no rule, name or alias identifies it.','WHO non riconosciuto: nessuna regola, nome o alias lo identifica.'],
 WHO_AMBIGUOUS:['Ambiguous WHO: more than one WHO is possible.','WHO ambiguo: più WHO sono possibili.'],
 WHO_SOURCE_CLASSIFICATION_MISSING:['The WHY of this WHO is not configured.','Il WHY di questo WHO non è configurato.'],
 WHY_RULE_MISSING:['The WHY depends on the movement and no active rule determines it.','Il WHY dipende dal movimento e nessuna regola attiva lo determina.'],
 WHY_DOCUMENT_MISSING:['A document or a clarification is needed.','Serve un documento o un chiarimento.'],
 WHY_RULES_CONFLICT:['Rules in conflict: they give different WHYs.','Regole in conflitto: indicano WHY diversi.'],
 WHY_SPLIT_INCOMPLETE:['Split incomplete.','Ripartizione incompleta.'],
 HUMAN_INCOMPLETE:['WHO chosen by a person, WHY missing.','WHO scelto da una persona, WHY mancante.'],
 PROVISIONAL_WHY:['Provisional WHY: the nature of the movement is still to be established.','WHY provvisorio: la natura del movimento è ancora da stabilire.'],
 PERSONAL_SOURCE_BUSINESS_WHAT:['Personal account or card with a business WHY: a personal WHY or a decision is needed.','Conto o carta personale con un WHY aziendale: serve un WHY personale o una decisione.'],
 DIRECTION_CONFLICT:['The WHY is an income but the movement is money out: verify it.','Il WHY è un’entrata ma il movimento è un’uscita: verificalo.'],
 CATEGORY_MISSING:['The WHY has no WHAT in the catalog (Configurazioni › WHY).','Il WHY non ha un WHAT nel catalogo (Configurazioni › WHY).'],
 SOURCE_OWNER_MISSING:['The account or card has no owner configured at the date.','Il conto o la carta non ha un titolare configurato alla data.'],
 CARD_PAYMENT_UNMATCHED:['Card payment without its credit on the card: upload the missing card statement.','Pagamento carta senza l’accredito sulla carta: carica l’estratto della carta mancante.'],
 CARD_PAYMENT_AMBIGUOUS:['Card payment with more than one possible counterpart: choose the right one below.','Pagamento carta con più controparti possibili: scegli qui sotto quella giusta.'],
 RELATIONSHIP_TO_DECIDE:['Economic relationship between owners to decide (draw, advance or repayment).','Rapporto economico tra titolari da decidere (prelievo, anticipo o restituzione).'],
 INCOMPLETE:['Incomplete data.','Dati incompleti.']};
// «Cosa è stato fatto» (Product Owner, 2026-11-18): the steps of the reconciliation on this movement, in plain words.
const H={SOURCE:['Account or card {0}: owner {1}.','Conto o carta {0}: titolare {1}.'],
 SOURCE_MISSING:['Account or card {0}: no owner configured at the date.','Conto o carta {0}: nessun titolare configurato alla data.'],
 MATCH_MATCHED:['Paired with movement #{0} as {1}: WHO and WHY come from the pairing.','Abbinato al movimento #{0} come {1}: WHO e WHY derivano dall’abbinamento.'],
 MATCH_AMBIGUOUS:['Looks like {0}, but more than one counterpart is possible.','Sembra {0}, ma le controparti possibili sono più di una.'],
 MATCH_WAITING:['Looks like {0}, but its counterpart is not among the uploaded movements.','Sembra {0}, ma la controparte non è tra i movimenti caricati.'],
 MATCH_OTHER:['Possible {0}.','Possibile {0}.'],
 BANK_NARRATIVE:['Bank operation recognised by its narrative «{0}»{1}.','Operazione della banca riconosciuta dalla causale «{0}»{1}.'],
 WHO_HUMAN:['WHO {0}: chosen by a person (protected).','WHO {0}: scelto da una persona (protetto).'],
 WHO_WEB_RESTAURANT:['WHO {0}: a public source identifies the merchant as a restaurant.','WHO {0}: una fonte pubblica identifica l’esercente come ristorante.'],
 VIA:['The payment passed through the intermediary {0}: the intermediary is never the WHO.','Il pagamento è passato dall’intermediario {0}: l’intermediario non è mai il WHO.'],
 VIA_RULE:['The rule {1} named only the intermediary {0}: the result is discarded, because the intermediary is never the WHO.','La regola {1} ha indicato solo l’intermediario {0}: il risultato è scartato, perché l’intermediario non è mai il WHO.'],
 WHO_HELD:['The name {0} was read, but it is not registered: {1}.','È stato letto il nome {0}, ma non viene registrato: {1}.'],
 WHO_RULE:['The rule {1} recognised it as {0}.','La regola {1} l’ha riconosciuto come {0}.'],
 WHO_RULE_NEW:['The rule {1} read the name {0}: it is a new WHO to confirm.','La regola {1} ha letto il nome {0}: è un nuovo WHO da confermare.'],
 WHO_TEXT:['The name or an alias of {0} is in the description.','Nella descrizione c’è il nome o un alias di {0}.'],
 WHO_OTHER:['WHO {0} ({1}).','WHO {0} ({1}).'],
 WHO_RULES_DISAGREE:['The rules give different WHO: {0}. Rules involved: {1}.','Le regole danno WHO diversi: {0}. Regole coinvolte: {1}.'],
 WHO_TEXT_AMBIGUOUS:['The description contains more than one registered WHO: {0}.','La descrizione contiene più WHO registrati: {0}.'],
 WHO_TEXT_AMBIGUOUS_RULE:['The name {0} was read{1}, but {2}.','È stato letto il nome {0}{1}, ma {2}.'],
 WHO_NONE:['No rule and no WHO name or alias recognises the counterparty.','Nessuna regola e nessun nome o alias di WHO riconosce la controparte.'],
 WHO_NONE_VIA:['Apart from the intermediary, no registered WHO is in the description.','Oltre all’intermediario, nella descrizione non c’è alcun WHO registrato.'],
 RESEARCH_WHO_IDENTIFIED:['Internet research: it indicates {0}{1}.','Ricerca internet: indica {0}{1}.'],
 RESEARCH_GENERIC_WHO:['Internet research: the exact counterparty is unknown, the nature is {0}{1}.','Ricerca internet: la controparte esatta non è nota, la natura è {0}{1}.'],
 RESEARCH_UNRESOLVED:['Internet research: the sources found do not establish it.','Ricerca internet: le fonti trovate non bastano a stabilirlo.'],
 RESEARCH_KEPT_FOR_PERSON:['Internet research: not run, the case needs a person.','Ricerca internet: non eseguita, il caso richiede una persona.'],
 RESEARCH_PROVIDER_ERROR:['Internet research: the service did not answer.','Ricerca internet: il servizio non ha risposto.'],
 RESEARCH_NOT_AUTHORIZED:['Internet research: not authorised on this PC.','Ricerca internet: non autorizzata su questo PC.'],
 WHY_HUMAN:['WHY {0}: decided by a person (protected).','WHY {0}: deciso da una persona (protetto).'],
 WHY_CONFIG:['WHY {0}: {1}.','WHY {0}: {1}.'],
 WHY_RULE:['WHY {0}: given by the rule {1}.','WHY {0}: dato dalla regola {1}.'],
 WHY_RESTAURANT:['WHY {0}: restaurant, from the owner of the card at the date.','WHY {0}: ristorante, secondo il titolare della carta alla data.'],
 WHY_OTHER:['WHY {0} ({1}).','WHY {0} ({1}).'],
 WHY_OPEN_UNIQUE:['WHO with one WHY, but its WHY is not set.','WHO con un solo WHY, ma il suo WHY non è impostato.'],
 WHY_OPEN_MULTIPLE_NONE:['WHO with more WHY: it has no active WHO WHY rule.','WHO con più WHY: non ha alcuna regola WHO WHY attiva.'],
 WHY_OPEN_RULES:['WHY rules checked on this movement: {0}.','Regole WHY provate su questo movimento: {0}.'],
 WHY_OPEN_CONFLICT:['The rules give different WHY: {0}.','Le regole danno WHY diversi: {0}.'],
 SPLIT:['Split into {0} lines by its document.','Ripartito in {0} righe dal suo documento.'],
 WHAT:['WHAT {0}, from the WHY.','WHAT {0}, dal WHY.'],
 WHOM:['WHOM {0}, owner of the account or card.','WHOM {0}, titolare del conto o carta.'],
 WHOM_EXC:['WHOM {0}, from the company exception of the WHO.','WHOM {0}, dall’eccezione per azienda del WHO.'],
 PAIR_WHY_NOT_USED_FOR_MULTIPLE_WHO:['Note: a WHY registered for this account is not used, because the WHO has more WHY.','Nota: un WHY registrato per questo conto non è usato, perché il WHO ha più WHY.'],
 WHAT_NOT_FROM_WHY:['Note: a different WHAT was proposed; the WHAT of the WHY is used.','Nota: era proposto un WHAT diverso; si usa il WHAT del WHY.'],
 SPLIT_MIXED_OPERATION:['Note: the split lines are of different kinds of operation.','Nota: le righe della ripartizione sono di tipi di operazione diversi.'],
 PROMISCUOUS_USE:['Note: possible mixed personal/business use.','Nota: possibile uso promiscuo personale/aziendale.'],
 MANAGEMENT_DESTINATION:['Note: the movement is for another entity than the one that paid; any recharge is decided later.','Nota: il movimento è per un’entità diversa da quella che ha pagato; l’eventuale riaddebito si decide dopo.'],
 ANOMALY:['Note: {0}','Nota: {0}']};
const MK={CARD_SETTLEMENT:['card payment','pagamento carta'],TRANSFER:['transfer between accounts','giroconto']};
const RO={CONFLICT:['in conflict','in conflitto'],MATCH:['applies','si applica'],NO_MATCH:['does not apply','non si applica'],INCOMPLETE:['information missing','mancano informazioni'],SPLIT:['split','ripartizione']};
const CM={'WHO SINGLE WHY':['the one WHY of the WHO','il WHY unico del WHO'],'WHO PERSONAL WHY':['personal WHY of the WHO (personal owner)','WHY personale del WHO (titolare personale)'],
 'WHO COMPANY WHY':['company WHY of the WHO (company owner)','WHY aziendale del WHO (titolare aziendale)'],'WHO EXCEPTION':['company exception of the WHO','eccezione per azienda del WHO'],
 'WHO + SOURCE':['WHY of the WHO for this account or card','WHY del WHO per questo conto o carta']};
// the notes of the WHO-name checks (engine texts) in the page language
const NOTE=[[/^Extracted WHO resembles a saved name or alias: (.*)$/,['it resembles a saved name or alias: $1','somiglia a un nome o alias già salvato: $1']],
 [/^the name matches INACTIVE WHO #\d+ '([^']+)'.*$/,['it is the name of the deactivated WHO «$1», which is neither recreated nor reactivated','è il nome del WHO disattivato «$1», che non viene ricreato né riattivato']],
 [/^The extracted WHO is not a valid catalog name\.?$/,['it is not a valid name for the catalog','non è un nome valido per il catalogo']],
 [/^Several new names from this run are similar: (.*)$/,['several new names of this reconciliation are similar: $1','più nomi nuovi di questa riconciliazione sono simili: $1']]];
const noteText=t=>{for(const [re,v] of NOTE){if(re.test(t||''))return (t||'').replace(re,v[IT?1:0]);}return t||'';};
// A new WHO read by a rule (Product Owner, 2026-11-18): confirmed here with the same buttons and the same service
// as «Nuovi WHO» on the WHO page (/bank/who-search-text/discovered/*), then the movement is read again.
function newWhoHtml(name){
 const n=esc(name);
 return `<div class="bc-row bc-newwho" data-nw-name="${n}"><button type="button" class="btn-secondary" data-nw="single">${IT?'Singolo':'Single'}</button><button type="button" class="btn-secondary" data-nw="multiple">${IT?'Più WHY':'More WHY'}</button><button type="button" class="btn-secondary" data-nw="intermediary">${IT?'Intermediario':'Intermediary'}</button><button type="button" class="btn-secondary" data-nw="alias">${IT?'È alias di…':'Alias of…'}</button></div>`;
}
async function newWho(b){
 const box=b.closest('[data-nw-name]'),name=box.dataset.nwName,kind=b.dataset.nw;err('');
 if(kind==='alias'){
  if(!whos){try{whos=(await getJSON('/bank/complete/whos')).whos;}catch(e){whos=[];}}
  box.innerHTML=`<label>${IT?'WHO esistente di cui è alias':'Existing WHO it is an alias of'}<input id="bc-nw-of" list="bc-nw-list" autocomplete="off" translate="no"><datalist id="bc-nw-list">${whos.map(w=>`<option value="${esc(w.name)}">`).join('')}</datalist></label><button type="button" class="btn-secondary" data-nw="alias-save">${IT?'Salva alias':'Save alias'}</button><button type="button" class="btn-secondary" data-nw="cancel">${IT?'Annulla':'Cancel'}</button>`;
  $('bc-nw-of').focus();return;}
 if(kind==='cancel'){render();return;}
 const pairs=[['name',name],['transaction_id',K.id]];let url='/bank/who-search-text/discovered/create';
 if(kind==='alias-save'){const v=(($('bc-nw-of')||{}).value||'').trim().toUpperCase();const w=(whos||[]).find(x=>x.name.toUpperCase()===v);
  if(!w){err(IT?'Scegli un WHO esistente dall’elenco.':'Choose an existing WHO from the list.');return;}
  url='/bank/who-search-text/discovered/alias';pairs.push(['who_id',w.id]);}
 else pairs.push(['kind',kind]);
 b.disabled=true;
 try{await postForm(url,pairs);changed=true;whos=null;await load(K.id);flash(IT?'WHO registrato: il movimento è stato riletto.':'WHO registered: the movement has been read again.');}
 catch(e){err(e.message);b.disabled=false;}
}
dlg.addEventListener('click',e=>{const b=e.target.closest('[data-nw]');if(b&&K)newWho(b);});
// Verifica (Product Owner, 2026-11-18): the movements the rule reads, from the existing rules check (the engine's own
// executor, read-only), with the other rules on the same movement and the human decision.
async function ruleCheck(b){
 const id=+b.dataset.ruleCheck,box=$('bc-rule-check-'+id);if(!box)return;
 if(box.dataset.loaded){box.hidden=!box.hidden;return;}
 b.disabled=true;box.innerHTML=`<p class="bc-note">${IT?'Lettura di tutti i movimenti con questa regola (sola lettura; la prima volta può richiedere qualche decina di secondi)…':'Reading every movement with this rule (read-only; the first time it can take some tens of seconds)…'}</p>`;
 try{const v=await getJSON('/bank/ai-rules/check/rules/'+id);box.dataset.loaded=1;
  const other=r=>(r.others||[]).filter(o=>o.who&&r.who&&o.who.toUpperCase()!==r.who.toUpperCase());
  const rows=(v.rows||[]).slice().sort((x,y)=>(other(y).length>0)-(other(x).length>0));   // the movements in conflict first
  const conflicts=rows.filter(r=>other(r).length).length;
  const differs=rows.filter(r=>(r.who&&r.human_who&&r.who.toUpperCase()!==r.human_who.toUpperCase())||(r.why&&r.human_why&&r.why!==r.human_why)).length;
  box.innerHTML=`<p class="bc-note">${IT?`Legge ${rows.length} movimenti · su ${conflicts} un’altra regola dà un WHO diverso · su ${differs} il risultato è diverso dalla decisione di una persona.`:`It reads ${rows.length} movements · on ${conflicts} another rule gives a different WHO · on ${differs} the result differs from a person's decision.`}</p>`+
   (rows.length?`<div class="bc-scroll"><table class="bc-table"><thead><tr><th>${IT?'Data':'Date'}</th><th>${IT?'Descrizione':'Description'}</th><th>${IT?'Importo':'Amount'}</th><th>${IT?'Questa regola':'This rule'}</th><th>${IT?'Altre regole':'Other rules'}</th><th>${IT?'Decisione di una persona':'Person’s decision'}</th></tr></thead><tbody>${rows.map(r=>{const o=other(r);const mine=(K&&r.description===K.movement.description&&r.date===K.movement.date);
    return `<tr${o.length||mine?` style="${mine?'font-weight:600;':''}${o.length?'background:var(--warn-bg,#fdf3dd)':''}"`:''}><td>${esc(r.date)}</td><td translate="no">${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td translate="no">${esc(r.who||'—')}${r.why?' · '+esc(r.why):''}</td><td translate="no">${(r.others||[]).map(x=>`<div><small>#${x.rule} ${esc(x.title||'')}</small>: ${esc(x.who||'—')}${x.why?' · '+esc(x.why):''}</div>`).join('')||'—'}</td><td translate="no">${esc([r.human_who,r.human_why||r.human_what].filter(Boolean).join(' · ')||'—')}</td></tr>`;}).join('')}</tbody></table></div>`:'');}
 catch(e){box.innerHTML=`<p class="bc-error">${esc(e.message)}</p>`;}
 finally{b.disabled=false;}
}
// Modifica: the rule's own editor, opened over this window; when it closes the case is read again if the rule was
// saved, the window stays where it was. A text rule, which recognises the WHO from the description itself, opens the
// AI Rule editor of the AI Rules page (window.BankAIRuleEditor, compact: Simula, Salva, Applica), included in this
// dialog by _bank_complete_modal.html. A WHO extractor/profile opens the Regole editor ("Discuss": conversation,
// preview, new version) — the AI Rule editor would not read it, the Regole editor would turn a text rule into a
// profile that no longer recognises the WHO.
function ruleEdit(id,editor){
 if(editor==='text'){
  window.BankAIRuleEditor.openRule(id,{onClose:async saved=>{
   if(saved&&K){changed=true;await load(K.id);flash(IT?'Regola salvata: il caso è stato riletto.':'Rule saved: the case has been read again.');}}});
  return;}
 let d=$('bc-rule-dialog');
 if(!d){d=document.createElement('dialog');d.id='bc-rule-dialog';d.className='bc-dialog bc-rule-dialog';d.setAttribute('aria-label',IT?'Modifica la regola':'Edit the rule');
  d.innerHTML=`<div class="bc-head"><h2>${IT?'Modifica la regola':'Edit the rule'}</h2><span class="bc-head-actions"><button type="button" class="bc-x" id="bc-rule-x" aria-label="${IT?'Chiudi':'Close'}">&times;</button></span></div><iframe id="bc-rule-frame" title="${IT?'Editor della regola':'Rule editor'}"></iframe>`;
  document.body.appendChild(d);$('bc-rule-x').onclick=()=>ruleDone(false);d.addEventListener('cancel',e=>{e.preventDefault();ruleDone(false);});}
 $('bc-rule-frame').src='/bank/rules?'+new URLSearchParams({rule_id:id,embed:'1'});d.showModal();
}
let ruleSaved=false;
async function ruleDone(saved){const d=$('bc-rule-dialog');if(!d||!d.open)return;ruleSaved=ruleSaved||saved;d.close();$('bc-rule-frame').src='about:blank';
 if(ruleSaved&&K){ruleSaved=false;changed=true;await load(K.id);flash(IT?'Regola salvata: il caso è stato riletto.':'Rule saved: the case has been read again.');}}
window.addEventListener('message',e=>{if(e.origin!==location.origin||!e.data||!$('bc-rule-dialog')||!$('bc-rule-dialog').open)return;
 if(e.data.type==='bank-profile-saved')ruleSaved=true;
 if(e.data.type==='bank-profile-closed')ruleDone(false);});
dlg.addEventListener('click',e=>{const c=e.target.closest('[data-rule-check]');if(c){ruleCheck(c);return;}const ed=e.target.closest('[data-rule-edit]');if(ed)ruleEdit(+ed.dataset.ruleEdit,ed.dataset.ruleEditor);});
function historyHtml(hist){
 if(!hist||!hist.steps||!hist.steps.length)return '';
 const tx=(k,...a)=>{const v=(H[k]||[k,k])[IT?1:0];return v.replace(/\{(\d)\}/g,(_,i)=>a[+i]??'');};
 const b=v=>`<strong translate="no">${esc(v||'—')}</strong>`;
 let used=[];
 const rule=id=>{const r=(hist.rules||{})[id];if(!r)return `<span translate="no">#${id}</span>`;
  if(!used.includes(id))used.push(id);
  return `<span class="bc-rule-name" translate="no">«${esc(r.name)}» <small>#${r.id}</small></span>`;};
 // every rule named in a step: its text and the two actions — Verifica (movements it reads) and Modifica
 const ruleBlock=id=>{const r=(hist.rules||{})[id];if(!r)return '';
  const state=r.deleted?(IT?'eliminata':'deleted'):r.status==='ACTIVE'?(IT?'attiva':'active'):(IT?'disattivata':'inactive');
  return `<details class="bc-rule" data-rule-id="${r.id}"><summary><span translate="no">«${esc(r.name)}»</span> <small>#${r.id}</small></summary><div class="bc-rule-text flow-chat-text">${esc(r.text||'—')}</div><small>${IT?'Versione':'Version'} ${esc(r.version??'—')} · ${state}</small>
   <div class="bc-row"><button type="button" class="btn-secondary" data-rule-check="${r.id}">${IT?'Verifica: movimenti che legge':'Check: movements it reads'}</button>${r.deleted?'':`<button type="button" class="btn-secondary" data-rule-edit="${r.id}" data-rule-editor="${r.editor==='text'?'text':'flow'}">${IT?'Modifica la regola':'Edit the rule'}</button>`}</div><div class="bc-rule-check" id="bc-rule-check-${r.id}" role="status"></div></details>`;};
 const rules=ids=>(ids||[]).map(rule).join(' ');
 const kind=k=>pick(MK,k)||esc(k||'');
 const lines=hist.steps.map(s=>{used=[];const line=sentence(s);return line+(used.length?`<div class="bc-rules">${used.map(ruleBlock).join('')}</div>`:'');});
 function sentence(s){switch(s.step){
  case 'SOURCE':return tx('SOURCE',`<span translate="no">${esc(s.source||'—')}</span>`,b(s.owner));
  case 'SOURCE_MISSING':return tx('SOURCE_MISSING',`<span translate="no">${esc(s.source||'—')}</span>`);
  case 'MATCH':return s.state==='MATCHED'?tx('MATCH_MATCHED',esc(s.counterpart_id),kind(s.kind)):tx(s.state==='AMBIGUOUS'?'MATCH_AMBIGUOUS':s.state==='WAITING'?'MATCH_WAITING':'MATCH_OTHER',kind(s.kind));
  case 'BANK_NARRATIVE':return tx('BANK_NARRATIVE',`<span translate="no">${esc(s.narrative)}</span>`,s.why?' → '+b(s.why):'');
  case 'WHO_HUMAN':case 'WHO_WEB_RESTAURANT':case 'WHO_TEXT':return tx(s.step,b(s.who));
  case 'VIA':return s.rules&&s.rules.length?tx('VIA_RULE',b((s.via||[]).join(', ')),rules(s.rules)):tx('VIA',b((s.via||[]).join(', ')));
  case 'WHO_HELD':return tx('WHO_HELD',b(s.who),esc(noteText(s.note)));
  case 'WHO_RULE':return tx(s.known?'WHO_RULE':'WHO_RULE_NEW',b(s.who),rules(s.rules))+(s.known||K.protected?'':newWhoHtml(s.who));
  case 'WHO_OTHER':return tx('WHO_OTHER',b(s.who),esc(pick(WM,s.method)||s.method||''));
  case 'WHO_RULES_DISAGREE':return tx('WHO_RULES_DISAGREE',b((s.candidates||[]).join(' / ')),rules(s.rules));
  case 'WHO_TEXT_AMBIGUOUS':return s.note?tx('WHO_TEXT_AMBIGUOUS_RULE',b((s.candidates||[])[0]),s.rules&&s.rules.length?(IT?' dalla regola ':' by the rule ')+rules(s.rules):'',esc(noteText(s.note))):tx('WHO_TEXT_AMBIGUOUS',b((s.candidates||[]).join(' / ')));
  case 'WHO_NONE':return tx(s.via&&s.via.length?'WHO_NONE_VIA':'WHO_NONE');
  case 'RESEARCH':{const src=(s.sources||[]).length?' ('+s.sources.map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title||x.url)}</a>`).join(', ')+')':'';
   const why=s.why?' → '+b(s.why):'';return H['RESEARCH_'+s.outcome]?tx('RESEARCH_'+s.outcome,b(s.who),why+src):esc(s.outcome);}
  case 'WHY_HUMAN':case 'WHY_RESTAURANT':return tx(s.step,b(s.why));
  case 'WHY_CONFIG':return tx('WHY_CONFIG',b(s.why),esc(pick(CM,s.method)||s.method));
  case 'WHY_RULE':return tx('WHY_RULE',b(s.why),rules(s.rules));
  case 'WHY_OTHER':return tx('WHY_OTHER',b(s.why),esc(pick(WM,s.method)||s.method||''));
  case 'WHY_OPEN':{if(s.code==='WHY_RULES_CONFLICT'&&s.rules&&s.rules.length)return tx('WHY_OPEN_CONFLICT',rules(s.rules));
   if(s.rules&&s.rules.length)return tx('WHY_OPEN_RULES',s.rules.map(id=>rule(id)+' <small>('+esc(pick(RO,(s.outcomes||{})[id])||(s.outcomes||{})[id]||'')+')</small>').join(' '));
   return tx(s.mode==='MULTIPLE'?'WHY_OPEN_MULTIPLE_NONE':'WHY_OPEN_UNIQUE');}
  case 'SPLIT':return tx('SPLIT',esc(s.lines));
  case 'WHAT':return tx('WHAT',b(s.what));
  case 'WHOM':return tx(s.exception?'WHOM_EXC':'WHOM',b(s.whom));
  case 'ANOMALY':return H[s.code]?tx(s.code):tx('ANOMALY',`<span translate="no">${esc(s.message)}</span>`);
  default:return esc(s.step);}}
 return `<h3>${esc(L('history'))}</h3><ol class="bc-list bc-history">${lines.map(x=>`<li>${x}</li>`).join('')}</ol>`;
}
const L=(k,...a)=>{const v=(S[k]||[k,k])[IT?1:0];return v.replace(/\{(\d)\}/g,(_,i)=>a[+i]??'');};
const pick=(d,k,...a)=>{const v=d[k];if(!v)return null;return v[IT?1:0].replace(/\{(\d)\}/g,(_,i)=>a[+i]??'');};
const subjectWord=s=>s==='PERSONAL'?L('personal'):s==='COMPANY'?L('company'):L('unknownOwner');

// static texts of the window
$('bc-title').textContent=L('title');$('bc-close').textContent=L('close');$('bc-next').textContent=L('next');
$('bc-confirm').textContent=L('confirm');$('bc-confirm-next').textContent=L('confirmNext');
$('bc-help').setAttribute('aria-label',L('help'));$('bc-x').setAttribute('aria-label',L('x'));

let ctx=null,K=null,whos=null,ai=null,sim=null,changed=false,busy=false,lastId=null;
const resolvedIds=new Set();
async function getJSON(url){const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});const v=await r.json().catch(()=>({}));
 if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
async function postJSON(url,body){return postForm(url,[['payload',JSON.stringify(body)]]);}
async function postForm(url,pairs){const b=new URLSearchParams({csrf_token:csrf()});pairs.forEach(([k,v])=>b.append(k,v??''));
 const r=await fetch(url,{method:'POST',credentials:'same-origin',body:b});const v=await r.json().catch(()=>({}));
 if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
function err(t){$('bc-error').hidden=!t;$('bc-error').textContent=t||'';}

function queue(){return (ctx&&ctx.queue)||[];}
function position(){const q=queue();const i=q.indexOf(K?K.id:lastId);$('bc-pos').textContent=q.length>1&&i>=0?L('pos',i+1,q.length):'';}
function nextId(){const q=queue();let i=q.indexOf(lastId);for(let j=i+1;j<q.length;j++){if(!resolvedIds.has(q[j]))return q[j];}return null;}

async function load(id){
 lastId=id;K=null;ai=null;sim=null;err('');busy=true;buttons();
 $('bc-body').innerHTML=`<p class="bc-note">${esc(L('loading'))}</p>`;position();
 try{const d=await getJSON('/bank/complete/case/'+id);K=Object.assign({id},d);}
 catch(e){$('bc-body').innerHTML='';err(e.message);busy=false;buttons();return;}
 busy=false;
 if(K.resolved&&ctx&&ctx.autoSkip){resolvedIds.add(id);const n=nextId();if(n){load(n);return;}closeIt();return;}
 render();
}

function whyOptions(sel){return `<option value="">${esc(L('choose'))}</option>`+K.whys.map(y=>`<option value="${y.id}" ${y.id===sel?'selected':''}>${esc(y.name)}</option>`).join('');}
function whatOf(id){const y=K.whys.find(x=>x.id===+id);return y?y.what:'—';}
function whyName(id){const y=K.whys.find(x=>x.id===+id);return y?y.name:'—';}

function proposalHtml(p){
 if(!p)return `<p class="bc-note">${esc(L('noProposal'))}</p>`;
 let origin=pick(O,p.origin,p.times,subjectWord(p.subject))||p.origin;
 if(p.origin==='ENGINE'&&p.method)origin+=' · '+(pick(WM,p.method)||p.method);
 const what=p.why_id?whatOf(p.why_id):null;
 let h=`<div class="bc-prop"><small>${esc(origin)}</small><div><strong translate="no">${esc(p.who||K.recognised.who||'—')}</strong> → <strong translate="no">${esc(p.why||'—')}</strong>${what?` <small translate="no">(${esc(what)})</small>`:''}</div>`;
 if(p.personal_why_id||p.company_why_id)h+=`<div><small>${esc(L('personalWhy'))}: <span translate="no">${esc(p.personal_why_id?whyName(p.personal_why_id):'—')}</span> · ${esc(L('companyWhy'))}: <span translate="no">${esc(p.company_why_id?whyName(p.company_why_id):'—')}</span></small></div>`;
 if(p.reason)h+=`<div><small class="flow-chat-text">${esc(p.reason)}</small></div>`;
 if(p.question)h+=`<div><strong>${esc(L('question'))}:</strong> <span class="flow-chat-text">${esc(p.question)}</span></div>`;
 if(p.sources&&p.sources.length)h+=`<div><small>${esc(L('sources'))}: ${p.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title||s.url)}</a>`).join(', ')}</small></div>`;
 return h+'</div>';
}

function opsHtml(o){
 if(!o)return '';const parts=[];
 const mvLine=x=>`<span translate="no">#${x.id} · ${esc(x.date)} · ${esc(x.source||'')} · ${esc(x.description)} · ${money(x.amount_minor)}</span>`;
 if(o.duplicate)parts.push(`<div class="bc-prop"><div>${esc(L('dup',o.duplicate.of?o.duplicate.of.id:'—'))}</div>${o.duplicate.of?`<div><small>${mvLine(o.duplicate.of)}</small></div>`:''}
  <div class="bc-row"><button type="button" class="btn-secondary" data-op="duplicate" data-v="CONFIRMED_DISTINCT">${esc(L('distinct'))}</button><button type="button" class="btn-secondary" data-op="duplicate" data-v="CONFIRMED_DUPLICATE">${esc(L('isDup'))}</button></div></div>`);
 if(o.match){const m=o.match;const head=m.state==='AMBIGUOUS'?L('matchAmb'):m.state==='WAITING'?L('matchWait'):L('matchMaybe');
  parts.push(`<div class="bc-prop"><div>${esc(head)}</div>${m.candidates.length?m.candidates.map((x,i)=>`<label class="bc-check"><input type="radio" name="bc-cp" value="${x.id}" ${x.ok?'':'disabled'} ${x.ok&&m.candidates.length===1?'checked':''}> ${mvLine(x)}</label>`
   +(x.missing_currency&&x.missing_currency.length?`<p class="bc-note">${esc(L('noCurrency'))} ${x.missing_currency.map(c=>`<span translate="no">${esc(c.name)}</span> (<a href="/bank/sources?edit=${c.id}">${esc(L('setCurrency'))}</a>)`).join(', ')}</p>`:'')).join('')
   +`<div class="bc-row"><button type="button" class="btn-secondary" data-op="match">${esc(L('pair'))}</button></div>`:`<p class="bc-note">${esc(L('noCand'))}</p>`}</div>`);}
 if(o.whom)parts.push(`<div class="bc-prop"><div>${esc(L('whomNeed'))}</div><div class="bc-row"><label>WHOM<select id="bc-whom" translate="no"><option value="">${esc(L('choose'))}</option>${o.whom.entities.map(e=>`<option value="${e.id}" ${e.id===o.whom.default?'selected':''}>${esc(e.name)}</option>`).join('')}</select></label><button type="button" class="btn-secondary" data-op="whom">${esc(L('saveWhom'))}</button></div></div>`);
 return parts.length?`<h3>${esc(L('ops'))}</h3>`+parts.join(''):'';
}
async function runOp(b){
 err('');const op=b.dataset.op;let body={transaction_id:K.id};
 if(op==='duplicate')body.decision=b.dataset.v;
 if(op==='match'){const r=document.querySelector('input[name="bc-cp"]:checked');if(!r){err(IT?'Scegli la controparte.':'Choose the counterpart.');return;}body.counterpart_id=+r.value;}
 if(op==='whom'){const v=+($('bc-whom')||{}).value;if(!v){err(IT?'Scegli il WHOM.':'Choose the WHOM.');return;}body.entity_id=v;}
 b.disabled=true;
 try{await postJSON('/bank/complete/'+op,body);changed=true;await load(K.id);flash(L('opDone'));}
 catch(e){err(e.message);b.disabled=false;}
}
dlg.addEventListener('click',e=>{const b=e.target.closest('[data-op]');if(b&&K)runOp(b);});

function render(){
 const k=K,mv=k.movement,rec=k.recognised||{};
 let h=`<h3>${esc(L('movement'))}</h3><dl class="bc-mv">
  <dt>${esc(L('date'))}</dt><dd>${esc(mv.date)}</dd><dt>${esc(L('amount'))}</dt><dd>${money(mv.amount_minor)}</dd>
  <dt>${esc(L('description'))}</dt><dd translate="no">${esc(mv.description)}</dd>
  <dt>${esc(L('account'))}</dt><dd translate="no">${esc((mv.source||{}).name||'—')}</dd>
  <dt>${esc(L('owner'))}</dt><dd><span translate="no">${esc((mv.owner||{}).name||'—')}</span> (${esc(subjectWord((mv.owner||{}).subject))})</dd></dl>`;
 if(k.kind==='EXCLUDED'||k.kind==='DONE'){$('bc-body').innerHTML=h+`<p class="bc-ok">${esc(L(k.kind==='EXCLUDED'?'excluded':'done'))}</p>`+historyHtml(k.history);buttons();return;}
 if(k.kind==='BANK_REASON'){
   renderBankReason(h);return;
 }
 const items=[];
 if(rec.who)items.push(`${esc(L('who'))}: <strong translate="no">${esc(rec.who)}</strong>${rec.who_method?` <small>(${esc(pick(WM,rec.who_method)||rec.who_method)})</small>`:''}`);
 if(rec.why)items.push(`${esc(L('why'))}: <strong translate="no">${esc(rec.why)}</strong>${rec.why_method?` <small>(${esc(pick(WM,rec.why_method)||rec.why_method)})</small>`:''}`);
 if(rec.what)items.push(`WHAT: <span translate="no">${esc(rec.what)}</span>`);
 if(rec.whom)items.push(`WHOM: <span translate="no">${esc(rec.whom)}</span>`);
 if(k.history&&k.history.steps&&k.history.steps.length)h+=historyHtml(k.history);
 else h+=`<h3>${esc(L('recognised'))}</h3>`+(items.length?`<ul class="bc-list">${items.map(x=>`<li>${x}</li>`).join('')}</ul>`:`<p class="bc-note">${esc(L('nothing'))}</p>`);
 if(k.protected)h+=`<p class="bc-note">${esc(L('protectedNote'))}</p>`;
 const miss=[];if(!rec.who)miss.push('WHO');if(!rec.why)miss.push('WHY');
 h+=`<h3>${esc(L('missing'))}</h3><ul class="bc-list">${k.open.map(x=>`<li>${esc(pick(C,x.code)||x.label||x.message)}${x.missing&&x.missing.length?' — <span>'+esc(x.missing.join(', '))+'</span>':''}${!C[x.code]?'':((x.code==='WHO_AMBIGUOUS'&&!(k.history&&k.history.steps&&k.history.steps.length))||x.code==='INCOMPLETE'?` <small translate="no">${esc(x.message)}</small>`:'')}</li>`).join('')||`<li>${esc(miss.join(', ')||(k.kind==='CONFIRM'?L('onlyConfirm'):'—'))}</li>`}</ul>`;
 if(k.kind==='INFO'){
  h+=opsHtml(k.ops);
  h+=`<h3>${esc(L('info'))}</h3><p class="bc-note">${esc(L('infoNote'))}</p><ul class="bc-list">${k.info.map(x=>`<li>${esc(pick(C,x.code)||x.message)}${x.link?` <a href="${esc(x.link)}">${esc(L('open'))}</a>`:''}</li>`).join('')}</ul>`;
  $('bc-body').innerHTML=h;buttons();return;}
 h+=opsHtml(k.ops);
 const p=ai||k.proposal;
 h+=`<h3>${esc(L('proposal'))}</h3><div id="bc-prop">${proposalHtml(p)}</div>`;
 h+=k.ai_available?`<div class="bc-row"><label>${esc(L('correct'))}<textarea id="bc-msg" placeholder="${esc(L('correctPh'))}"></textarea></label>
   <button type="button" class="btn-secondary" id="bc-ai">${esc(L('askAi'))}</button></div><p class="bc-note" id="bc-ai-state" role="status"></p>`
  :`<p class="bc-note">${esc(L('aiOff'))}</p>`;
 if(k.ai_available && k.kind==='WHY' && rec.who_id){
  h+='<button type="button" class="btn-secondary" id="bc-group">'+(IT?'Analizza i movimenti di questo WHO':'Analyse movements of this WHO')+'</button><div id="bc-group-result" role="status"></div>';
 }
 // the person's classification, prefilled from the proposal
 const whoVal=rec.who||(p&&p.who)||'',whyVal=(p&&p.why_id)||null;
 h+=`<h3>${esc(L('yours'))}</h3><div class="bc-row">`;
 // WHO: the field plus the full list of WHO always visible below it (Product Owner, 2026-11-18: to see at once whether
 // a similar WHO, or one with the same meaning, already exists). Typing narrows the list; a click puts the name in.
 if(k.kind==='WHO')h+=`<div class="bc-who-field"><label for="bc-who">${esc(L('who'))}</label><input id="bc-who" autocomplete="off" translate="no" placeholder="${esc(L('whoPh'))}" value="${esc(whoVal)}"><small id="bc-who-state"></small><div id="bc-who-list" class="bc-who-list" translate="no"></div></div>`;
 else h+=`<label>${esc(L('who'))}<input value="${esc(whoVal)}" disabled translate="no"></label>`;
 h+=`<label>${esc(L('why'))}<select id="bc-why" translate="no">${whyOptions(whyVal)}</select><small>${esc(L('what'))}: <span id="bc-what" translate="no">${esc(whyVal?whatOf(whyVal):'—')}</span></small></label></div>`;
 if(k.bank_reason)h+='<button type="button" class="btn-secondary" id="bc-bank">È una operazione della banca</button>';
 h+=`<div id="bc-reuse"></div>`;
 $('bc-body').innerHTML=h;
 if($('bc-bank'))$('bc-bank').onclick=()=>{K.kind='BANK_REASON';render();};
 const groupButton=$('bc-group');
 if(groupButton)groupButton.onclick=async()=>{
  const output=$('bc-group-result');
  groupButton.disabled=true;
  output.textContent=L('loading');
  try {
   const {analysis}=await postForm('/bank/complete/group',[['transaction_id',mv.id]]);
   const messages=analysis.proposals.map(p=>p.text+' · '+p.resolves+'/'+analysis.movements);
   for(const limit of analysis.limits||[])if(limit.text)messages.push(limit.text);
   output.textContent=messages.join(' | ')||(IT?'Nessuna regola proposta.':'No rule proposed.');
  } catch(error){output.textContent=error.message;}
  finally{groupButton.disabled=false;}
 };
 if(k.kind==='WHO')initWho();
 $('bc-why').addEventListener('change',()=>{$('bc-what').textContent=$('bc-why').value?whatOf($('bc-why').value):'—';renderReuse();buttons();});
 if($('bc-ai'))$('bc-ai').addEventListener('click',askAi);
 renderReuse(p&&p.applies);buttons();
}

function renderBankReason(header){
 const group=K.bank_reason;
 $('bc-body').innerHTML=header+opsHtml(K.ops)+`<h3>Operazioni della banca</h3><p>${esc(group.bank)} · ${esc(group.narrative)} · ${group.count} movimenti</p>
 <label>Quale WHY si applica a questa causale in ${group.direction==='IN'?'entrata':'uscita'}?
 <select id="bc-bank-why">${whyOptions(null)}</select></label>
 <button type="button" id="bc-bank-save" disabled>Salva WHY per questa causale</button>`;
 const select=$('bc-bank-why'), save=$('bc-bank-save');
 select.onchange=()=>save.disabled=!select.value;
 save.onclick=async()=>{
   save.disabled=true;
   try{
     await postJSON('/bank/complete/bank-reasons',{transaction_id:K.id,why_id:Number(select.value)});
     changed=true; await load(K.id);
   }catch(error){err(error.message);save.disabled=false;}
 };
 buttons();position();
}

async function initWho(){
 if(!whos){try{whos=(await getJSON('/bank/complete/whos')).whos;}catch(e){whos=[];}}
 const list=$('bc-who-list');
 list.innerHTML=whos.map(w=>`<button type="button" class="bc-who-item" data-name="${esc(w.name)}">${esc(w.name)}</button>`).join('');
 const items=[...list.querySelectorAll('.bc-who-item')];
 const filter=()=>{const q=$('bc-who').value.trim().toUpperCase();let shown=0;
  items.forEach(b=>{const on=!q||b.dataset.name.toUpperCase().includes(q);b.hidden=!on;if(on)shown++;});
  list.dataset.empty=shown?'':'1';};
 list.addEventListener('click',e=>{const b=e.target.closest('.bc-who-item');if(!b)return;$('bc-who').value=b.dataset.name;$('bc-who').dispatchEvent(new Event('input'));$('bc-who').focus();});
 const upd=()=>{const w=whoMatch();$('bc-who-state').textContent=!$('bc-who').value.trim()?'':(w?L('existingWho'):L('newWho'));filter();renderReuse();buttons();};
 $('bc-who').addEventListener('input',upd);upd();
}
function whoMatch(){if(!K||K.kind!=='WHO')return K&&K.recognised.who_id?{id:K.recognised.who_id,name:K.recognised.who}:null;
 const v=($('bc-who')||{}).value||'';const key=v.trim().toUpperCase().replace(/\s+/g,' ');
 return (whos||[]).find(w=>w.name.toUpperCase().replace(/\s+/g,' ')===key)||null;}
function chosen(){const why=+($('bc-why')||{}).value||null;const w=whoMatch();
 const name=K.kind==='WHO'?(($('bc-who')||{}).value||'').trim():K.recognised.who;
 return {why_id:why,who_id:w?w.id:(K.kind==='WHO'?null:K.recognised.who_id),who:w?w.name:name};}

// ---- reuse --------------------------------------------------------------------------------------------------
function scope(){const r=document.querySelector('input[name="bc-scope"]:checked');return r?r.value:'only';}
function ownerSubject(){return (K.movement.owner||{}).subject||null;}
function ownerException(){const o=K.movement.owner;if(!o||!K.config)return null;return (K.config.exceptions||[]).find(x=>x.entity_id===o.id)||null;}
function renderReuse(applies){
 const box=$('bc-reuse');if(!box)return;sim=null;
 const c=chosen();const who=c.who||'WHO';
 if(!c.why_id||!(c.who_id||c.who)){box.innerHTML='';return;}
 let h=`<h3>${esc(L('scope'))}</h3>`;
 if(K.reuse==='RULE'){
  h+=`<p class="bc-note">${esc(L('rule',who))}</p><button type="button" class="btn-secondary" id="bc-rule">${esc(L('defineRule'))}</button><p class="bc-note">${esc(L('ruleOnly'))}</p>`;
  box.innerHTML=h;$('bc-rule').onclick=openRule;return;}
 const prev=scope();
 const sel=applies==='ALL_OF_WHO'?'single':applies==='BY_OWNER_KIND'?'subject':(applies?'only':prev);
 h+=`<div class="bc-scope"><label><input type="radio" name="bc-scope" value="only" ${sel==='only'?'checked':''}> ${esc(L('only'))}</label>`;
 if(K.reuse==='CONFIG'&&c.who_id){
  const cfg=K.config||{},subj=ownerSubject(),exc=ownerException();
  h+=`<label><input type="radio" name="bc-scope" value="single" ${sel==='single'?'checked':''}> <span translate="no">${esc(L('single',who))}</span></label>`;
  if(subj){
   const pv=subj==='PERSONAL'?c.why_id:((ai&&ai.personal_why_id)||cfg.personal_why_id||(cfg.pairs_proposal||{}).personal_why_id||null);
   const cv=subj==='COMPANY'?c.why_id:((ai&&ai.company_why_id)||cfg.company_why_id||(cfg.pairs_proposal||{}).company_why_id||null);
   h+=`<label><input type="radio" name="bc-scope" value="subject" ${sel==='subject'?'checked':''}> <span translate="no">${esc(L('bySubject',who))}</span></label>
    <div class="bc-row" id="bc-subject" ${sel==='subject'?'':'hidden'}>
     <label>${esc(L('personalWhy'))} ${subj==='PERSONAL'?esc(L('thisSide')):''}<select id="bc-pwhy" translate="no" ${subj==='PERSONAL'?'disabled':''}>${whyOptions(pv)}</select></label>
     <label>${esc(L('companyWhy'))} ${subj==='COMPANY'?esc(L('thisSide')):''}<select id="bc-cwhy" translate="no" ${subj==='COMPANY'?'disabled':''}>${whyOptions(cv)}</select></label></div>`;
  }
  h+=`<p class="bc-note">${esc(exc?L('excThis',K.movement.owner.name):L('excKept'))}</p>`;
 }else if(K.reuse==='TEXT'){
  const suggested=(K.movement.description||'').replace(/\d[\d\s#*\/.-]{3,}.*/,'').trim().slice(0,40);
  h+=`<label><input type="radio" name="bc-scope" value="text" ${sel==='text'||(applies&&applies!=='THIS_ONLY'&&applies!=='DEPENDS_ON_MOVEMENT')?'checked':''}> <span translate="no">${esc(L('text',who))}</span>:</label>
   <div class="bc-row"><label><input id="bc-text" translate="no" value="${esc(suggested)}"></label></div>`;
  const w=whoMatch();const noCfg=!w||!K.config||!K.config.behaviour;
  if(noCfg&&ownerSubject())h+=`<p class="bc-note">${esc(L('textCfg',who,subjectWord(ownerSubject())))}</p>`;
 }
 h+=`</div><div id="bc-sim"></div>`;
 box.innerHTML=h;
 box.querySelectorAll('input[name="bc-scope"]').forEach(r=>r.addEventListener('change',()=>{if($('bc-subject'))$('bc-subject').hidden=scope()!=='subject';sim=null;renderSim();buttons();}));
 box.addEventListener('change',e=>{if(e.target.matches('#bc-pwhy,#bc-cwhy'))resetSim();});
 if($('bc-text'))$('bc-text').addEventListener('input',resetSim);
 renderSim();
}
function resetSim(){sim=null;renderSim();buttons();}
function draft(){
 const c=chosen(),cfg=K.config||{},s=scope(),exc=ownerException();
 const exceptions=(cfg.exceptions||[]).map(x=>({entity_id:x.entity_id,why_id:x.why_id,whom_id:x.whom_id}));
 if(K.reuse==='TEXT'){const subj=ownerSubject();if(!subj)return null;
  return {behaviour:'BY_SUBJECT',personal_why_id:subj==='PERSONAL'?c.why_id:null,company_why_id:subj==='COMPANY'?c.why_id:null,exceptions:[]};}
 if(exc){exceptions.forEach(x=>{if(x.entity_id===exc.entity_id)x.why_id=c.why_id;});}
 if(s==='single')return {who_id:c.who_id,behaviour:'SINGLE',why_id:exc?(cfg.why_id||c.why_id):c.why_id,exceptions};
 const pv=+(($('bc-pwhy')||{}).value)||null,cv=+(($('bc-cwhy')||{}).value)||null,subj=ownerSubject();
 return {who_id:c.who_id,behaviour:'BY_SUBJECT',personal_why_id:subj==='PERSONAL'&&!exc?c.why_id:pv,company_why_id:subj==='COMPANY'&&!exc?c.why_id:cv,exceptions};
}
function renderSim(){
 const box=$('bc-sim');if(!box)return;const s=scope();
 if(s==='only'){box.innerHTML=`<p class="bc-note">${esc(L('neither'))}</p>`;return;}
 if(!sim){box.innerHTML=`<button type="button" class="btn-secondary" id="bc-preview">${esc(L('preview'))}</button>`;$('bc-preview').onclick=preview;return;}
 if(sim.loading){box.innerHTML=`<p class="bc-note">${esc(L('previewing'))}</p>`;return;}
 const rows=sim.rows;
 let h=`<p><strong>${esc(rows.length?L('changes',rows.length):L('noChanges'))}</strong></p>`;
 if(sim.summary)h+=`<p class="bc-note">${esc(L('summary',sim.summary.unchanged,sim.summary.still_open,sim.summary.protected))}</p>`;
 if(rows.length)h+=`<div class="bc-scroll"><table class="bc-table"><thead><tr><th>${esc(L('date'))}</th><th>${esc(L('account'))}</th><th>${esc(L('description'))}</th><th class="num">${esc(L('amount'))}</th><th>${esc(L('before'))}</th><th>${esc(L('after'))}</th></tr></thead><tbody>${
  rows.map(x=>`<tr><td>${esc(x.date)}</td><td translate="no">${esc(x.source||'')}<br><small>${esc(x.owner||'')}</small></td><td translate="no">${esc(x.description)}</td><td class="num">${money(x.amount_minor)}</td><td translate="no">${esc(x.before||'—')}</td><td translate="no">${esc(x.after||'—')}</td></tr>`).join('')}</tbody></table></div>`;
 if(rows.length)h+=`<label class="bc-check"><input type="checkbox" id="bc-apply"> ${esc(L('applyOthers',rows.length))}</label>`;
 const who=chosen().who||'WHO';
 h+=`<label class="bc-check"><input type="checkbox" id="bc-save"> ${esc(L('saveCriterion'))}</label><p class="bc-note">${esc(K.reuse==='TEXT'?L('saveTextNote'):L('saveCfgNote',who))}</p><p class="bc-note">${esc(L('neither'))}</p>`;
 box.innerHTML=h;
}
async function preview(){
 err('');const c=chosen(),s=scope();sim={loading:true};renderSim();
 try{
  if(s==='text'){
   const v=await postJSON('/bank/complete/text-preview',{transaction_id:K.id,text:($('bc-text')||{}).value||'',who_id:c.who_id,config_draft:(c.who_id&&K.config&&K.config.behaviour)?null:draft()});
   sim={rows:v.rows.map(x=>({id:x.id,date:x.date,source:x.source,owner:x.owner,description:x.description,amount_minor:x.amount_minor,
    before:(x.who_before||'—')+' / '+(x.why_before||'—'),after:(c.who||'')+' / '+(x.why_after||'—'),ok:!!x.why_after_id}))};
   sim.rows=sim.rows.filter(x=>x.ok);
  }else{
   const v=await postForm('/bank/why-signals/who/simulate',[['draft',JSON.stringify(draft())]]);
   sim={summary:v.summary,rows:v.rows.filter(x=>x.id!==K.id&&(x.effect==='new_why'||x.effect==='changed_why'))};
  }
 }catch(e){sim=null;err(e.message);}
 renderSim();buttons();
}
function openRule(){
 if(!window.BankWhyRuleEditor)return;const mv=K.movement;
 window.BankWhyRuleEditor.open({who_id:K.recognised.who_id,source:(mv.source||{}).id,context:(IT?'Da Completa: ':'From Complete: ')+mv.description,
  movements:[{id:mv.id,date:mv.date,description:mv.description,amount_minor:mv.amount_minor,source:(mv.source||{}).name,why:K.recognised.why}],movements_total:1,
  onSaved:()=>{changed=true;load(K.id).then(()=>{err('');});},onClose:()=>{try{$('bc-why').focus();}catch(_){}}});
}

// ---- AI -----------------------------------------------------------------------------------------------------
async function askAi(){
 err('');const st=$('bc-ai-state');st.textContent=L('aiWorking');$('bc-ai').disabled=true;
 try{const v=await postForm('/bank/complete/ai',[['transaction_id',K.id],['message',($('bc-msg')||{}).value||'']]);
  if(v.resolved){changed=true;resolvedIds.add(K.id);const n=nextId();if(n)await load(n);else closeIt();return;}
  ai=v.proposal;const keep=($('bc-msg')||{}).value||'';render();if($('bc-msg'))$('bc-msg').value=keep;
  if(ai.who&&$('bc-who')&&!$('bc-who').value){$('bc-who').value=ai.who;$('bc-who').dispatchEvent(new Event('input'));}
 }catch(e){err(e.message);st.textContent='';}
 finally{if($('bc-ai'))$('bc-ai').disabled=false;}
}

// ---- confirm ------------------------------------------------------------------------------------------------
function buttons(){
 const actionable=K&&(K.kind==='WHO'||K.kind==='WHY'||K.kind==='CONFIRM');
 const c=actionable&&$('bc-why')?chosen():null;
 const ok=!!(c&&c.why_id&&(c.who_id||c.who))&&!busy&&!(sim&&sim.loading);
 $('bc-confirm').disabled=$('bc-confirm-next').disabled=!ok;
 $('bc-confirm').hidden=$('bc-confirm-next').hidden=!actionable;
 $('bc-next').disabled=busy;
}
async function confirmCase(goNext){
 err('');const c=chosen();
 if(!c.why_id){err(L('chooseWhy'));return;}if(!c.who_id&&!c.who){err(L('chooseWho'));return;}
 const s=scope(),apply=!!($('bc-apply')&&$('bc-apply').checked),save=!!($('bc-save')&&$('bc-save').checked);
 if(s!=='only'&&(apply||save)&&!sim){err(L('previewFirst'));return;}
 const body={transaction_id:K.id,why_id:c.why_id,who_id:c.who_id,new_who:c.who_id?'':c.who,confirmed:true,
  mode:s==='only'?'single':(s==='text'?'text':'config'),apply_ids:apply&&sim?sim.rows.map(x=>x.id):[],save_criterion:save,simulated:!!sim};
 if(body.mode!=='single'){body.draft=draft();if(s==='text')body.text=($('bc-text')||{}).value||'';}
 busy=true;buttons();
 try{
  const v=await postJSON('/bank/complete/confirm',body);changed=true;
  v.written.forEach(x=>resolvedIds.add(x.id));
  if(ctx&&ctx.onWritten)ctx.onWritten(v.written);
  const me=v.written.find(x=>x.id===K.id);
  let msg=me?L('saved',me.who,me.why,me.what||'—'):'';
  const others=v.written.filter(x=>x.id!==K.id).length;if(others)msg+=' '+L('savedOthers',others);
  if(v.skipped&&v.skipped.length)msg+=' '+L('skipped',v.skipped.map(x=>'#'+x.id).join(', '));
  if(v.criterion)msg+=' '+(v.criterion.kind==='text'?L('critText')+(v.criterion.config?' '+L('critCfg'):''):L('critCfg'));
  busy=false;
  if(goNext){const n=nextId();if(n){await load(n);flash(msg);return;}}
  K=Object.assign(K,{kind:'DONE'});$('bc-body').innerHTML=`<p class="bc-ok">${esc(msg)}</p>`+(nextId()?'':`<p class="bc-note">${esc(L('end'))}</p>`);buttons();
 }catch(e){busy=false;err(e.message);buttons();}
}
function flash(msg){if(!msg)return;const p=document.createElement('p');p.className='bc-ok';p.textContent=msg;$('bc-body').prepend(p);}

$('bc-confirm').onclick=()=>confirmCase(false);
$('bc-confirm-next').onclick=()=>confirmCase(true);
$('bc-next').onclick=()=>{const n=nextId();if(n)load(n);else{$('bc-body').innerHTML=`<p class="bc-note">${esc(L('end'))}</p>`;K=null;buttons();}};
const closeIt=()=>{if(dlg.open)dlg.close();};
$('bc-close').onclick=closeIt;$('bc-x').onclick=closeIt;
dlg.addEventListener('close',()=>{const c=ctx;ctx=null;if(c&&c.onClose)c.onClose(changed,lastId);});

window.BankComplete={open(id,options){
 ctx=Object.assign({queue:[id]},options||{});changed=false;resolvedIds.clear();whos=whos||null;
 if(!dlg.open)dlg.showModal();load(id);
}};

// ---- list integration (Riconcilio): one "Completa" per open row, rows updated in place, position kept ------------
const RETURN='bank-complete-return';
function rowButtons(){return [...document.querySelectorAll('.bank-complete-open[data-complete]')].filter(b=>!b.closest('tr.bc-done'));}
function bumpTabs(n){
 const tabs=[...document.querySelectorAll('.review-tab')];if(tabs.length!==2||!n)return;
 const active=tabs.findIndex(t=>t.classList.contains('is-active'));if(active!==0)return;   // rows leave "Without WHO" only
 [[0,-n],[1,n]].forEach(([i,d])=>{tabs[i].childNodes.forEach(nd=>{if(nd.nodeType===3)nd.textContent=nd.textContent.replace(/\((\d+)\)/,(_,v)=>`(${Math.max(0,+v+d)})`);});});
}
function markRows(rows){
 let moved=0;
 rows.forEach(x=>{const tr=document.getElementById('t-'+x.id);if(!tr||tr.classList.contains('bc-done'))return;
  tr.classList.add('bc-done');moved++;
  tr.querySelectorAll('.bank-complete-open').forEach(b=>{const s=document.createElement('span');s.className='badge ok';s.textContent=IT?'Completato':'Completed';
   const n=document.createElement('span');n.className='cell-note';n.setAttribute('translate','no');n.textContent=`${x.who||''} → ${x.why||''}${x.what?' ('+x.what+')':''}`;
   b.replaceWith(s,n);});
  const st=tr.querySelector('[data-cell="status"]');if(st){st.innerHTML='<span class="rp-st rp-st-confirmed" role="img" aria-label="Complete">&#10004;</span><span class="rp-st-text"></span>';st.lastChild.textContent=IT?'Confermato':'Confirmed';}
  const cf=tr.querySelector('[data-action="confirm"]');if(cf)cf.hidden=true;});
 bumpTabs(moved);
}
document.addEventListener('click',e=>{
 const b=e.target.closest('.bank-complete-open[data-complete]');if(!b)return;e.preventDefault();
 const ids=rowButtons().map(x=>+x.dataset.complete);const id=+b.dataset.complete;
 window.BankComplete.open(id,{queue:ids.includes(id)?ids:[id],autoSkip:true,onWritten:markRows,onClose:(changed,last)=>{
  const q=ids,i=Math.max(0,q.indexOf(last));
  if(changed){try{sessionStorage.setItem(RETURN,JSON.stringify({path:location.pathname+location.search,keys:q.slice(i).concat(q.slice(0,i).reverse()),at:Date.now()}));}catch(_){}
   location.reload();return;}
  const tr=document.getElementById('t-'+last);const btn=tr&&tr.querySelector('.bank-complete-open');
  if(tr){tr.scrollIntoView({block:'center'});(btn||b).focus({preventScroll:true});}
 }});
});
// After the reload that follows a completion: back to the last case's row, else the next one still in the list.
try{const v=JSON.parse(sessionStorage.getItem(RETURN)||'null');
 if(v&&v.path===location.pathname+location.search&&Date.now()-v.at<60000){sessionStorage.removeItem(RETURN);
  const go=()=>{for(const k of v.keys){const tr=document.getElementById('t-'+k);if(tr){tr.scrollIntoView({block:'center'});
   const f=tr.querySelector('.bank-complete-open')||tr.querySelector('button,select,a[href]');if(f)f.focus({preventScroll:true});return;}}};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else setTimeout(go,0);}}catch(_){}
})();
