const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const money = value => new Intl.NumberFormat('it-IT',{style:'currency',currency:'USD'}).format(value/100);
const day = value => new Intl.DateTimeFormat('it-IT',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value+'T12:00:00'));
const icons = {
 meals:'<path d="M5 3v7m3-7v7m-6-7v7c0 3 6 3 6 0M5 13v8M17 3c-3 4-3 10 0 10h2M19 3v18"/>',
 travel:'<path d="m3 11 7 2 3 8 2-1-1-8 6-6c2-2 0-4-2-2l-6 6-8-1z"/>',
 research:'<circle cx="10" cy="10" r="6"/><path d="m14.5 14.5 6 6M7 10h6M10 7v6"/>',
 purpose:'<path d="M6 3h9l4 4v14H6zM15 3v5h4M9 12h7M9 16h7"/>'
};
const initialRules = [
 {id:'meals',title:'Pasti al ristorante',text:'Se pago un ristorante con la carta aziendale, è un meal di lavoro. Se lo pago con la carta personale, è una spesa personale.',example:'Carta aziendale → Business Meal · Carta personale → Owner Personal — Restaurant'},
 {id:'travel',title:'Riconoscere un viaggio e chiedere il motivo',text:'Raggruppa le transazioni che appartengono allo stesso viaggio. Chiedimi una sola volta se è personale o business; chiudi la modale e usa la risposta sui movimenti collegati. Considera anche se la carta è personale o aziendale.',example:'«Vedo un viaggio a Cozumel. Personale o business?»',open:'Da definire insieme: cosa prevale se il tipo di viaggio indicato e la carta utilizzata non coincidono.'},
 {id:'research',title:'Verificare sul web chi è la controparte',text:'Per ogni WHO, cerca su internet cosa fa davvero. Verifica che sia la controparte giusta, preferisci il sito ufficiale e conserva la fonte. Usa questa conoscenza per capire il tipo di spesa o di incasso, insieme alla causale e al contesto.',example:'Prime Line Distributors → distributore alimentare → Food Purchases'},
 {id:'purpose',title:'Capire il motivo, anche senza tutti i dettagli',text:'Leggi tutta la causale. Se il motivo generale è chiaro, compila il WHY senza aspettare una suddivisione che la banca non fornisce. Non forzare una destinazione contabile più precisa delle evidenze.',example:'ADP Tax → Payroll Tax Payment · ADP WAGE PAY → Payroll Wages Payment'}
];
const STORAGE='rfone-bank-assistant-local-chat-v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(STORAGE)||'{}');}catch{}
let state={rules:Array.isArray(saved.rules)?saved.rules:structuredClone(initialRules),answers:[],knowledge:[],conversations:saved.conversations||{}};
let snapshot,activeCase,editingRule,showAll=false,returnFocus=null;
function persist(){try{localStorage.setItem(STORAGE,JSON.stringify(state));}catch{toast('La memoria del browser non è disponibile. Le modifiche restano in questa sessione.');}}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,4500);}
function openDialog(id){returnFocus=document.activeElement;$(id).showModal();}
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog=>{dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});dialog.addEventListener('close',()=>{if(returnFocus?.isConnected)returnFocus.focus();else document.querySelector('#cases-list button')?.focus();});});

function renderRules(){
 $('rule-count').textContent=state.rules.length;
 $('rules-list').innerHTML=state.rules.map(rule=>`<div class="rule-row" id="rule-${escapeHTML(rule.id)}"><div class="rule-icon"><svg viewBox="0 0 24 24" aria-hidden="true">${icons[rule.id]||icons.purpose}</svg></div><div><div class="rule-title">${escapeHTML(rule.title)}</div><div class="rule-copy">${escapeHTML(rule.text)}</div>${rule.example?`<div class="rule-example">${escapeHTML(rule.example)}${rule.id==='travel'?'<button type="button" id="try-trip">Prova la domanda ↗</button>':''}</div>`:''}${rule.open?`<div class="rule-open">${escapeHTML(rule.open)}</div>`:''}</div><button type="button" class="text-button" data-edit="${escapeHTML(rule.id)}" aria-label="Modifica ${escapeHTML(rule.title)}">Modifica</button></div>`).join('');
 document.querySelectorAll('[data-edit]').forEach(button=>button.addEventListener('click',()=>editRule(button.dataset.edit)));
 $('try-trip')?.addEventListener('click',()=>openDialog('trip-dialog'));
}
function editRule(id){editingRule=id;const rule=state.rules.find(r=>r.id===id);$('rule-dialog-title').textContent=rule?'Modifica regola':'Aggiungi una regola';$('rule-name').value=rule?.title||'';$('rule-text').value=rule?.text||'';openDialog('rule-dialog');}
$('add-rule').addEventListener('click',()=>editRule(null));
$('rule-form').addEventListener('submit',event=>{event.preventDefault();const title=$('rule-name').value.trim(),text=$('rule-text').value.trim();if(!title||!text)return;const existing=state.rules.find(r=>r.id===editingRule);if(existing){existing.title=title;existing.text=text;}else state.rules.push({id:'custom-'+Date.now(),title,text});persist();renderRules();$('rule-dialog').close();toast('Regola salvata nell’anteprima.');});
document.querySelectorAll('[data-trip]').forEach(button=>button.addEventListener('click',()=>{const answer=button.dataset.trip;$('trip-dialog').close();toast(`Esempio completato: viaggio ${answer.toLowerCase()}. Nessuna transazione reale modificata.`);}));

function visibleRows(group){const period=$('period').value;return group.rows.filter(row=>(period==='all'||row.date.startsWith(period)));}
function sourceList(rows){return [...new Set(rows.map(row=>row.source))].join(' · ');}
function transactionTable(rows){return `<div class="table-scroll"><table><thead><tr><th>Data</th><th>Source</th><th>Descrizione</th><th>Importo</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${day(row.date)}</td><td>${escapeHTML(row.source)}</td><td class="description">${escapeHTML(row.description)}</td><td class="money">${money(row.amount)}</td></tr>`).join('')}</tbody></table></div>`;}
function renderCases(){
 if(!snapshot)return;
 const all=snapshot.cases.map(group=>({...group,visible:visibleRows(group)})).filter(group=>group.visible.length);
 const query=$('search').value.trim().toLocaleLowerCase('it');
 const filtered=all.filter(group=>!query||group.who.toLocaleLowerCase('it').includes(query));
 const count=all.reduce((sum,group)=>sum+group.visible.length,0);
 $('question-count').textContent=all.length;
 $('questions-description').textContent=`${count} movimenti ancora senza WHY, raggruppati in ${all.length} controparti. Ne parliamo in chat: confermi la regola, poi controlli la sua anteprima su tutto il database.`;
 $('queue-summary').textContent=query?`${filtered.length} WHO trovati`:`${all.length} domande, non ${count}`;
 const shown=showAll?filtered:filtered.slice(0,6);
 $('cases-list').innerHTML=shown.map(group=>{const rows=group.visible;const total=rows.reduce((sum,row)=>sum+row.amount,0);return `<article class="case-row" id="case-${group.id}"><div><div class="who-name">${escapeHTML(group.who)}</div><div class="case-meta">${rows.length} ${rows.length===1?'movimento':'movimenti'} · <span class="money">${money(total)}</span><br>${escapeHTML(sourceList(rows))}</div></div><div class="case-question">${escapeHTML(group.question)}<div class="case-example">${escapeHTML(group.context)}</div></div><button type="button" data-answer="${group.id}">Parliamone</button><details class="case-details"><summary>Vedi ${rows.length===1?'il movimento':`i ${rows.length} movimenti`}</summary>${transactionTable(rows)}</details></article>`;}).join('');
 if(filtered.length>6&&!showAll)$('cases-list').insertAdjacentHTML('beforeend',`<button type="button" class="btn-secondary" id="show-all">Mostra gli altri ${filtered.length-6} WHO</button>`);
 $('show-all')?.addEventListener('click',()=>{showAll=true;renderCases();});
 $('empty').hidden=filtered.length!==0;
 if(query&&!filtered.length)$('empty').innerHTML='<strong>Nessun WHO corrisponde alla ricerca.</strong><p>Prova con una parte diversa del nome.</p>';
 else $('empty').innerHTML='<strong>Nessun caso da chiarire in questo periodo.</strong><p>Le risposte già date rimangono nella conoscenza acquisita.</p>';
 document.querySelectorAll('[data-answer]').forEach(button=>button.addEventListener('click',()=>answerCase(Number(button.dataset.answer))));
}
// Included in app.js at build time: one conversational flow, no direct apply.
let chatPending = false;
function conversation(whoId) {
  state.conversations ||= {};
  if (!state.conversations[whoId]) {
    const group = snapshot.cases.find(item => item.id === whoId);
    state.conversations[whoId] = {messages:[{role:'assistant',text:group.question+'\n'+group.context}],draft:null,preview:null};
  }
  return state.conversations[whoId];
}
function answerCase(id) {
  activeCase = snapshot.cases.find(group => group.id === id);
  $('answer-title').textContent = activeCase.who;
  $('chat-input').value = '';
  renderConversation();
  openDialog('answer-dialog');
  $('chat-input').focus();
}
function renderConversation() {
  if (!activeCase) return;
  const thread=conversation(activeCase.id);
  $('chat-messages').innerHTML=thread.messages.map(message=>`<div class="chat-turn chat-${message.role}"><span class="chat-speaker">${message.role==='assistant'?'RF-One':'Tu'}</span><div>${escapeHTML(message.text).replace(/\n/g,'<br>')}</div></div>`).join('');
  $('chat-confirmation').hidden=!thread.draft;
  $('chat-confirmation').innerHTML=thread.draft?`<div class="rule-confirmation"><span class="eyebrow">QUESTA È LA REGOLA CHE HO CAPITO</span><p>${escapeHTML(thread.draft.rule_text).replace(/\n/g,'<br>')}</p><p class="learning-note">Non l’ho ancora applicata. È corretta, comprese le condizioni e le eccezioni?</p><div class="confirmation-actions"><button type="button" id="confirm-chat-rule">Sì, mostra l’anteprima su tutto il DB</button><button type="button" class="btn-secondary" id="correct-chat-rule">No, ti spiego meglio</button></div></div>`:'';
  $('confirm-chat-rule')?.addEventListener('click',confirmChatRule);
  $('correct-chat-rule')?.addEventListener('click',()=>{$('chat-input').focus();});
  $('chat-preview').hidden=!thread.preview;
  if(thread.preview)renderDatabasePreview(thread.preview);
  setChatPending(chatPending);
}
function setChatPending(pending,caption='Sto capendo la regola dalla tua risposta…') {
  chatPending=pending;
  $('chat-busy').hidden=!pending;
  $('chat-busy').textContent=caption;
  $('chat-send').disabled=pending;
  $('chat-input').disabled=pending;
  if($('confirm-chat-rule'))$('confirm-chat-rule').disabled=pending||Boolean($('chat-input').value.trim());
  if($('correct-chat-rule'))$('correct-chat-rule').disabled=pending;
}
async function chatRequest(path,values) {
  const csrf=document.querySelector('meta[name="bank-csrf"]')?.content||'';
  if(!csrf||csrf.includes('{{'))throw Error('Apri questa chat nel Bank locale sulla porta 5080: questa pagina separata non è collegata all’AI.');
  const body=new URLSearchParams({csrf_token:csrf,...values});
  const response=await fetch(path,{method:'POST',body,credentials:'same-origin'});
  let payload;
  try{payload=await response.json();}catch{throw Error('Il server non riesce a rispondere. Riprova dalla pagina Bank locale.');}
  if(!response.ok||payload.ok===false)throw Error(payload.error||'Non riesco a completare questa richiesta.');
  return payload;
}
$('chat-form').addEventListener('submit',async event=>{
  event.preventDefault();if(chatPending||!activeCase)return;
  const text=$('chat-input').value.trim();if(!text)return;
  const whoId=activeCase.id,thread=conversation(whoId);
  thread.draft=null;thread.preview=null;
  thread.messages.push({role:'user',text});$('chat-input').value='';persist();renderConversation();setChatPending(true);
  try{
    const answer=await chatRequest('/bank/ai-rules/chat',{who_id:String(whoId),messages:JSON.stringify(thread.messages),general_rules:JSON.stringify(state.rules.map(rule=>({title:rule.title,text:rule.text})))});
    thread.messages.push({role:'assistant',text:answer.reply});
    if(answer.ready)thread.draft={rule_text:answer.rule_text,confirmation_token:answer.confirmation_token};
  }catch(error){thread.messages.push({role:'assistant',text:'Non sono riuscito a completare l’interpretazione. '+error.message+' Nessuna modifica applicata.'});}
  finally{setChatPending(false);persist();if(activeCase.id===whoId){renderConversation();$('chat-confirmation').hidden?$('chat-input').focus():$('confirm-chat-rule')?.focus();}}
});
$('chat-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('chat-form').requestSubmit();}});
$('chat-input').addEventListener('input',()=>{if($('confirm-chat-rule'))$('confirm-chat-rule').disabled=chatPending||Boolean($('chat-input').value.trim());});
async function confirmChatRule() {
  if(chatPending||!activeCase)return;
  const whoId=activeCase.id,thread=conversation(whoId),draft=thread.draft;if(!draft)return;
  thread.messages.push({role:'user',text:'Sì, confermo questa regola. Fammi vedere l’anteprima sull’intero database.'});
  renderConversation();setChatPending(true,'Sto verificando la regola su tutti i movimenti del database, anche quelli già classificati…');
  try{
    const preview=await chatRequest('/bank/ai-rules/chat/preview',{confirmed:'yes',confirmation_token:draft.confirmation_token});
    thread.preview=preview;thread.draft=null;
    thread.messages.push({role:'assistant',text:`Ho esaminato ${preview.examined} movimenti su ${preview.database_total} presenti nel database. La regola ne riguarda ${preview.matches}; ${preview.planned_updates} verrebbero aggiornati. Qui sotto vedi anche quelli invariati, protetti, in conflitto o da chiarire. Non ho applicato modifiche.`});
  }catch(error){thread.messages.push({role:'assistant',text:'L’anteprima non è stata completata. '+error.message+' Nessuna modifica applicata.'});}
  finally{setChatPending(false);persist();if(activeCase.id===whoId){renderConversation();$('chat-preview').hidden?$('chat-input').focus():$('chat-preview').scrollIntoView({block:'start',behavior:'smooth'});}}
}
function renderDatabasePreview(preview) {
  const labels={UPDATED:'Da aggiornare',UNCHANGED:'Invariato',PROTECTED:'Protetto',CONFLICT:'Conflitto',UNRESOLVED:'Da chiarire'};
  const items=[...(preview.match_items||[]),...(preview.doubt_items||[])];
  $('chat-preview').innerHTML=`<div class="preview-heading"><span class="eyebrow">REGOLA CONFERMATA · SOLO ANTEPRIMA</span><h3>Come cambierebbe l’intero database</h3></div><p class="preview-rule">${escapeHTML(preview.confirmed_rule)}</p><div class="preview-counts"><span><strong>${preview.examined}</strong> esaminati</span><span><strong>${preview.planned_updates}</strong> da aggiornare</span><span><strong>${preview.unchanged}</strong> invariati</span><span><strong>${preview.protected}</strong> protetti</span><span><strong>${preview.conflicts}</strong> conflitti</span><span><strong>${(preview.unresolved||0)+(preview.doubts||0)}</strong> da chiarire</span></div><p class="preview-scope">Tutti i mesi e tutte le Source, inclusi i movimenti già classificati. ${preview.not_matching} movimenti non corrispondono alla regola. ${preview.excluded_from_scope} esclusi dal perimetro contabile, per esempio duplicati soppressi. Nessun campionamento.</p><div class="table-scroll"><table class="chat-preview-table"><thead><tr><th>Data / Source</th><th>Movimento</th><th>Adesso</th><th>Con la regola</th><th>Esito</th></tr></thead><tbody>${items.map(item=>`<tr><td>${item.date?day(item.date):'—'}<br><small>${escapeHTML(item.source)}</small></td><td><div class="preview-description">${escapeHTML(item.description)}</div><span class="money">${money(Math.round(Number(item.amount)*100))}</span></td><td><span>${escapeHTML(item.who||'—')}</span><br><strong>${escapeHTML(item.why||'WHY mancante')}</strong>${item.for_whom?`<br><small>Per: ${escapeHTML(item.for_whom)}</small>`:''}</td><td><span>${escapeHTML(item.proposed_who||'WHO invariato')}</span><br><strong>${escapeHTML(item.proposed_why||'Nessun nuovo WHY proposto')}</strong>${item.proposed_for_whom?`<br><small>Per: ${escapeHTML(item.proposed_for_whom)}</small>`:''}</td><td><span class="outcome outcome-${escapeHTML(item.plan||'UNRESOLVED')}">${labels[item.plan]||'Da chiarire'}</span><p class="preview-reason">${escapeHTML(item.plan_note||item.reason||'')}</p></td></tr>`).join('')}</tbody></table></div>${!items.length?'<p>Nessun movimento coinvolto da questa regola.</p>':''}<p class="preview-no-write">Nessuna modifica applicata. Puoi correggere la regola continuando la chat e confermare una nuova anteprima.</p>`;
}

function renderKnowledge(){const learned=[{who:'PRIME LINE DISTR',why:'Food Purchases',note:'Distributore alimentare. Correzione esplicita dell’utente, già salvata nel Bank come WHY di default.',origin:'Confermata dall’utente',source:'https://www.primelinedist.com/about'},...state.knowledge];$('knowledge-count').textContent=learned.length;$('knowledge-list').innerHTML=learned.map(item=>`<div class="knowledge-row"><div class="who-name">${escapeHTML(item.who)}</div><div><div class="why">${escapeHTML(item.why)}</div><div class="knowledge-source">${escapeHTML(item.note||'Soluzione da riutilizzare per questa controparte.')}${item.source?`<br><a href="${item.source}" target="_blank" rel="noopener">Fonte: sito ufficiale Prime Line ↗</a>`:''}</div></div><span class="knowledge-badge">${escapeHTML(item.origin)}</span></div>`).join('');}
$('period').addEventListener('change',()=>{showAll=false;renderCases();});$('search').addEventListener('input',()=>{showAll=false;renderCases();});
$('reset').addEventListener('click',()=>{state={rules:structuredClone(initialRules),answers:[],knowledge:[],conversations:{}};persist();renderRules();renderCases();renderKnowledge();toast('Anteprima ripristinata.');});
renderRules();renderKnowledge();
fetch('/bank/ai-rules/snapshot').then(response=>{if(!response.ok)throw Error('snapshot');return response.json();}).then(data=>{snapshot=data;for(const period of data.periods){const option=document.createElement('option');option.value=period;option.textContent=new Intl.DateTimeFormat('it-IT',{month:'long',year:'numeric'}).format(new Date(period+'-15T12:00:00'));$('period').append(option);}$('snapshot-date').textContent=`Dati Bank letti il ${data.readAt} · Anteprima separata dal database operativo`;renderCases();}).catch(()=>{$('questions-description').textContent='Non riesco a caricare i dati locali. Apri la pagina dal collegamento locale, non direttamente dal file.';});

