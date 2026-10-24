const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const money = value => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(value/100);
const day = value => new Intl.DateTimeFormat('en-US',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value+'T12:00:00'));
const icons = {
 meals:'<path d="M5 3v7m3-7v7m-6-7v7c0 3 6 3 6 0M5 13v8M17 3c-3 4-3 10 0 10h2M19 3v18"/>',
 travel:'<path d="m3 11 7 2 3 8 2-1-1-8 6-6c2-2 0-4-2-2l-6 6-8-1z"/>',
 research:'<circle cx="10" cy="10" r="6"/><path d="m14.5 14.5 6 6M7 10h6M10 7v6"/>',
 purpose:'<path d="M6 3h9l4 4v14H6zM15 3v5h4M9 12h7M9 16h7"/>'
};
const initialRules = [
 {id:'meals',title:'Restaurant meals',text:'Restaurant payments on a company card are business meals. Payments on a personal card are personal expenses.',example:'Company card → Business Meal · Personal card → Owner Personal — Restaurant'},
 {id:'travel',title:'Identify a trip and ask its purpose',text:'Group transactions from the same trip. Ask once whether it is personal or business, close the dialog and use that answer for related transactions. Also consider whether the card is personal or company-owned.',example:'«I see a trip to Cozumel. Personal or business?»',open:'To clarify: which takes priority when the stated trip purpose and the card type differ.'},
 {id:'research',title:'Research the counterparty online',text:'Research what each WHO does. Verify the identity, prefer official websites and retain sources. Use this knowledge with the description and context to understand the expense or income.',example:'Prime Line Distributors → food distributor → Food Purchases'},
 {id:'purpose',title:'Understand the purpose with incomplete details',text:'Read the full description. If the overall purpose is clear, fill in WHY without waiting for details the bank does not provide. Do not choose an accounting destination more specific than the evidence supports.',example:'ADP Tax → Payroll Tax Payment · ADP WAGE PAY → Payroll Wages Payment'}
];
const STORAGE='rfone-bank-assistant-local-chat-v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(STORAGE)||'{}');}catch{}
let state={rules:Array.isArray(saved.rules)?saved.rules:structuredClone(initialRules),answers:[],knowledge:[],conversations:saved.conversations||{}};
let snapshot,activeCase,editingRule,showAll=false,returnFocus=null;
function persist(){try{localStorage.setItem(STORAGE,JSON.stringify(state));}catch{toast('Browser storage is unavailable. Changes remain in this session.');}}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,4500);}
function openDialog(id){returnFocus=document.activeElement;$(id).showModal();}
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog=>{dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});dialog.addEventListener('close',()=>{if(returnFocus?.isConnected)returnFocus.focus();else document.querySelector('#cases-list button')?.focus();});});

function managementButtons(kind,id){return `<span class="management-actions"><button type="button" class="text-button" data-manage-kind="${kind}" data-manage-id="${escapeHTML(id)}" data-manage-action="rename">Rename</button><button type="button" class="text-button delete-button" data-manage-kind="${kind}" data-manage-id="${escapeHTML(id)}" data-manage-action="delete">Delete</button></span>`;}
let management=null;
function bindManagement(){document.querySelectorAll('[data-manage-action]').forEach(button=>button.onclick=()=>{
 const {manageKind:kind,manageId:id,manageAction:action}=button.dataset;
 const item=kind==='rule'?snapshot.learned_rules.find(r=>String(r.id)===id):kind==='who'?snapshot.knowledge.find(k=>String(k.who_id)===id):state.rules.find(r=>r.id===id);
 if(!item)return;management={kind,id,action};const title=item.title||item.who;
 $('manage-title').textContent=(action==='rename'?'Rename: ':'Delete: ')+title;
 $('manage-name-label').hidden=action==='delete';$('manage-name').required=action==='rename';$('manage-name').value=title;
 $('manage-description').textContent=action==='rename'?'Change the name only. Conditions and transactions remain unchanged.':kind==='who'?'Permanently delete this profile and its collected information? Imports will not recreate it. Transaction WHO values remain unchanged.':'Permanently delete this entry? It will no longer apply to new transactions. Existing classifications and rollback history remain available.';
 $('manage-submit').textContent=action==='rename'?'Save name':'Delete permanently';$('manage-error').textContent='';openDialog('manage-dialog');if(action==='rename')$('manage-name').focus();
 });}
 $('manage-form').addEventListener('submit',async event=>{
 event.preventDefault();if(!management)return;const {kind,id,action}=management;const title=$('manage-name').value.trim();
 if(action==='rename'&&!title){$('manage-error').textContent='Enter a name.';return;}
 $('manage-submit').disabled=true;
 try{
  if(kind==='guide'){
   if(action==='rename')state.rules.find(r=>r.id===id).title=title;else state.rules=state.rules.filter(r=>r.id!==id);
  }else if(kind==='who')await chatRequest(`/bank/ai-rules/who/${id}/manage`,{action,title});
  else await chatRequest(`/bank/ai-rules/rules/${id}/${action==='rename'?'title':'delete'}`,{user_title:title,response_format:'json'});
  if(action==='delete'){
   if(kind==='rule')state.rules=state.rules.filter(r=>String(r.learned_rule_id)!==id);
   const key=kind==='rule'?'rule-'+id:kind==='who'?'who-'+id:'guide-'+id;delete state.conversations[key];
  }
  if(activeCase&&((kind==='rule'&&String(activeCase.rule_id)===id)||(kind==='who'&&String(activeCase.who_id)===id)||(kind==='guide'&&activeCase.guide_id===id)))$('answer-dialog').close();
  persist();await refreshSnapshot();$('manage-dialog').close();toast(action==='rename'?'Name updated.':'Entry deleted.');
 }catch(error){$('manage-error').textContent=error.message;}finally{$('manage-submit').disabled=false;}
 });
function catalogRow(rule){
 return `<div class="recognition-row"><div><strong>${escapeHTML(rule.title)}</strong><span class="knowledge-badge">${rule.status!=='ACTIVE'?'Paused':(rule.apply_future?'Active for future imports':'Inactive for future imports')}</span><details><summary>Conditions and assignments</summary><p>${escapeHTML(rule.text)}</p><small>Version ${rule.version} · ${escapeHTML(rule.status)}</small></details></div><button type="button" class="text-button" data-rule-id="${rule.id}">Discuss</button>${managementButtons('rule',rule.id)}</div>`;
}
function renderRules(){
 const rules=snapshot?.learned_rules||[];
 const general=rules.filter(r=>r.organization_kind==='GENERAL');
 const signatures=rules.filter(r=>r.organization_kind==='RECOGNITION');
 $('rule-count').textContent=general.length;$('recognition-count').textContent=signatures.length;
 const query=$('rule-search').value.trim().toLocaleLowerCase('en');
 const matches=general.filter(r=>!query||(r.title+' '+r.text).toLocaleLowerCase('en').includes(query));
 $('rules-list').innerHTML=matches.map(catalogRow).join('')||'<p>No matching general rules.</p>';
 const guides=state.rules.filter(r=>!r.learned_rule_id);
 $('rules-list').insertAdjacentHTML('beforeend',`<details class="general-guides"><summary>Instructions to discuss and complete (${guides.length})</summary>${guides.map(r=>`<div class="recognition-row"><div><strong>${escapeHTML(r.title)}</strong><p>${escapeHTML(r.text)}</p><small>Needs clarification before it can be applied.</small></div><button type="button" data-guide="${escapeHTML(r.id)}" class="text-button">Discuss</button>${managementButtons('guide',r.id)}</div>`).join('')}</details>`);
 const search=$('recognition-search').value.trim().toLocaleLowerCase('en');
 const found=signatures.filter(r=>!search||(r.title+' '+r.text).toLocaleLowerCase('en').includes(search));
 $('recognition-list').innerHTML=(search||showAllRecognitions?found:found.slice(0,6)).map(catalogRow).join('')||'<p>No matching profiles.</p>';
 if(!search&&!showAllRecognitions&&found.length>6)$('recognition-list').insertAdjacentHTML('beforeend',`<button class="btn-secondary" id="all-recognitions">Show ${found.length-6} more profiles</button>`);
 $('all-recognitions')?.addEventListener('click',()=>{showAllRecognitions=true;renderRules();});
 document.querySelectorAll('[data-rule-id]').forEach(b=>b.addEventListener('click',()=>openRuleContext({rule_id:b.dataset.ruleId})));
 document.querySelectorAll('[data-guide]').forEach(b=>b.addEventListener('click',()=>openRuleContext({},state.rules.find(r=>r.id===b.dataset.guide))));
 bindManagement();
}
let showAllRecognitions=false,showAllKnowledge=false;
$('add-rule').addEventListener('click',()=>openRuleContext({}, {id:'new-general',title:'New general rule',text:'',kind:'GENERAL'}));
$('add-recognition').addEventListener('click',()=>openRuleContext());
$('rule-search').addEventListener('input',renderRules);$('recognition-search').addEventListener('input',renderRules);
$('knowledge-search').addEventListener('input',renderKnowledge);
$('chat-kind').addEventListener('change',()=>{if(activeCase){conversation().organization_kind=$('chat-kind').value;conversation().preview=null;$('chat-preview').hidden=true;persist();}});

function visibleRows(group){const period=$('period').value;return group.rows.filter(row=>!row.covered&&(period==='all'||row.date.startsWith(period)));}
function sourceList(rows){return [...new Set(rows.map(row=>row.source))].join(' · ');}
function transactionTable(rows){return `<div class="table-scroll"><table><thead><tr><th>Date</th><th>Source</th><th>Description</th><th>Amount</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${day(row.date)}</td><td>${escapeHTML(row.source)}</td><td class="description">${escapeHTML(row.description)}</td><td class="money">${money(row.amount)}</td></tr>`).join('')}</tbody></table></div>`;}
function renderCases(){
 if(!snapshot)return;
 const all=snapshot.cases.map(group=>({...group,visible:visibleRows(group)})).filter(group=>group.visible.length);
 const query=$('search').value.trim().toLocaleLowerCase('en');
 const filtered=all.filter(group=>!query||group.who.toLocaleLowerCase('en').includes(query));
 const count=all.reduce((sum,group)=>sum+group.visible.length,0);
 $('question-count').textContent=all.length;
 $('questions-description').textContent=`${count} transactions to review, grouped into ${all.length} counterparties. Approved rules appear in Rules. Exceptions remain here for clarification; you choose when rules apply.`;
 $('queue-summary').textContent=query?`${filtered.length} WHO matches`:`${all.length} grouped questions for ${count} transactions`;
 const shown=showAll?filtered:filtered.slice(0,6);
 $('cases-list').innerHTML=shown.map(group=>{const rows=group.visible;const total=rows.reduce((sum,row)=>sum+row.amount,0);return `<article class="case-row" id="case-${group.id}"><div><div class="who-name">${escapeHTML(group.who)}</div><div class="case-meta">${rows.length} ${rows.length===1?'transaction':'transactions'} · <span class="money">${money(total)}</span><br>${escapeHTML(sourceList(rows))}</div></div><div class="case-question">${escapeHTML(group.question)}<div class="case-example">${escapeHTML(group.context)}</div></div><button type="button" data-answer="${group.id}">Discuss</button><details class="case-details"><summary>View ${rows.length===1?'il transaction':`i ${rows.length} transactions`}</summary>${transactionTable(rows)}</details></article>`;}).join('');
 if(filtered.length>6&&!showAll)$('cases-list').insertAdjacentHTML('beforeend',`<button type="button" class="btn-secondary" id="show-all">Show ${filtered.length-6} more WHO entries</button>`);
 $('show-all')?.addEventListener('click',()=>{showAll=true;renderCases();});
 $('empty').hidden=filtered.length!==0;
 if(query&&!filtered.length)$('empty').innerHTML='<strong>No WHO matches your search.</strong><p>Try a different part of the name.</p>';
 else $('empty').innerHTML='<strong>No cases to review in this period.</strong><p>Previous answers remain available in saved knowledge.</p>';
 document.querySelectorAll('[data-answer]').forEach(button=>button.addEventListener('click',()=>answerCase(button.dataset.answer)));
}
// The conversation owns authoring and the three execution choices.
let chatPending=false,contextRequest=0;
function conversation(context=activeCase){
 state.conversations ||= {};
 return state.conversations[context.id] ||= {messages:[{role:'assistant',text:context.question+'\n'+context.context}],draft:null,preview:null};
}
async function openRuleContext(values={},startingRule=null){
 const request=++contextRequest;
 try{
  const response=await fetch('/bank/ai-rules/context?'+new URLSearchParams(values),{cache:'no-store',credentials:'same-origin'});
  const context=await response.json();if(!response.ok||!context.ok)throw Error(context.error||'Context unavailable.');
  if(request!==contextRequest)return;
  if(startingRule){context.id='guide-'+startingRule.id;context.starting_rule=startingRule.text;context.guide_id=startingRule.id;context.who=startingRule.title;context.context=startingRule.text;context.organization_kind=startingRule.kind||'GENERAL';}
  activeCase=context;
  const thread=conversation(context);
  if(thread.rule_version!==context.rule_version){thread.draft=null;thread.preview=null;}
  thread.rule_id=context.rule_id||null;thread.rule_version=context.rule_version;
  thread.organization_kind=context.organization_kind||'RECOGNITION';$('chat-kind').value=thread.organization_kind;
  if(context.rule_text&&context.confirmation_token&&(!thread.draft||thread.draft.rule_text===context.rule_text)){thread.draft={rule_text:context.rule_text,confirmation_token:context.confirmation_token};thread.preview=null;}
  $('photo-form').hidden=true;
  $('answer-title').textContent=context.who;$('chat-input').value='';
  $('chat-context').textContent=context.context;
  $('chat-related').innerHTML=!context.rule_id&&context.related_rules.length>1?'<p>Several rules match this transaction. Which one would you like to discuss?</p>'+context.related_rules.map(rule=>`<button type="button" class="btn-secondary" data-related-rule="${rule.id}">${escapeHTML(rule.title)}</button>`).join(''):'';
  document.querySelectorAll('[data-related-rule]').forEach(button=>button.addEventListener('click',()=>openRuleContext({rule_id:button.dataset.relatedRule,transaction_id:context.transaction_id||''})));
  renderConversation();
  if(!$('answer-dialog').open)openDialog('answer-dialog');
  $('chat-input').focus();loadConversationHistory();
 }catch(error){toast(error.message);}
}
function answerCase(id,ruleId=null){
 const group=snapshot.cases.find(item=>String(item.id)===String(id));
 if(!group){toast('Reload the page to reopen this question.');return;}
 const values={transaction_id:group.rows[0].id};
 if(ruleId||group.rule_id)values.rule_id=ruleId||group.rule_id;
 openRuleContext(values);
}
function renderConversation(){
 if(!activeCase)return;const thread=conversation();
 $('chat-messages').innerHTML=thread.messages.map(message=>`<div class="chat-turn chat-${message.role}"><span class="chat-speaker">${message.role==='assistant'?'RF-One':'You'}</span><div>${escapeHTML(message.text).replace(/\n/g,'<br>')}</div></div>`).join('');
 $('chat-confirmation').hidden=!thread.draft;
 $('chat-confirmation').innerHTML=thread.draft?`<div class="rule-confirmation"><span class="eyebrow">RULE TO APPROVE</span><p>${escapeHTML(thread.draft.rule_text).replace(/\n/g,'<br>')}</p><p class="learning-note">Continue the discussion or choose which transactions it applies to. Existing transactions change only after preview and approval.</p><div class="confirmation-actions"><button type="button" class="btn-secondary chat-choice" data-rule-choice="FUTURE">Save · future only</button><button type="button" class="chat-choice" data-rule-choice="PAST_AND_FUTURE">Save · all transactions and future</button></div><p class="cell-note">“All transactions” updates the specified fields, including manual assignments and previous rule results, and enables the rule for future imports.</p></div>`:'';
 document.querySelectorAll('[data-rule-choice]').forEach(button=>button.addEventListener('click',()=>confirmChatRule(button.dataset.ruleChoice)));
 $('chat-preview').hidden=!thread.preview;
 if(thread.preview)renderDatabasePreview(thread.preview);
 setChatPending(chatPending);
}
function setChatPending(pending,caption='Sto ragionando sulla tua indicazione…'){
 chatPending=pending;$('chat-busy').hidden=!pending;$('chat-busy').textContent=caption;
 $('chat-send').disabled=pending;$('chat-input').disabled=pending;
 document.querySelectorAll('#photo-form input,#photo-form select,#photo-form button').forEach(control=>control.disabled=pending);
 document.querySelectorAll('.chat-choice,#chat-apply-past').forEach(button=>button.disabled=pending||Boolean($('chat-input').value.trim()));
}
async function chatRequest(path,values){
 const csrf=document.querySelector('meta[name="bank-csrf"]')?.content||'';
 if(!csrf)throw Error('The Bank session expired. Reload the page.');
 const response=await fetch(path,{method:'POST',body:new URLSearchParams({csrf_token:csrf,...values}),credentials:'same-origin'});
 let payload;try{payload=await response.json();}catch{throw Error('The server could not respond. Try again.');}
 if(!response.ok||payload.ok===false)throw Error(payload.error||'Operation could not be completed.');
 return payload;
}
$('chat-form').addEventListener('submit',async event=>{
 event.preventDefault();if(chatPending||!activeCase)return;
 const text=$('chat-input').value.trim();if(!text)return;
 const context=activeCase,thread=conversation(context);
 thread.draft=null;thread.preview=null;thread.messages.push({role:'user',text});$('chat-input').value='';persist();renderConversation();setChatPending(true);
 try{
  const answer=await chatRequest('/bank/ai-rules/chat',{who_id:context.who_id||'',transaction_id:context.transaction_id||'',rule_id:thread.rule_id||'',starting_rule:context.starting_rule||'',messages:JSON.stringify(thread.messages.slice(-20)),general_rules:JSON.stringify(state.rules.filter(rule=>!rule.learned_rule_id).map(rule=>({title:rule.title,text:rule.text})))});
  thread.messages.push({role:'assistant',text:answer.reply});
  if(answer.ready)thread.draft={rule_text:answer.rule_text,confirmation_token:answer.confirmation_token};
 }catch(error){thread.messages.push({role:'assistant',text:'Interpretation incomplete: '+error.message});}
 finally{setChatPending(false);persist();if(activeCase===context){renderConversation();$('chat-input').focus();}}
});
$('chat-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('chat-form').requestSubmit();}});
$('chat-input').addEventListener('input',()=>setChatPending(chatPending));
function adoptSaved(context,thread,result){
 if(!result.saved_rule_id)return;
 context.rule_id=result.saved_rule_id;context.rule_version=result.saved_rule_version;
 thread.rule_id=result.saved_rule_id;thread.rule_version=result.saved_rule_version;
 if(context.guide_id){const guide=state.rules.find(rule=>rule.id===context.guide_id);if(guide){guide.learned_rule_id=result.saved_rule_id;guide.text=thread.draft?.rule_text||thread.preview?.confirmed_rule||guide.text;}}
 state.conversations['rule-'+result.saved_rule_id]=thread;
 if(result.confirmation_token)thread.draft={rule_text:thread.draft?.rule_text||thread.preview?.confirmed_rule||context.rule_text,confirmation_token:result.confirmation_token};
}
async function confirmChatRule(action){
 if(chatPending||!activeCase||$('chat-input').value.trim())return;
 const context=activeCase,thread=conversation(context),draft=thread.draft;if(!draft)return;
 setChatPending(true,action==='PAST_AND_FUTURE'?'Preparing a preview of all matching transactions…':'Saving your choice…');
 try{
  const result=await chatRequest('/bank/ai-rules/chat/decision',{confirmed:'yes',confirmation_token:draft.confirmation_token,action,organization_kind:thread.organization_kind||'RECOGNITION'});
  if(action==='PAST_AND_FUTURE'){
   thread.preview=result;
   thread.messages.push({role:'assistant',text:`The preview covers ${result.matches} transactions: ${result.planned_updates} would change. The rule has not been applied or enabled for future imports yet. Review the before and after values, then approve below.`});
  }else{
   thread.preview=null;adoptSaved(context,thread,result);await refreshSnapshot();
   thread.messages.push({role:'assistant',text:'Saved and active for future imports. Existing transactions remain unchanged.'});
  }
 }catch(error){thread.messages.push({role:'assistant',text:error.message});}
 finally{setChatPending(false);persist();if(activeCase===context){renderConversation();loadConversationHistory();}}
}
async function applyChatPreview(){
 if(chatPending||!activeCase||$('chat-input').value.trim())return;
 const context=activeCase,thread=conversation(context),preview=thread.preview;if(!preview)return;
 setChatPending(true,'Applying only the approved preview changes…');
 try{
  const result=await chatRequest('/bank/ai-rules/chat/apply',{confirmation_token:preview.confirmation_token,preview_id:preview.preview_id});
  adoptSaved(context,thread,result);thread.preview=null;await refreshSnapshot();
  thread.messages.push({role:'assistant',text:`Application #${result.application.application_id}: ${result.application.updated} transactions updated. The rule is also active for future imports. Roll back changes to existing transactions in this conversation’s history.`});
 }catch(error){thread.preview=null;thread.messages.push({role:'assistant',text:error.message+' Run a new preview before trying again.'});}
 finally{setChatPending(false);persist();if(activeCase===context){renderConversation();loadConversationHistory();}}
}
function renderDatabasePreview(preview){
 const labels={UPDATED:'Da aggiornare',UNCHANGED:'Invariato',PROTECTED:'Protetto',CONFLICT:'Conflitto',UNRESOLVED:'Needs clarification'};
 const items=[...(preview.match_items||[]),...(preview.doubt_items||[])];
 $('chat-preview').innerHTML=`<div class="preview-heading"><span class="eyebrow">BEFORE UPDATING EXISTING TRANSACTIONS</span><h3>Proposed transaction changes</h3></div><p class="preview-rule">${escapeHTML(preview.confirmed_rule)}</p><div class="preview-counts"><span><strong>${preview.examined}</strong> examined</span><span><strong>${preview.planned_updates}</strong> to update</span><span><strong>${preview.unchanged}</strong> unchanged</span><span><strong>${preview.protected}</strong> protected</span><span><strong>${(preview.unresolved||0)+(preview.doubts||0)}</strong> needs clarification</span></div><div class="table-scroll"><table class="chat-preview-table"><thead><tr><th>Date / Account</th><th>Transaction</th><th>Current</th><th>After</th><th>Result</th></tr></thead><tbody>${items.map(item=>`<tr><td>${item.date?day(item.date):'—'}<br><small>${escapeHTML(item.source)}</small></td><td><div class="preview-description">${escapeHTML(item.description)}</div>${money(Math.round(Number(item.amount)*100))}</td><td>${escapeHTML(item.who||'—')}<br><strong>${escapeHTML(item.why||'WHY missing')}</strong><br>${escapeHTML(item.for_whom||'—')}</td><td>${escapeHTML(item.proposed_who||'—')}<br><strong>${escapeHTML(item.proposed_why||'—')}</strong><br>${escapeHTML(item.proposed_for_whom||'—')}</td><td>${labels[item.plan]||'Needs clarification'}<p class="preview-reason">${escapeHTML(item.plan_note||item.reason||'')}</p></td></tr>`).join('')}</tbody></table></div><p class="preview-no-write">Original bank data stays unchanged. Uncertain transactions remain for review. Applied changes can be rolled back without overwriting later edits.</p><button type="button" id="chat-apply-past">Approve and apply this preview</button>`;
 $('chat-apply-past').addEventListener('click',applyChatPreview);
}
async function loadConversationHistory(){
 const context=activeCase,ruleId=conversation(context).rule_id;
 $('chat-history').hidden=!ruleId;if(!ruleId)return;
 try{
  const response=await fetch(`/bank/ai-rules/rules/${ruleId}/applications`,{cache:'no-store',credentials:'same-origin'}),data=await response.json();
  if(activeCase!==context)return;if(!response.ok||!data.ok)throw Error(data.error);
  $('chat-history-list').innerHTML=data.applications.length?data.applications.map(app=>`<div class="chat-history-item"><strong>Application #${app.id}</strong> · ${app.updated} transactions updated${app.rolled_back_at?' · Already rolled back':''}${app.can_rollback?`<button type="button" class="btn-secondary" data-undo-application="${app.id}">Roll back transaction changes</button>`:''}<p id="undo-result-${app.id}" role="status"></p></div>`).join(''):'<p>This rule has not been applied to existing transactions.</p>';
  document.querySelectorAll('[data-undo-application]').forEach(button=>button.addEventListener('click',async()=>{
   if(chatPending)return;button.disabled=true;
   try{const result=await chatRequest(`/bank/ai-rules/applications/${button.dataset.undoApplication}/rollback`,{});conversation(context).preview=null;$('chat-preview').hidden=true;
    $(`undo-result-${button.dataset.undoApplication}`).textContent=`${result.restored} transactions restored; ${result.skipped.length} kept because they were changed later.`+(result.skipped.length?' ID: '+result.skipped.map(item=>item.id).join(', '):'');await refreshSnapshot();persist();
   }catch(error){button.disabled=false;$(`undo-result-${button.dataset.undoApplication}`).textContent=error.message;}
  }));
 }catch(error){$('chat-history-list').textContent='Unable to load history: '+error.message;}
}


function renderKnowledge(){
 const rows=snapshot?.knowledge||[],query=$('knowledge-search').value.trim().toLocaleLowerCase('en');
 const matches=rows.filter(k=>!query||((k.title||'')+' '+k.who+' '+(k.why||'')).toLocaleLowerCase('en').includes(query));
 $('knowledge-count').textContent=rows.length;
 $('knowledge-list').innerHTML=(query||showAllKnowledge?matches:matches.slice(0,6)).map(k=>`<div class="knowledge-row"><div class="who-name">${escapeHTML(k.title||k.who)}${k.title&&k.title!==k.who?`<small>WHO: ${escapeHTML(k.who)}</small>`:''}</div><div><div class="why">Default WHY: ${escapeHTML(k.why||'needs clarification')}</div><p>${escapeHTML(k.summary||'Activity not yet documented with sources.')}</p>${k.suggested_why?`<p>Research suggests: ${escapeHTML(k.suggested_why)} · confirm in the context of this payment.</p>`:''}${(k.sources||[]).map(source=>`<a href="${escapeHTML(source.url)}" target="_blank" rel="noopener">${escapeHTML(source.title)} ↗</a>`).join(' · ')}</div><div><button class="btn-secondary" data-research-who="${k.who_id}">Search the web</button><button class="text-button" data-discuss-who="${k.who_id}">Discuss</button>${managementButtons('who',k.who_id)}<p data-research-result="${k.who_id}" role="status"></p></div></div>`).join('')||'<p>No matching counterparties.</p>';
 if(!query&&!showAllKnowledge&&matches.length>6)$('knowledge-list').insertAdjacentHTML('beforeend',`<button id="all-knowledge" class="btn-secondary">Show ${matches.length-6} more counterparties</button>`);
 bindManagement();
 $('all-knowledge')?.addEventListener('click',()=>{showAllKnowledge=true;renderKnowledge();});
 document.querySelectorAll('[data-discuss-who]').forEach(b=>b.addEventListener('click',()=>openRuleContext({who_id:b.dataset.discussWho})));
 document.querySelectorAll('[data-research-who]').forEach(b=>b.addEventListener('click',async()=>{
  b.disabled=true;const status=document.querySelector(`[data-research-result="${b.dataset.researchWho}"]`);status.textContent='Looking up the activity and official sources…';
  try{await chatRequest(`/bank/ai-rules/who/${b.dataset.researchWho}/research`,{});await refreshSnapshot();toast('WHO knowledge updated with sources. No transactions changed.');}
  catch(error){status.textContent=error.message;b.disabled=false;}
 }));
}
$('period').addEventListener('change',()=>{showAll=false;renderCases();});$('search').addEventListener('input',()=>{showAll=false;renderCases();});
$('reset').addEventListener('click',()=>{state={...state,answers:[],knowledge:[],conversations:{}};persist();renderRules();renderCases();renderKnowledge();toast('Local conversations cleared. Names and deleted entries are preserved.');});
renderRules();renderKnowledge();
async function refreshSnapshot(){const response=await fetch('/bank/ai-rules/snapshot',{cache:'no-store'});if(!response.ok)throw Error('snapshot');snapshot=await response.json();renderRules();renderCases();renderKnowledge();}
fetch('/bank/ai-rules/snapshot').then(response=>{if(!response.ok)throw Error('snapshot');return response.json();}).then(data=>{snapshot=data;renderRules();renderKnowledge();for(const period of data.periods){const option=document.createElement('option');option.value=period;option.textContent=new Intl.DateTimeFormat('en-US',{month:'long',year:'numeric'}).format(new Date(period+'-15T12:00:00'));$('period').append(option);}$('snapshot-date').textContent=`Bank data read on ${data.readAt} · Bank database`;renderCases();}).catch(()=>{$('questions-description').textContent='Unable to load local data. Open the local page URL rather than the file directly.';});


// Open the selected transaction without waiting for the full archive dashboard.
const entry=new URLSearchParams(location.search);if(entry.has('transaction_id')||entry.has('rule_id')){const values={};if(entry.has('transaction_id'))values.transaction_id=entry.get('transaction_id');if(entry.has('rule_id'))values.rule_id=entry.get('rule_id');(entry.get('capture')==='1'?openPhotoCapture(values):openRuleContext(values));}const back=entry.get('return_to');if(back&&/^\/bank(?:[/?#]|$)/.test(back)){$('chat-return').href=back;$('chat-return').hidden=false;}

async function openPhotoCapture(values){
 await openRuleContext(values);if(!activeCase)return;
 const context=activeCase;context.id='capture-'+values.transaction_id;context.rule_id=null;
 const thread=conversation(context);thread.rule_id=null;thread.draft=null;thread.preview=null;thread.organization_kind='RECOGNITION';$('chat-kind').value='RECOGNITION';
 try{
  const response=await fetch(`/bank/ai-rules/capture/${values.transaction_id}`,{cache:'no-store'}),data=await response.json();
  if(!response.ok||!data.ok)throw Error(data.error);
  context.transaction_id=data.transaction_id;context.capture_who=data.who;context.capture_description=data.description;$('answer-title').textContent='Profile · '+data.who;
  $('photo-values').textContent=`WHO: ${data.who} · WHY: ${data.why} · WHOM: ${data.whom} · Destination: ${data.destination||'not set'} · Source: ${data.source} · ${data.direction}`;
  $('photo-pattern').value=data.pattern;$('photo-memo').value=data.memo||'';$('photo-original-memo').textContent=data.memo?'Original memo: '+data.memo:'No separate bank memo.';$('photo-match-op').value=data.match_op;$('photo-form').hidden=false;
  thread.messages=[{role:'assistant',text:'These are the current transaction values. Check how to recognize it, then choose future imports only or all transactions as well.'}];
 }catch(error){thread.messages=[{role:'assistant',text:error.message}];}
 renderConversation();persist();
}
$('photo-form').addEventListener('submit',async event=>{
 event.preventDefault();if(chatPending||!activeCase)return;
 const context=activeCase,thread=conversation();setChatPending(true,'Preparing a profile from the current transaction values…');
 try{
  const result=await chatRequest(`/bank/ai-rules/capture/${context.transaction_id}`,{pattern:$('photo-pattern').value,match_op:$('photo-match-op').value,memo_pattern:$('photo-memo').value});
  thread.rule_id=result.rule_id;context.rule_id=result.rule_id;thread.organization_kind='RECOGNITION';$('chat-kind').value='RECOGNITION';
  thread.draft={rule_text:result.rule_text,confirmation_token:result.confirmation_token};thread.preview=null;
  thread.messages.push({role:'assistant',text:result.rule_id?'A profile with these conditions already exists. It will be updated. Choose where to apply it.':'Profile ready. Choose where to apply it.'});
 }catch(error){thread.draft=null;thread.preview=null;thread.messages.push({role:'assistant',text:error.message});}
 finally{setChatPending(false);renderConversation();persist();loadConversationHistory();}
});
$('photo-pattern').addEventListener('input',()=>{if(activeCase){conversation().draft=null;conversation().preview=null;renderConversation();}});
$('photo-match-op').addEventListener('change',()=>{if(activeCase){$('photo-pattern').value=$('photo-match-op').value==='who'?activeCase.capture_who:activeCase.capture_description;conversation().draft=null;conversation().preview=null;renderConversation();}});

$('photo-memo').addEventListener('input',()=>{if(activeCase){conversation().draft=null;conversation().preview=null;renderConversation();}});
