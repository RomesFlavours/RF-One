const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let snapshot,chat=null,busy=false,preview=null,management=null,catalogProposal=null,scanId=null,pollTimer=null;
let allPhotos=false,parentEditor=null,transactionContext=null;
const embedded=new URLSearchParams(location.search).get('embed')==='1';
if(embedded)document.body.classList.add('flow-embedded');
let reviewedPhotos=new Set();
let photoScope='CURRENT',currentWhom='';
function hasPhotoSave(){return chat?.kind==='PHOTO'&&!parentEditor;}
function resetPhotoScope(){photoScope=chat?.transaction_id?'CURRENT':'FUTURE';currentWhom=chat?.transaction_whom_id||'';}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,5000);}
async function api(path,data){const options={credentials:'same-origin',cache:'no-store'};if(data){options.method='POST';options.body=new URLSearchParams({csrf_token:document.querySelector('meta[name="bank-csrf"]').content,...data});}const response=await fetch(path,options);const value=await response.json();if(!response.ok||value.ok===false)throw Error(value.error||'Operation could not be completed.');return value;}
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>{if(b.closest('dialog').id==='flow-chat'&&parentEditor){if(!busy)returnToExtractor();return;}b.closest('dialog').close();}));
$('flow-chat').addEventListener('close',()=>{if(window.parent!==window&&new URLSearchParams(location.search).get('embed')==='1')window.parent.postMessage({type:'bank-profile-closed',transactionId:chat?.transaction_id},location.origin);});
$('flow-chat').addEventListener('cancel',event=>{if(parentEditor){event.preventDefault();if(!busy)returnToExtractor();}});
function status(text){$('chat-status').textContent=text||'';}
function actions(rule){return `<div class="flow-actions"><button class="btn-secondary" data-edit="${rule.id}">Discuss</button><button class="text-button" data-rename="${rule.id}">Rename</button><button class="text-button delete-button" data-delete="${rule.id}">Delete</button><small>${rule.status!=='ACTIVE'?'Paused':rule.future?'Active for future imports':'Inactive for new imports'} · Version ${rule.version}</small></div>`;}
function ruleRow(r){return `<div class="flow-item"><h3>${esc(r.title)}</h3><p class="flow-chat-text">${esc(r.summary||r.text)}</p>${!r.managed?`<details><summary>Previous text retained in history</summary><p class="flow-chat-text">${esc(r.text)}</p></details>`:''}${actions(r)}</div>`;}
function bindActions(){document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openChat({rule_id:b.dataset.edit}));document.querySelectorAll('[data-rename]').forEach(b=>b.onclick=()=>manage('rule',b.dataset.rename,'rename'));document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>manage('rule',b.dataset.delete,'delete'));}
function render(){
 if(!snapshot)return;
 const query=$('rule-search').value.toLocaleLowerCase('en');$('rules-count').textContent=snapshot.rules.length+(snapshot.drafts||[]).filter(d=>!d.rule_id).length;
 $('rules-list').innerHTML=snapshot.rules.filter(r=>(r.title+' '+r.text).toLocaleLowerCase('en').includes(query)).map(ruleRow).join('')||'<p>No matching AI rules.</p>';
 const drafts=(snapshot.drafts||[]).filter(d=>(d.title+' '+d.text).toLocaleLowerCase('en').includes(query));
 if(drafts.length)$('rules-list').insertAdjacentHTML('afterbegin',`<section aria-label="Saved changes"><h3>Drafts</h3>${drafts.map(d=>`<div class="flow-item"><h3>${esc(d.title)}</h3><p class="flow-chat-text">${esc(d.text)}</p><button type="button" class="btn-secondary" data-open-draft="${d.id}">Edit draft</button></div>`).join('')}</section>`);
 document.querySelectorAll('[data-open-draft]').forEach(b=>b.onclick=()=>openChat({conversation_id:b.dataset.openDraft}));
 const q=$('photo-search').value.toLocaleLowerCase('en');const photos=snapshot.photos.filter(p=>(p.who+' '+p.title+' '+p.rules.map(r=>r.title+' '+r.text).join(' ')).toLocaleLowerCase('en').includes(q));
 $('photos-count').textContent=snapshot.photos.length;
 $('photos-list').innerHTML=(q||allPhotos?photos:photos.slice(0,8)).map((p,i)=>`<div class="flow-item"><h3>${esc(p.title||p.who)}</h3>${p.title!==p.who&&p.who?`<small>WHO: ${esc(p.who)}</small>`:''}${p.summary?`<p>${esc(p.summary)}</p>`:''}${p.why?`<p>Existing default WHY for this WHO: ${esc(p.why)}</p>`:''}${(p.sources||[]).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(' · ')}${p.rules.map(r=>`<details><summary>${esc(r.title)}${r.needs_definition?' · Complete WHY and WHOM':''}</summary><p class="flow-chat-text">${esc(r.text)}</p>${actions(r)}</details>`).join('')}${p.who_id?`<div class="flow-actions"><button class="btn-secondary" data-who="${p.who_id}">${p.rules.length?'Refine this WHO’s cases':'Define WHY and WHOM in chat'}</button><button class="text-button" data-who-rename="${p.who_id}">Rename profile</button><button class="text-button delete-button" data-who-delete="${p.who_id}">Delete profile and cases</button></div>`:''}${!p.rules.length?'<p class="muted">Incomplete: this profile cannot reconcile transactions yet.</p>':''}</div>`).join('')||'<p>No matching profiles.</p>';
 if(!q&&!allPhotos&&photos.length>8)$('photos-list').insertAdjacentHTML('beforeend',`<button id="photos-all" class="btn-secondary">Show ${photos.length-8} more profiles</button>`);
 $('photos-all')?.addEventListener('click',()=>{allPhotos=true;render();});
 bindActions();document.querySelectorAll('[data-who]').forEach(b=>b.onclick=()=>openChat({kind:'PHOTO',who_id:b.dataset.who}));
 document.querySelectorAll('[data-who-rename]').forEach(b=>b.onclick=()=>manage('who',b.dataset.whoRename,'rename'));
 document.querySelectorAll('[data-who-delete]').forEach(b=>b.onclick=()=>manage('who',b.dataset.whoDelete,'delete'));
 $('pending-list').innerHTML=snapshot.pending.map(p=>`<div class="flow-item"><strong>${esc(p.description)}</strong><p>${esc(p.proposal?.probable_who?'Suggested WHO: '+p.proposal.probable_who:p.error||({QUEUED:'Awaiting automatic reconciliation',PROPOSED:'Research to review',STALE:'Transaction changed: review needed',AMBIGUOUS:'Needs clarification',ERROR:'Processing incomplete'}[p.status]||p.status))}</p>${p.proposal?.summary?`<p>${esc(p.proposal.summary)}</p>`:''}${(p.proposal?.sources||[]).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(' · ')}<div class="flow-actions"><a href="/bank/review?q=${encodeURIComponent(p.description)}">Review transaction</a><button class="btn-secondary" data-transaction="${p.id}">Discuss / Recognition profile</button></div></div>`).join('')||'<p>No new transactions to review.</p>';
 document.querySelectorAll('[data-transaction]').forEach(b=>b.onclick=()=>openChat({kind:'PHOTO',transaction_id:b.dataset.transaction}));
}
async function refresh(){snapshot=await api('/bank/flow/snapshot');render();}
$('rule-search').oninput=render;$('photo-search').oninput=render;
$('new-extractor').onclick=()=>openChat({kind:'EXTRACTOR'});$('new-photo').onclick=()=>openChat({kind:'PHOTO'});
async function loadTransactionContext(conversation){
 if(!conversation.transaction_id)return null;
 return (await api(`/bank/flow/transactions/${conversation.transaction_id}/context`)).transaction;
}
function renderTransactionContext(){
 const node=$('flow-transaction-context'),t=transactionContext;
 node.hidden=!t||String(t.id)!==String(chat.transaction_id);
 if(node.hidden){node.replaceChildren();return;}
 const amount=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}).format(t.amount_minor/100);
 const fields=[['Date',t.date],['Amount',`${t.currency||''} ${amount}`.trim()],['Account',t.account],['Source',t.source],['Owner',t.owner]];
 node.innerHTML=`<strong class="flow-transaction-label">Current transaction #${esc(t.id)}</strong><dl class="flow-transaction-meta">${fields.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value||'—')}</dd></div>`).join('')}</dl><p class="flow-transaction-description">${esc(t.description||'No description')}</p>${hasPhotoSave()?`<div class="transaction-whom"><label for="transaction-whom">WHOM · current transaction</label><select id="transaction-whom"><option value="">${t.whom_id?'Default: '+esc(snapshot.catalog.whom.find(x=>x.id===t.whom_id)?.name||'Source owner'):'Choose WHOM…'}</option>${snapshot.catalog.whom.map(x=>`<option value="${x.id}" ${String(x.id)===String(currentWhom)?'selected':''}>${esc(x.name)}</option>`).join('')}</select><small>${currentWhom?'This choice applies only to this transaction.':t.whom_id?'From the Source or your existing manual choice.':'The Source has no owner. Choose WHOM to continue.'}</small></div>`:''}`;
 const select=$('transaction-whom');if(select){select.disabled=busy;select.onchange=async()=>{
  currentWhom=select.value;const scope=preview?.scope;
  if(!scope){renderTransactionContext();return;}
  preview=null;pending(true,'Updating the preview…');
  try{await previewProfile(scope);}catch(error){renderChat();status(error.message);}finally{pending(false,$('chat-status').textContent);}
 };}
}
function focusEditorStart(){
 $('chat-title').focus({preventScroll:true});$('flow-chat-body').scrollTop=0;
}
async function openChat(values){
 if(busy)return;
 try{chat=values.conversation_id?await api(`/bank/flow/conversation/${values.conversation_id}`):await api('/bank/flow/conversation',values);transactionContext=await loadTransactionContext(chat);preview=null;parentEditor=null;reviewedPhotos=new Set();resetPhotoScope();$('chat-input').value=chat.pending_message||'';renderChat();$('flow-chat').showModal();focusEditorStart();}
 catch(error){toast(error.message);}
}
function renderResearch(){
 $('photo-tools').hidden=chat?.kind!=='PHOTO'||!!preview;const r=chat?.research;$('research-panel').hidden=!r;if(!r)return;
 $('research-summary').textContent=(r.summary||'')+(chat.history?.length?'\n'+chat.history.map(h=>'Transaction #'+h.transaction_id+' · '+h.date+' · WHO: '+h.who+' · WHY: '+(snapshot.catalog.why.find(x=>x.id===h.why_id)?.name||h.why_id||'—')+' · WHAT: '+(snapshot.catalog.destinations.find(x=>x.id===h.destination_id)?.name||'—')).join('\n'):'');$('research-summary').style.whiteSpace='pre-line';$('research-sources').innerHTML=(r.sources||[]).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(' · ');
 $('research-who').value=chat.research_known_who||r.probable_who||chat.who||'';$('research-who').readOnly=!!chat.research_known_who;
 const options=chat.research_choices,proposals=r.proposals||[];const why=new Set(options?.why_ids||proposals.map(p=>p.why_id)),what=new Set(options?.what_ids||proposals.map(p=>p.what_id));
 $('research-why').innerHTML=snapshot.catalog.why.map(x=>`<option value="${x.id}" ${why.has(x.id)?'selected':''}>${esc(x.name)}</option>`).join('');
 $('research-what').innerHTML=snapshot.catalog.what.map(x=>`<option value="${x.id}" ${what.has(x.id)?'selected':''}>${esc(x.name)}</option>`).join('');
}
function renderChat(){
 if(!chat)return;renderTransactionContext();renderResearch();$('chat-title').textContent=parentEditor?'Recognition profile · '+chat.who:chat.title||(chat.kind==='EXTRACTOR'?'New AI rule':'New recognition profile');
 $('delete-current-rule').hidden=false; $('delete-current-rule').disabled=busy;
 $('chat-purpose').textContent=chat.kind==='EXTRACTOR'?'How to extract WHO from the description.':'Research WHO and choose WHY and WHAT. WHOM defaults to the Source.';
 const candidates=chat.rule_candidates||[];$('rule-target').hidden=!candidates.length;
 $('rule-target-select').innerHTML='<option value="">Choose the rule to update</option>'+candidates.map(r=>`<option value="${r.id}">${esc(r.title)} (#${r.id})</option>`).join('');
 $('published-definition').hidden=!chat.previous_text; $('published-definition').textContent=chat.previous_text?'Current rule definition: '+chat.previous_text:'';
 $('chat-messages').innerHTML=chat.messages.map(m=>`<div class="chat-message"><strong>${m.role==='user'?'You':'ChatGPT'}</strong><p class="flow-chat-text">${esc(m.text)}</p></div>`).join('');
 const current=chat.current_values;
 $('chat-values').innerHTML=(chat.who?`<p><strong>WHO:</strong> ${esc(chat.who)}</p>`:'')+(!transactionContext&&chat.example?.description?`<p><strong>Example:</strong> ${esc(chat.example.description)}</p>`:'')+(current?`<p><strong>Transaction values:</strong> ${esc(current.who)} · WHY: ${esc(snapshot.catalog.why.find(x=>x.id===current.why_id)?.name||'')} · WHOM: ${esc(snapshot.catalog.whom.find(x=>x.id===current.whom_id)?.name||'')}</p><p class="muted">Explain when to use these values.</p>`:'');
 const back=new URLSearchParams(location.search).get('return_to');$('flow-example-return').hidden=true;if(back){const url=new URL(back,location.origin);if(url.origin===location.origin&&url.pathname==='/bank/review'){$('flow-example-return').href=url.href;$('flow-example-return').hidden=false;}}
 const composerSave=hasPhotoSave();
 $('profile-save').hidden=!composerSave;$('profile-save').disabled=busy;
 $('profile-save-scope').hidden=!composerSave;$('profile-save-hint').hidden=!composerSave;
 const currentOption=document.querySelector('[name="profile-scope"]:not([value="ALL"])');currentOption.value=chat.transaction_id?'CURRENT':'FUTURE';
 $('profile-current-label').textContent=chat.transaction_id?'Save and apply to the current record':'Save for future records';
 document.querySelectorAll('[name="profile-scope"]').forEach(r=>{r.checked=r.value===photoScope;r.disabled=busy;});
 $('chat-input').placeholder=chat.kind==='PHOTO'?'Explain when to use the selected WHY and WHAT':'Describe the format and where WHO begins and ends';
 $('chat-confirmation').hidden=!!preview||composerSave||(!chat.ready&&chat.kind!=='EXTRACTOR');$('save-draft').hidden=chat.kind!=='EXTRACTOR';$('save-draft').disabled=busy;$('preview').disabled=busy||(!chat.ready&&chat.kind!=='EXTRACTOR');$('preview-results').hidden=!preview;$('chat-form').hidden=!!preview;
 $('catalog-proposals').innerHTML=(chat.new_catalog||[]).map((p,i)=>`<p>Suggested new ${esc(p.kind)}: <strong>${esc(p.name)}</strong> <button type="button" class="btn-secondary" data-create-catalog="${i}">Review and create</button></p>`).join('');
 document.querySelectorAll('[data-create-catalog]').forEach(b=>b.onclick=()=>openCatalog(chat.new_catalog[Number(b.dataset.createCatalog)]));
}
function saveBlocked(action){return !!preview?.used||(action!=='FUTURE'&&preview?.can_apply===false);}
function pending(value,message){busy=value;$('profile-save').disabled=value;document.querySelectorAll('[name="profile-scope"]').forEach(r=>r.disabled=value);$('profile-research').disabled=value;$('research-use').disabled=value;$('delete-current-rule').disabled=value;$('chat-send').disabled=value;$('preview').disabled=value||(!chat?.ready&&chat?.kind!=='EXTRACTOR');$('save-draft').disabled=value;$('chat-input').disabled=value;document.querySelectorAll('[data-save]').forEach(b=>b.disabled=value||saveBlocked(b.dataset.save));document.querySelectorAll('#transaction-whom').forEach(b=>b.disabled=value);status(message);}
async function researchProfile(mode='profile'){
 if(busy||!chat||chat.kind!=='PHOTO')return;pending(true,'Researching WHO and catalog choices…');
 try{chat=await api(`/bank/flow/conversation/${chat.id}/research`,{mode});preview=null;renderChat();status(chat.research?.verified?'Review the proposal and choose the catalog entries.':'Choose WHO, WHY and WHAT from the available lists.');}
 catch(error){status(error.message);}finally{pending(false,$('chat-status').textContent);}
}
$('profile-research').onclick=()=>researchProfile(new URLSearchParams(location.search).get('research')==='1'?'transaction':'profile');
$('research-choices').onsubmit=async event=>{
 event.preventDefault();if(busy||!chat)return;const selected=id=>Array.from($(id).selectedOptions).map(x=>Number(x.value));
 pending(true,'Preparing profile…');try{chat=await api(`/bank/flow/conversation/${chat.id}/research/choices`,{who:$('research-who').value,why_ids:JSON.stringify(selected('research-why')),what_ids:JSON.stringify(selected('research-what'))});preview=null;renderChat();status(chat.ready?'Preview the real transactions before saving.':'Explain when each selected WHY and WHAT applies in the chat.');}
 catch(error){status(error.message);}finally{pending(false,$('chat-status').textContent);}
};
document.querySelectorAll('[name="profile-scope"]').forEach(r=>r.onchange=()=>{photoScope=r.value;});
function researchChoicesChanged(values){
 const old=chat.research_choices;
 const same=(a,b)=>JSON.stringify([...a].sort((x,y)=>x-y))===JSON.stringify([...b].sort((x,y)=>x-y));
 return !old||values.who.trim().toUpperCase()!==(chat.who||'').trim().toUpperCase()||!same(values.why_ids,old.why_ids)||!same(values.what_ids,old.what_ids);
}
async function incorporateMessage(message){
 if(!message)return;
 chat=await api(`/bank/flow/conversation/${chat.id}`,{message});$('chat-input').value='';
}
async function incorporateChoices(){
 if(!chat.research)return;
 const values={who:$('research-who').value,why_ids:Array.from($('research-why').selectedOptions).map(x=>Number(x.value)),what_ids:Array.from($('research-what').selectedOptions).map(x=>Number(x.value))};
 if(values.who.trim()&&values.why_ids.length&&researchChoicesChanged(values))chat=await api(`/bank/flow/conversation/${chat.id}/research/choices`,{who:values.who,why_ids:JSON.stringify(values.why_ids),what_ids:JSON.stringify(values.what_ids)});
}
async function previewProfile(scope){
 preview=await api(`/bank/flow/conversation/${chat.id}/preview`,{scope,current_whom_id:currentWhom});
 chat=await api(`/bank/flow/conversation/${chat.id}`);renderChat();renderPreview();
 status(preview.can_apply===false&&scope!=='FUTURE'?preview.blocking_reason:'Review the preview, then confirm save and apply.');
 $('preview-results').scrollIntoView({block:'start'});
}
$('profile-save').onclick=async()=>{
 if(busy||!hasPhotoSave())return;
 const message=$('chat-input').value.trim(),scope=photoScope;
 const values={who:$('research-who').value,why_ids:Array.from($('research-why').selectedOptions).map(x=>Number(x.value)),what_ids:Array.from($('research-what').selectedOptions).map(x=>Number(x.value))};
 pending(true,'Preparing your instructions and preview…');preview=null;
 try{
  if(chat.research&&researchChoicesChanged(values))chat=await api(`/bank/flow/conversation/${chat.id}/research/choices`,{who:values.who,why_ids:JSON.stringify(values.why_ids),what_ids:JSON.stringify(values.what_ids)});
  await incorporateMessage(message);renderChat();
  if(!chat.ready){status('Answer the question in chat before saving. Your instructions are kept.');$('chat-input').focus();return;}
  await previewProfile(scope);
 }catch(error){renderChat();status(error.message);}finally{pending(false,$('chat-status').textContent);}
};
$('chat-form').onsubmit=async event=>{
 event.preventDefault();if(busy||!chat)return;const message=$('chat-input').value.trim();if(!message)return;
 pending(true,'Clarifying the instructions…');preview=null;
 try{await incorporateChoices();await incorporateMessage(message);renderChat();}
 catch(error){status(error.message);}finally{pending(false,$('chat-status').textContent==='Clarifying the instructions…'?'':$('chat-status').textContent);$('chat-input').focus();}
};
$('save-draft').onclick=async()=>{
 if(busy||!chat||chat.kind!=='EXTRACTOR')return;
 pending(true,'Saving…');
 try{chat=await api(`/bank/flow/conversation/${chat.id}/draft`,{pending_message:$('chat-input').value});preview=null;renderChat();await refresh();status('Draft saved. Active rule unchanged.');}
 catch(error){status(error.message);}finally{pending(false,$('chat-status').textContent);}
};
$('rule-target-select').onchange=async()=>{const id=$('rule-target-select').value;if(!id||busy)return;pending(true,'Selecting rule…');try{chat=await api(`/bank/flow/conversation/${chat.id}/target`,{rule_id:id});preview=null;renderChat();status('Existing rule selected. Save the draft, then preview.');}catch(error){status(error.message);}finally{pending(false,$('chat-status').textContent);}};
$('delete-current-rule').onclick=()=>{if(!busy&&chat)manage(chat.rule_id?'rule':'draft',chat.rule_id||chat.id,'delete');};
function editRule(){if(busy)return;preview=null;renderChat();status('');$('chat-input').focus();}
$('preview').onclick=async()=>{
 if(busy||!chat)return;
 if(chat.kind!=='EXTRACTOR'&&$('chat-input').value.trim()){status('Send your message first.');return;}
 pending(true,'Checking real transactions. No changes are being made…');
 try{preview=await api(`/bank/flow/conversation/${chat.id}/preview`,{});chat=await api(`/bank/flow/conversation/${chat.id}`);renderChat();renderPreview();status('Review the results, then choose where to apply.');}
 catch(error){status(error.message);}finally{pending(false,$('chat-status').textContent);}
};
function highlightedDescription(row){
 const parts=row.who_highlight;
 if(!parts||!parts.who||[parts.before,parts.who,parts.after].some(x=>typeof x!=='string')||parts.before+parts.who+parts.after!==row.description)return esc(row.description);
 return esc(parts.before)+'<mark class="who-highlight" title="Extracted WHO">'+esc(parts.who)+'</mark>'+esc(parts.after);
}
function previewWho(row){return (row.who_highlight?.who||row.extracted_who||'').trim().toUpperCase();}
async function openPreviewPhoto(row){
 if(busy||parentEditor||!preview)return;
 const parent={chat,preview,transactionContext,scrollTop:$('flow-chat-body').scrollTop,rowId:row.transaction_id};
 pending(true,'Opening recognition profile…');
 try{
  const photo=await api('/bank/flow/conversation',{kind:'PHOTO',transaction_id:row.transaction_id,parent_preview_id:preview.id});
  const context=await loadTransactionContext(photo);parentEditor=parent;chat=photo;transactionContext=context;preview=null;$('chat-input').value='';renderChat();focusEditorStart();status('Define this profile, preview it, then save it to return to the list.');
 }catch(error){status(error.message);}finally{pending(false,$('chat-status').textContent);}
}
async function returnToExtractor(updated=false){
 const parent=parentEditor;if(!parent)return;
 chat=parent.chat;preview=parent.preview;transactionContext=parent.transactionContext;parentEditor=null;$('chat-input').value='';renderChat();renderPreview();
 if(updated){
  try{await refresh();preview=await api(`/bank/flow/conversation/${chat.id}/preview`,{});renderChat();renderPreview();status('Profile saved. Continue with the next transaction.');}
  catch(error){preview=null;renderChat();status('Profile saved. Refresh the rule preview: '+error.message);}
 }else status('Back to the extraction preview.');
 $('flow-chat-body').scrollTop=parent.scrollTop;
 const rowButton=document.querySelector(`[data-photo-row="${parent.rowId}"]`);if(rowButton)rowButton.focus({preventScroll:true});
}
function renderPreview(){
 const p=preview;if(!p)return;const extraction=chat.kind==='EXTRACTOR';$('preview-results').hidden=false;$('chat-form').hidden=true;$('chat-confirmation').hidden=true;
 $('preview-results').innerHTML=`<h3>Preview on real transactions${extraction?` · ${p.source==='rule'?'Current rule':'Draft'}`:''}</h3>${extraction&&p.definition_text?`<p class="muted">${esc(p.definition_text)}</p>`:''}${extraction?'':'<button type="button" id="edit-preview-instructions" class="text-button">Edit instructions</button>'}<p>${p.matched} matching · ${p.reconcilable} ready to apply${p.matched>p.reconcilable?` · ${p.matched-p.reconcilable} need your input`:""}.</p><div class="table-scroll"><table><thead><tr><th>Transaction</th><th>Extracted WHO</th><th>Before</th><th>After</th><th>Result</th>${extraction?'<th>Photo</th>':''}</tr></thead><tbody>${p.rows.map(r=>`<tr><td>${esc(r.date)}<br>${highlightedDescription(r)}</td><td>${esc(r.extracted_who||(r.who_highlight?.uncertain?'Check highlighted name':'Not extracted'))}</td><td>${esc(['WHO: '+(r.before?.who||'—'),'WHY: '+(r.before?.why||'—'),'WHOM: '+(r.before?.whom||'—')].join('\n'))}</td><td>${esc(r.after?['WHO: '+r.after.who,'WHY: '+r.after.why,'WHAT: '+(r.after.what||'—'),'WHOM: '+(r.after.whom||'Choose above')].join('\n'):'No assignment')}</td><td>${esc(r.choice?(r.choice.review_before_confirm?'Ready to apply · confirmation required':'Ready to reconcile'):(r.missing_fields?.includes('WHOM')?'Choose WHOM above':'Needs review'))}<br>${esc(r.note)}</td>${extraction?`<td><button type="button" class="btn-secondary" data-photo-row="${r.transaction_id}" ${previewWho(r)&&!r.who_highlight?.uncertain?'':'disabled'}>Photo</button>${reviewedPhotos.has(previewWho(r))?'<small style="display:block;margin-top:4px">Saved</small>':''}</td>`:''}</tr>`).join('')}</tbody></table></div>${parentEditor?'<p>Save this profile to return to the transaction list. Existing transactions stay unchanged until you apply the extraction rule.</p><button data-save="FUTURE">Save profile</button>':saveChoices()}`;
 const editInstructions=$('edit-preview-instructions');if(editInstructions)editInstructions.onclick=editRule;
 document.querySelectorAll('[data-photo-row]').forEach(b=>b.onclick=()=>openPreviewPhoto(p.rows.find(r=>String(r.transaction_id)===b.dataset.photoRow)));
 bindSaveChoices();
}
function saveChoices(){if(preview?.scope){const scope=preview.scope,label=scope==='CURRENT'?'Current record only':scope==='ALL'?'All matching repository records still to reconcile':'Future records only';return `<p><strong>${label}</strong> · Confirmation also saves this profile for future imports. Applied changes can be rolled back.</p><div class="flow-actions"><button type="button" data-save="${scope}">${scope==='FUTURE'?'Confirm save':'Confirm save and apply'}</button><button type="button" id="edit-rule" class="btn-secondary">Edit</button></div>`;}if(chat?.run_id)return '<p>Save updates this profile for future imports and reconciles only this transaction. Rollback is available in reconciliation history.</p><button type="button" data-save="CURRENT">Save profile and reconcile this transaction</button> <button type="button" id="edit-rule" class="btn-secondary">Edit</button>';return '<p>Save publishes this version for future imports. Save and apply to repository also updates existing transactions. Applied changes can be rolled back without overwriting later edits.</p><div class="flow-actions"><button type="button" data-save="FUTURE">'+(chat?.kind==='PHOTO'?'Save for future':'Save')+'</button><button type="button" data-save="ALL">Save and apply to repository</button><button type="button" id="edit-rule" class="btn-secondary">Edit</button></div>';}

function bindSaveChoices(){const edit=$('edit-rule');if(edit)edit.onclick=editRule;document.querySelectorAll('[data-save]').forEach(b=>{b.disabled=busy||saveBlocked(b.dataset.save);b.onclick=()=>save(b.dataset.save);});}

async function save(action){
 if(busy||!preview||saveBlocked(action))return;
 if(chat.kind!=='EXTRACTOR'&&$('chat-input').value.trim()){status('Send your message first.');return;}
 pending(true,action==='FUTURE'?'Saving for future imports…':'Applying preview results…');
 try{const result=await api(`/bank/flow/conversation/${chat.id}/save`,{preview_id:preview.id,action});if(chat.run_id){preview.used=true;window.parent.postMessage({type:'bank-profile-saved',transactionId:chat.transaction_id,runId:chat.run_id,ruleId:result.rule_id},location.origin);status('Profile saved and transaction reconciled.');return;}if(parentEditor){reviewedPhotos.add((chat.who||'').trim().toUpperCase());await returnToExtractor(true);return;}preview=null;chat=await api(`/bank/flow/conversation/${chat.id}`);renderChat();await refresh();if(scanId)await pollScan();if((chat.research_choices||chat.run_id)&&chat.transaction_id){if(window.parent!==window){window.parent.postMessage({type:'bank-profile-saved',transactionId:chat.transaction_id,ruleId:result.rule_id,runId:chat.run_id},location.origin);}else{const back=new URLSearchParams(location.search).get('return_to');if(back){const u=new URL(back,location.origin);if(u.origin===location.origin&&u.pathname==='/bank/review')location.assign(u.href);}}}status(action==='ALL'||action==='CURRENT'?`${result.updated} transactions updated. Profile saved. Rollback is available in history.`:'Rule saved and active for future imports.');}
 catch(error){preview=null;renderChat();status(error.message);}finally{pending(false,$('chat-status').textContent);}
}
$('discover').onclick=async()=>{
 $('discover').disabled=true;$('discovery-status').textContent='Looking for recurring formats across all transactions…';
 try{const result=await api('/bank/flow/discover',{});scanId=result.id;sessionStorage.setItem('bank-format-scan',String(scanId));pollScan();}
 catch(error){$('discovery-status').textContent=error.message;$('discover').disabled=false;}
};
async function pollScan(){
 if(!scanId)return;
 try{const result=await api(`/bank/flow/discover/${scanId}`);const active=['QUEUED','RUNNING'].includes(result.status);
  $('discovery-status').textContent=active?`Search in progress: ${result.examined||0} transactions examined, ${result.processed||0} of ${result.groups||'…'} groups analyzed.`:`Search ${result.status==='COMPLETE'?'complete':result.status==='PARTIAL'?'partially complete':'incomplete'}: ${result.examined||0} transactions examined. ${(result.errors||[]).length?'Some groups could not be analyzed. Run the search again.':''} ${result.error||''}`;
  $('discovery-results').innerHTML=(result.formats||[]).map((p,i)=>`<div class="flow-item"><h3>${esc(p.title)}</h3><p>${esc(p.reply)}</p>${p.needs_clarification?'<p class="muted">One format · extraction variants to clarify in chat</p>':''}<button class="btn-secondary" data-discovery-index="${p.index??i}">Discuss and preview on real transactions</button></div>`).join('');
  document.querySelectorAll('[data-discovery-index]').forEach(b=>b.onclick=()=>openChat({scan_id:scanId,index:b.dataset.discoveryIndex,kind:'EXTRACTOR'}));
  $('discover').disabled=active;if(active)pollTimer=setTimeout(pollScan,4000);
 }catch(error){$('discovery-status').textContent=error.message;$('discover').disabled=false;}
}
function manage(kind,id,action){
 const item=kind==='draft'?chat:kind==='who'?snapshot.photos.find(p=>String(p.who_id)===String(id)):[...snapshot.rules,...snapshot.photos.flatMap(p=>p.rules)].find(r=>String(r.id)===String(id));if(!item)return;
 management={kind,id,action};$('manage-title').textContent=(action==='rename'?'Rename: ':'Delete: ')+(item.title||item.who);$('manage-name').value=item.title||item.who;$('manage-label').hidden=action==='delete';$('manage-name').required=action==='rename';
 $('manage-description').textContent=action==='rename'?'Change the name only.':kind==='draft'?'Discard this proposed format or draft?':kind==='who'?'Delete this profile, its knowledge and all its cases? Transactions and rollback history are retained.':'Delete this rule from automatic processing? Transactions and rollback history are retained.';
 $('manage-submit').textContent=action==='rename'?'Save name':'Delete permanently';$('manage-error').textContent='';$('manage-dialog').showModal();
}
$('manage-form').onsubmit=async event=>{
 event.preventDefault();if(!management)return;$('manage-submit').disabled=true;const {kind,id,action}=management;
 try{if(action==='rename'&&!$('manage-name').value.trim())throw Error('Enter a name.');
  if(kind==='rule')await api(`/bank/ai-rules/rules/${id}/${action==='rename'?'title':'delete'}`,{user_title:$('manage-name').value.trim(),response_format:'json'});
  else if(kind==='draft')await api(`/bank/flow/conversation/${id}/discard`,{});
  else await api(`/bank/flow/photos/${id}/manage`,{action,title:$('manage-name').value.trim()});
  preview=null;if(action==='delete'&&((kind==='rule'&&String(chat?.rule_id)===String(id))||(kind==='draft'&&String(chat?.id)===String(id)))){$('flow-chat').close();chat=null;}await refresh();$('manage-dialog').close();if(scanId)await pollScan();toast(action==='rename'?'Name updated.':'Entry deleted.');
 }catch(error){$('manage-error').textContent=error.message;}finally{$('manage-submit').disabled=false;}
};
$('history-open').onclick=async()=>{
 $('history-dialog').showModal();$('history-list').textContent='Loading history…';
 try{const result=await api('/bank/flow/history');$('history-list').innerHTML=result.applications.map(a=>`<div class="flow-item"><strong>${esc(a.title)}</strong><p>Application #${a.id} · ${a.updated} transactions updated${a.rolled_back_at?' · already rolled back':''}</p>${a.can_rollback?`<button class="btn-secondary" data-undo="${a.id}">Roll back this application</button>`:''}<p id="undo-${a.id}" role="status"></p></div>`).join('')||'<p>No applications recorded.</p>';
 document.querySelectorAll('[data-undo]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await api(`/bank/ai-rules/applications/${b.dataset.undo}/rollback`,{});$(`undo-${b.dataset.undo}`).textContent=`${r.restored} transactions restored; ${r.skipped.length} kept because they were changed later.`;await refresh();}catch(error){$(`undo-${b.dataset.undo}`).textContent=error.message;b.disabled=false;}});
 }catch(error){$('history-list').textContent=error.message;}
};
function openCatalog(proposal){catalogProposal=proposal;$('catalog-name').value=proposal.name;$('catalog-title').textContent=proposal.kind==='WHY'?'New WHY':'New WHOM';$('destination-label').hidden=proposal.kind!=='WHY';$('legal-label').hidden=proposal.kind!=='WHOM';$('catalog-legal').value='';$('catalog-explanation').textContent=proposal.kind==='WHOM'?'Without a legal name, this creates a virtual recipient. Enter a legal name only to create a new company.':'Choose an existing accounting destination or set it later.';$('catalog-destination').innerHTML='<option value="">To be defined</option>'+snapshot.catalog.destinations.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('');$('catalog-destination').value=proposal.accounting_classification_id||'';$('catalog-error').textContent='';$('catalog-dialog').showModal();}
$('catalog-form').onsubmit=async event=>{event.preventDefault();$('catalog-create').disabled=true;try{const result=await api('/bank/flow/catalog',{confirmed:'yes',kind:catalogProposal.kind,name:$('catalog-name').value,destination_id:$('catalog-destination').value,legal_name:$('catalog-legal').value});snapshot.catalog=result.catalog;$('catalog-dialog').close();toast('Entry created. Continue the chat to use it in the profile conditions.');$('chat-input').value=`I created ${catalogProposal.kind} "${$('catalog-name').value}". Use it in the agreed cases.`;$('chat-input').focus();}catch(error){$('catalog-error').textContent=error.message;}finally{$('catalog-create').disabled=false;}};
refresh().then(()=>{const params=new URLSearchParams(location.search);if(embedded)document.querySelector('.wrap').hidden=true;if(params.get('conversation_id'))return openChat({conversation_id:params.get('conversation_id')});if(params.get('embed')==='1')document.querySelector('.wrap').hidden=true;if(params.get('transaction_id'))return openChat({transaction_id:params.get('transaction_id'),kind:params.get('capture')==='1'?'PHOTO':'EXTRACTOR',run_id:params.get('run_id')||''}).then(()=>{if(params.get('research')==='1'&&!chat.research)return researchProfile(chat.run_id&&chat.who?'profile':'transaction');});if(params.get('rule_id'))return openChat({rule_id:params.get('rule_id')});const saved=sessionStorage.getItem('bank-format-scan');if(saved){scanId=Number(saved);pollScan();}}).catch(error=>toast('Unable to load Bank: '+error.message));
