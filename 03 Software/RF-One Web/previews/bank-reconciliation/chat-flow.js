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
function answerCase(id, ruleId=null) {
  activeCase = snapshot.cases.find(group => group.id === id);
  if(!activeCase){toast('Ricarica la pagina per riaprire questa regola.');return;}
  const thread=conversation(id);
  thread.rule_id=ruleId||activeCase.rule_id||thread.rule_id||null;
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
  $('chat-confirmation').innerHTML=thread.draft?`<div class="rule-confirmation"><span class="eyebrow">QUESTA È LA REGOLA CHE HO CAPITO</span><p>${escapeHTML(thread.draft.rule_text).replace(/\n/g,'<br>')}</p><p class="learning-note">Non l’ho ancora applicata. È corretta, comprese le condizioni e le eccezioni?</p><div class="confirmation-actions"><button type="button" id="confirm-chat-rule">Sì, salva la regola e mostra l’anteprima</button><button type="button" class="btn-secondary" id="correct-chat-rule">No, ti spiego meglio</button></div></div>`:'';
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
  if(!csrf)throw Error('Apri questa chat nel Bank locale sulla porta 5080: questa pagina separata non è collegata all’AI.');
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
    const answer=await chatRequest('/bank/ai-rules/chat',{who_id:String(whoId),messages:JSON.stringify(thread.messages),general_rules:JSON.stringify(state.rules.map(rule=>({title:rule.title,text:rule.text}))),rule_id:thread.rule_id?String(thread.rule_id):''});
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
  thread.messages.push({role:'user',text:'Sì, confermo e salvo questa regola. Fammi vedere l’anteprima sull’intero database.'});
  renderConversation();setChatPending(true,'Sto verificando la regola su tutti i movimenti del database, anche quelli già classificati…');
  try{
    const preview=await chatRequest('/bank/ai-rules/chat/preview',{confirmed:'yes',confirmation_token:draft.confirmation_token});
    thread.preview=preview;thread.draft=null;thread.rule_id=preview.saved_rule_id;
    await refreshSnapshot();
    thread.messages.push({role:'assistant',text:`Ho esaminato ${preview.examined} movimenti su ${preview.database_total} presenti nel database. La regola ne riguarda ${preview.matches}; ${preview.planned_updates} verrebbero aggiornati. Ho salvato la regola nella sezione Regole. I movimenti dubbi o in conflitto restano in Parliamone, collegati alla regola da affinare. Nessuna classificazione è stata applicata.`});
  }catch(error){thread.messages.push({role:'assistant',text:'L’anteprima non è stata completata. '+error.message+' Nessuna modifica applicata.'});}
  finally{setChatPending(false);persist();if(activeCase.id===whoId){renderConversation();$('chat-preview').hidden?$('chat-input').focus():$('chat-preview').scrollIntoView({block:'start',behavior:'smooth'});}}
}
function renderDatabasePreview(preview) {
  const labels={UPDATED:'Da aggiornare',UNCHANGED:'Invariato',PROTECTED:'Protetto',CONFLICT:'Conflitto',UNRESOLVED:'Da chiarire'};
  const items=[...(preview.match_items||[]),...(preview.doubt_items||[])];
  $('chat-preview').innerHTML=`<div class="preview-heading"><span class="eyebrow">REGOLA SALVATA · MOVIMENTI IN ANTEPRIMA</span><h3>Come cambierebbe l’intero database</h3></div><p class="preview-rule">${escapeHTML(preview.confirmed_rule)}</p><div class="preview-counts"><span><strong>${preview.examined}</strong> esaminati</span><span><strong>${preview.planned_updates}</strong> da aggiornare</span><span><strong>${preview.unchanged}</strong> invariati</span><span><strong>${preview.protected}</strong> protetti</span><span><strong>${preview.conflicts}</strong> conflitti</span><span><strong>${(preview.unresolved||0)+(preview.doubts||0)}</strong> da chiarire</span></div><p class="preview-scope">Tutti i mesi e tutte le Source, inclusi i movimenti già classificati. ${preview.not_matching} movimenti non corrispondono alla regola. ${preview.excluded_from_scope} esclusi dal perimetro contabile, per esempio duplicati soppressi. Nessun campionamento.</p><div class="table-scroll"><table class="chat-preview-table"><thead><tr><th>Data / Source</th><th>Movimento</th><th>Adesso</th><th>Con la regola</th><th>Esito</th></tr></thead><tbody>${items.map(item=>`<tr><td>${item.date?day(item.date):'—'}<br><small>${escapeHTML(item.source)}</small></td><td><div class="preview-description">${escapeHTML(item.description)}</div><span class="money">${money(Math.round(Number(item.amount)*100))}</span></td><td><span>${escapeHTML(item.who||'—')}</span><br><strong>${escapeHTML(item.why||'WHY mancante')}</strong>${item.for_whom?`<br><small>Per: ${escapeHTML(item.for_whom)}</small>`:''}</td><td><span>${escapeHTML(item.proposed_who||'WHO invariato')}</span><br><strong>${escapeHTML(item.proposed_why||'Nessun nuovo WHY proposto')}</strong>${item.proposed_for_whom?`<br><small>Per: ${escapeHTML(item.proposed_for_whom)}</small>`:''}</td><td><span class="outcome outcome-${escapeHTML(item.plan||'UNRESOLVED')}">${labels[item.plan]||'Da chiarire'}</span><p class="preview-reason">${escapeHTML(item.plan_note||item.reason||'')}</p></td></tr>`).join('')}</tbody></table></div>${!items.length?'<p>Nessun movimento coinvolto da questa regola.</p>':''}<p class="preview-no-write">Nessuna modifica applicata. Puoi correggere la regola continuando la chat e confermare una nuova anteprima.</p>`;
}
