// Discover WHY Patterns (BANK_WHY_PATTERNS_001). Uses the page helpers of flow.js ($, esc, api, toast).
let whyScan=null,whyTimer=null,whyFilter='open',whyData=null;
const money=v=>v==null?'—':String(v);
const plural=(n,one,many)=>`${n} ${n===1?one:many}`;

function whyCheckList(title,items,empty){
 if(!items||!items.length)return empty?`<p class="muted">${esc(empty)}</p>`:'';
 return `<details><summary>${esc(title)} (${items.length})</summary><ul class="why-list">${items.map(i=>`<li><span>${esc(i.date)}</span> ${esc(i.description)} <strong>${esc(i.amount)}</strong> <small>${esc(i.source||'')}</small>${i.note?`<br><small>${esc(i.note)}</small>`:''}</li>`).join('')}</ul></details>`;
}
function whyLater(c){
 const l=c.later;if(!l)return '';
 if(c.later_found)return `<li>Later period: the same rule is also found using only data up to ${esc(l.cutoff)}. After that date it covers ${plural(l.after,'movement','movements')}: ${l.human_agree} agree with a human decision, ${l.human_disagree} disagree.</li>`;
 return `<li>Later period: this rule needs data after ${esc(l.cutoff)} to be found, so it cannot yet be checked on a later period.</li>`;
}
function whyOptional(c){
 const o=c.optional;if(!o)return '';
 if(!o.fields.length)return '<li>Uses only information that every Source supplies.</li>';
 return `<li>Uses optional Source information (${o.fields.map(esc).join(', ')}). If a Source stops supplying it, ${plural(o.without_optional_lost,'movement stays','movements stay')} undecided. No error.</li>`;
}
function whyProposal(p){
 const c=p.check,ba=c.before_after||{},cond=p.when||[],exc=p.unless||[];
 const badges=[`${plural(c.formats,'format','formats')} · ${plural(c.movements,'movement','movements')}`];
 if(c.formats>1)badges.push('Joins several formats');
 badges.push(p.basis==='evidence'?'Based on RF-One evidence':'Based on recurrence');
 const warn=c.counterexample_count||c.conflict_count||(c.overlaps||[]).length;
 const state=p.status==='PROPOSED'?'':`<p class="why-state">${p.status==='APPROVED'?'Approved: active rule #'+esc(p.rule_id):'Rejected'}${p.note?': '+esc(p.note):''}</p>`;
 return `<article class="flow-item why-proposal${warn?' why-warn':''}" id="why-p-${p.id}">
  <h3>WHY: ${esc(p.why)}</h3><p>${badges.map(b=>`<span class="badge">${esc(b)}</span>`).join(' ')}</p>
  <p><strong>When</strong></p><ul class="why-conditions">${cond.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>
  ${exc.length?`<p><strong>Except</strong></p><ul class="why-conditions">${exc.map(e=>`<li>${esc(e.text||'')} <small>${esc(e.note||'')}</small></li>`).join('')}</ul>`:''}
  <ul class="why-facts">
   <li>Amount covered: ${esc(c.amount)}</li>
   <li>What approving changes: ${ba['new WHY']||0} get a WHY for the first time · ${ba['unchanged']||0} already have this WHY${ba['agrees with the human decision']?` · ${ba['agrees with the human decision']} agree with a human decision`:''} · ${ba['different WHY today']||0} have a different WHY today${ba['protected (human decision kept)']?` · ${ba['protected (human decision kept)']} human decisions stay as they are`:''}</li>
   <li>Human counterexamples: <strong>${c.counterexample_count}</strong> · Conflicts with existing rules or profiles: <strong>${c.conflict_count}</strong> (each becomes an Exception for a person)</li>
   ${(c.overlaps||[]).map(o=>`<li>Overlaps “${esc(o.rule)}” (WHY ${esc(o.why)}) on ${plural(o.movements,'movement','movements')}</li>`).join('')}
   ${c.incomplete?`<li>${plural(c.incomplete,'movement','movements')} cannot be decided: information missing (${c.missing.map(esc).join('; ')})</li>`:''}
   ${whyLater(c)}${whyOptional(c)}
  </ul>
  ${whyCheckList('Human counterexamples',c.counterexamples)}${whyCheckList('Conflicts with existing rules or profiles',c.conflicts)}
  ${whyCheckList('Movements that would get a WHY for the first time',c.new)}${whyCheckList('Examples',c.examples)}
  <details><summary>Formats joined (${c.formats})</summary><p class="flow-chat-text">${(c.format_list||[]).map(esc).join(' · ')}</p></details>
  ${p.reply?`<p class="muted">AI: ${esc(p.reply)}</p>`:''}${state}
  ${p.status==='PROPOSED'?`<div class="flow-actions"><button data-why-approve="${p.id}">Approve…</button><button class="btn-secondary" data-why-discuss="${p.id}">Discuss with AI</button><button class="text-button delete-button" data-why-reject="${p.id}">Reject</button></div>
  <div class="why-confirm" id="why-confirm-${p.id}" hidden><p><strong>If you approve:</strong> the rule becomes active and the reconciliation engine applies it from its next run, without AI. ${ba['new WHY']||0} movements get the WHY ${esc(p.why)}. Human decisions are not changed. Any movement where a profile or another rule gives a different WHY becomes an Exception for a person. You can deactivate the rule at any time.</p><div class="flow-actions"><button data-why-confirm="${p.id}">Confirm approval</button><button class="btn-secondary" data-why-cancel="${p.id}">Cancel</button></div></div>
  <form class="why-discuss" id="why-discuss-${p.id}" hidden><label>What should change?<textarea rows="2" maxlength="1000" placeholder="E.g. exclude the payments to …, or this is not Food: it is …"></textarea></label><div class="flow-actions"><button>Send to AI</button></div></form>`:''}
  <p role="status" id="why-msg-${p.id}"></p></article>`;
}
function whyVisible(p){
 const c=p.check;
 if(whyFilter==='open')return p.status==='PROPOSED';
 if(whyFilter==='joined')return p.status==='PROPOSED'&&c.formats>1;
 if(whyFilter==='issues')return p.status==='PROPOSED'&&(c.counterexample_count||c.conflict_count||(c.overlaps||[]).length);
 if(whyFilter==='clean')return p.status==='PROPOSED'&&!(c.counterexample_count||c.conflict_count||(c.overlaps||[]).length);
 return p.status===whyFilter;
}
function whyRender(){
 const d=whyData;if(!d)return;
 const ps=d.proposals||[];
 const s=d.summary||{};
 $('why-summary').innerHTML=d.status==='COMPLETE'||d.status==='PARTIAL'?`<p>${plural(d.examined,'movement','movements')} read (${d.structural||0} card settlements and transfers are decided before any rule) · ${plural(d.formats,'description format','description formats')} · AI reading: ${plural(d.ai_calls,'batch','batches')}${d.errors?.length?` (${d.errors.length} not completed)`:''}.</p><p><strong>${plural(s.proposals||0,'proposed rule','proposed rules')}</strong>, ${s.consolidated||0} of which join several formats · ${s.covered||0} movements covered.</p>${d.domain&&!d.domain.available?`<p class="muted">RF-One domain data (Clover, Tips) not connected: ${esc(d.domain.reason)}. Rules needing that evidence stay undecided.</p>`:''}${d.domain?.payroll?`<p class="muted">Payroll evidence: ${esc(d.domain.payroll)}.</p>`:''}`:'';
 const counts={open:0,joined:0,issues:0,clean:0,APPROVED:0,REJECTED:0};
 for(const p of ps)for(const k of Object.keys(counts)){const f=whyFilter;whyFilter=k;if(whyVisible(p))counts[k]++;whyFilter=f;}
 const names={open:'To decide',joined:'Join several formats',issues:'With conflicts',clean:'Without conflicts',APPROVED:'Approved',REJECTED:'Rejected'};
 $('why-filters').hidden=!ps.length;
 $('why-filters').innerHTML=Object.keys(names).map(k=>`<button class="${k===whyFilter?'':'btn-secondary'}" data-why-filter="${k}">${names[k]} (${counts[k]})</button>`).join('');
 document.querySelectorAll('[data-why-filter]').forEach(b=>b.onclick=()=>{whyFilter=b.dataset.whyFilter;whyRender();});
 const shown=ps.filter(whyVisible).sort((a,b)=>b.check.movements-a.check.movements);
 $('why-proposals').innerHTML=shown.map(whyProposal).join('')||(ps.length?'<p class="muted">Nothing in this view.</p>':'');
 bindWhy();
}
function whyMsg(id,text){const n=$(`why-msg-${id}`);if(n)n.textContent=text;}
function bindWhy(){
 document.querySelectorAll('[data-why-approve]').forEach(b=>b.onclick=()=>{$(`why-confirm-${b.dataset.whyApprove}`).hidden=false;});
 document.querySelectorAll('[data-why-cancel]').forEach(b=>b.onclick=()=>{$(`why-confirm-${b.dataset.whyCancel}`).hidden=true;});
 document.querySelectorAll('[data-why-confirm]').forEach(b=>b.onclick=()=>whyAction(b.dataset.whyConfirm,'approve',{confirm:'yes'}));
 document.querySelectorAll('[data-why-reject]').forEach(b=>b.onclick=()=>whyAction(b.dataset.whyReject,'reject',{}));
 document.querySelectorAll('[data-why-discuss]').forEach(b=>b.onclick=()=>{const f=$(`why-discuss-${b.dataset.whyDiscuss}`);f.hidden=!f.hidden;if(!f.hidden)f.querySelector('textarea').focus();});
 document.querySelectorAll('form.why-discuss').forEach(f=>f.onsubmit=async e=>{e.preventDefault();const id=f.id.slice(12),text=f.querySelector('textarea').value.trim();if(!text)return;f.querySelector('button').disabled=true;whyMsg(id,'The AI is revising the proposal and RF-One is testing it again on the whole history…');
  try{const r=await api(`/bank/flow/why-discover/${whyScan}/proposals/${id}/discuss`,{message:text});whyData.proposals=whyData.proposals.map(p=>String(p.id)===id?r.proposal:p);whyRender();whyMsg(id,'Revised and tested again. Read the result before approving.');}
  catch(error){whyMsg(id,error.message);f.querySelector('button').disabled=false;}});
}
async function whyAction(id,action,data){
 whyMsg(id,action==='approve'?'Approving…':'Saving…');
 try{const r=await api(`/bank/flow/why-discover/${whyScan}/proposals/${id}/${action}`,data);whyData.proposals=whyData.proposals.map(p=>String(p.id)===String(id)?r.proposal:p);whyRender();await whyRules();toast(action==='approve'?'Rule approved. The reconciliation engine applies it on its next run.':'Proposal rejected.');}
 catch(error){whyMsg(id,error.message);}
}
async function whyPoll(){
 if(!whyScan)return;clearTimeout(whyTimer);
 try{const d=await api(`/bank/flow/why-discover/${whyScan}`);whyData=d;const active=['QUEUED','RUNNING'].includes(d.status);
  $('why-status').textContent=active?`Discovery in progress… ${d.step||''}`:d.status==='ERROR'?`Discovery not completed: ${d.error||''}`:d.status==='PARTIAL'?'Discovery partly completed: some formats could not be read by the AI. Run it again to complete them; formats already read are not asked again.':'Discovery complete.';
  $('why-discover').disabled=active;whyRender();if(active)whyTimer=setTimeout(whyPoll,4000);
 }catch(error){$('why-status').textContent=error.message;$('why-discover').disabled=false;}
}
async function whyRules(){
 try{const r=await api('/bank/flow/why-rules');$('why-rules-count').textContent=r.rules.filter(x=>x.status==='ACTIVE').length;
  $('why-rules-list').innerHTML=r.rules.map(x=>`<div class="flow-item"><h3>${esc(x.why)}</h3><p class="flow-chat-text">${esc(x.text)}</p><p><small>${x.status==='ACTIVE'?'Active':'Inactive'} · Version ${x.version} · approved ${esc(x.created_at)}${x.optional.length?' · uses optional Source information: '+x.optional.map(esc).join(', '):''}</small></p><div class="flow-actions"><button class="btn-secondary" data-why-rule="${x.id}" data-why-rule-action="${x.status==='ACTIVE'?'deactivate':'activate'}">${x.status==='ACTIVE'?'Deactivate':'Activate again'}</button></div></div>`).join('')||'<p class="muted">No approved WHY rule yet.</p>';
  document.querySelectorAll('[data-why-rule]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api(`/bank/flow/why-rules/${b.dataset.whyRule}/${b.dataset.whyRuleAction}`,{});await whyRules();toast('Rule updated. The reconciliation engine runs again.');}catch(error){toast(error.message);b.disabled=false;}});
 }catch(error){$('why-rules-list').textContent=error.message;}
}
$('why-discover').onclick=async()=>{
 $('why-discover').disabled=true;$('why-status').textContent='Starting the discovery…';
 try{const r=await api('/bank/flow/why-discover',{});whyScan=r.id;whyFilter='open';whyPoll();}
 catch(error){$('why-status').textContent=error.message;$('why-discover').disabled=false;}
};
(async()=>{await whyRules();try{const r=await api('/bank/flow/why-discover/latest');if(r.id){whyScan=r.id;whyPoll();}}catch(error){}})();
