// WHO Pattern Training (BANK_WHO_TRAINING_001). The person teaches; RF-One code builds and tests the rules.
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,data){const o={credentials:'same-origin',cache:'no-store'};if(data){o.method='POST';o.body=new URLSearchParams({csrf_token:document.querySelector('meta[name="bank-csrf"]').content,...data});}
 const r=await fetch(path,o);const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
function toast(t){$('toast').textContent=t;$('toast').hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>$('toast').hidden=true,5000);}
let D=null;const sel=new Set();let marks={who:new Set(),vars:new Set()},tokens=[],shownFocus=null;

function whoNow(r){
 if(r.example)return r.example.external?'<span class="badge">You: external knowledge</span>':`<span class="badge">You: ${esc(r.example.who)}</span>`;
 if(r.human_who)return `Human: ${esc(r.human_who)}`;
 if(r.rule_who)return `Rule: ${esc(r.rule_who)}`;
 return '<span class="muted">—</span>';
}
function shown(){
 const q=$('wt-q').value.trim().toLowerCase(),src=$('wt-source').value,min=parseFloat($('wt-min').value),max=parseFloat($('wt-max').value),from=$('wt-from').value,to=$('wt-to').value,st=$('wt-status').value;
 return D.movements.filter(r=>{
  if(q&&!(r.description.toLowerCase().includes(q)||(r.example?.who||r.human_who||r.rule_who||'').toLowerCase().includes(q)))return false;
  if(src&&String(r.source_id)!==src)return false;
  const a=r.amount_minor/100;if(!isNaN(min)&&a<min)return false;if(!isNaN(max)&&a>max)return false;
  if(from&&r.date<from)return false;if(to&&r.date>to)return false;
  if(st==='todo'&&(r.example||r.human_who||r.rule_who))return false;if(st==='mine'&&!r.example)return false;
  if(st==='human'&&!r.human_who)return false;if(st==='rule'&&!r.rule_who)return false;return true;});
}
function renderRows(){
 const rows=shown();$('wt-count').textContent=`${rows.length} of ${D.movements.length}`;
 $('wt-rows').innerHTML=rows.map(r=>`<tr><td><input type="checkbox" data-id="${r.id}" ${sel.has(r.id)?'checked':''} aria-label="Select movement ${r.id}"></td><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td>${whoNow(r)}</td></tr>`).join('');
 $('wt-rows').querySelectorAll('input[data-id]').forEach(c=>c.onchange=()=>{const id=+c.dataset.id;c.checked?sel.add(id):sel.delete(id);renderTeach();});
 $('wt-all').checked=rows.length>0&&rows.every(r=>sel.has(r.id));
}
function renderSummary(){
 const s=D.summary;
 $('wt-summary').innerHTML=`<table class="who-table"><tbody>
  <tr><td>Bank movements</td><td>${s.movements}</td></tr>
  <tr><td>WHO confirmed by you here</td><td>${s.confirmed} · of which ${s.single} only for those movements (not a rule)</td></tr>
  <tr><td>WHO decided by a person earlier in Bank</td><td>${s.human}</td></tr>
  <tr><td>Read by approved WHO rules (${D.approved_rules} rules)</td><td>${s.covered}</td></tr>
  <tr><td>With a known WHO (any of the above, each counted once)</td><td>${s.known}</td></tr>
  <tr><td>Still to examine</td><td><strong>${s.to_examine}</strong></td></tr>
  <tr><td>Rule proposals waiting for your decision (not counted above)</td><td>${s.proposals_pending}</td></tr></tbody></table>`;
}
function tokenize(text){const out=[];const re=/[A-Za-z0-9&'.]+|\s+|[^A-Za-z0-9\s]/g;let m;while((m=re.exec(text)))out.push({t:m[0],s:m.index,e:m.index+m[0].length,space:/^\s+$/.test(m[0])});return out;}
function renderDesc(){
 const id=+$('wt-focus').value,r=D.movements.find(x=>x.id===id);if(!r){$('wt-desc').textContent='';return;}
 $('wt-desc').innerHTML=tokens.map((k,i)=>k.space?esc(k.t).replace(/ /g,'&nbsp;'):`<span class="wt-tok${marks.who.has(i)?' wt-is-who':''}${marks.vars.has(i)?' wt-is-var':''}" data-tok="${i}">${esc(k.t)}</span>`).join('');
 $('wt-desc').querySelectorAll('[data-tok]').forEach(x=>x.onclick=()=>{const i=+x.dataset.tok,mode=document.querySelector('input[name=wt-mode]:checked').value,set=mode==='who'?marks.who:marks.vars;
  set.has(i)?set.delete(i):set.add(i);(mode==='who'?marks.vars:marks.who).delete(i);renderDesc();});
}
function focusChanged(){const r=D.movements.find(x=>x.id===+$('wt-focus').value);shownFocus=r?r.id:null;tokens=r?tokenize(r.description):[];marks={who:new Set(),vars:new Set()};
 if(r&&r.example&&r.example.span){tokens.forEach((k,i)=>{if(!k.space&&k.s>=r.example.span[0]&&k.e<=r.example.span[1])marks.who.add(i);if((r.example.variables||[]).some(v=>k.s>=v[0]&&k.e<=v[1]))marks.vars.add(i);});}
 renderDesc();}
function renderTeach(){
 $('wt-teach').hidden=!sel.size;$('wt-selected').textContent=sel.size;if(!sel.size)return;
 const chosen=D.movements.filter(r=>sel.has(r.id));const keep=$('wt-focus').value;
 $('wt-focus').innerHTML=chosen.map(r=>`<option value="${r.id}">${esc(r.date)} · ${esc(r.description.slice(0,80))}</option>`).join('');
 if(chosen.some(r=>String(r.id)===keep))$('wt-focus').value=keep;
 if(!$('wt-who').value){const w=chosen.find(r=>r.example?.who);if(w)$('wt-who').value=w.example.who;}
 // the marks stay while the same example is shown (a reload after Create WHO must not erase them)
 if(+$('wt-focus').value!==shownFocus)focusChanged();else renderDesc();
}
function span(){const who=[...marks.who].sort((a,b)=>a-b);if(!who.length)return null;return [tokens[who[0]].s,tokens[who[who.length-1]].e];}
async function load(){
 D=await api('/bank/who-training/data');
 $('wt-whos').innerHTML=D.whos.map(w=>`<option value="${esc(w)}">`).join('');
 const keepSrc=$('wt-source').value;$('wt-source').innerHTML='<option value="">All</option>'+D.sources.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');$('wt-source').value=keepSrc;
 renderSummary();renderRows();renderTeach();renderProposals();renderSingles();
}
function renderSingles(){
 const rows=D.movements.filter(r=>r.example&&(r.example.single||r.example.external));
 $('wt-singles').innerHTML=rows.length?`<div class="who-scroll"><table class="who-table"><thead><tr><th>Source</th><th>Date</th><th>Description</th><th>Amount</th><th>WHO</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td>${r.example.external?'Needs external knowledge'+(r.example.who?': '+esc(r.example.who):''):esc(r.example.who)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">None yet.</p>';
}
function renderProposals(){
 $('wt-proposals').innerHTML=(D.proposals||[]).slice().reverse().map(p=>{const c=p.check;return `<div class="flow-item" id="wt-p-${p.id}"><h3>${esc(p.text)}</h3>
  <p><span class="badge">${p.status==='PROPOSED'?'Waiting for your decision':p.status==='APPROVED'?'Approved: active rule #'+p.rule_id:'Rejected'}</span> Intercepts ${c.selected} movements: ${c.examples} of your examples (${c.examples_agree} read correctly${c.examples_disagree?`, <strong>${c.examples_disagree} read differently</strong>`:''}) and <strong>${c.additional} additional</strong>${c.approved_conflicts?` · ${c.approved_conflicts} read differently by an approved rule`:''}.</p>
  <details data-proposal="${p.id}"><summary>Show every intercepted movement</summary><p class="muted">Loading…</p></details></div>`;}).join('')||'<p class="muted">No proposal yet.</p>';
 document.querySelectorAll('[data-proposal]').forEach(d=>d.ontoggle=()=>{if(d.open)openProposal(+d.dataset.proposal,d);});
}
async function openProposal(pid,box){
 const p=(await api(`/bank/who-training/proposals/${pid}`)).proposal,c=p.check;const open=p.status==='PROPOSED';
 box.innerHTML=`<summary>Every intercepted movement (${c.selected})</summary>
  ${open?'<p class="muted">Tick the movements this rule must NOT intercept, then correct the rule.</p>':''}
  <div class="who-scroll"><table class="who-table"><thead><tr>${open?'<th>Exclude</th>':''}<th></th><th>Source</th><th>Date</th><th>Description</th><th>Amount</th><th>WHO read</th><th>Your WHO</th></tr></thead><tbody>
  ${c.rows.map(r=>`<tr class="${r.disagrees?'who-wrong':''}">${open?`<td>${r.example?'':`<input type="checkbox" data-exclude="${r.id}" aria-label="Exclude movement ${r.id}">`}</td>`:''}<td>${r.example?'<span class="badge">Your example</span>':'Additional'}</td><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td><strong>${esc(r.who)}</strong>${r.approved_who&&r.approved_who.toUpperCase()!==r.who.toUpperCase()?`<br><small>approved rule: ${esc(r.approved_who)}</small>`:''}</td><td>${esc(r.expected||'')}</td></tr>`).join('')}</tbody></table></div>
  ${open?`<div class="flow-actions"><button class="btn-secondary" data-act="exclude">Exclude the ticked and correct the rule</button><button data-act="approve">Approve…</button><button class="text-button delete-button" data-act="reject">Reject</button></div>
  <div class="why-confirm" data-confirm hidden><p><strong>If you approve:</strong> this rule becomes active and the reconciliation engine reads WHO with it on its next run, for the ${c.selected} movements above and future imports. No WHO you decided is changed; a more specific approved rule keeps precedence. You can deactivate it later.</p><div class="flow-actions"><button data-act="confirm">Confirm approval</button><button class="btn-secondary" data-act="cancel">Cancel</button></div></div>`:''}
  <p role="status" data-msg></p>`;
 const msg=t=>box.querySelector('[data-msg]').textContent=t;
 box.querySelectorAll('[data-act]').forEach(b=>b.onclick=async()=>{const a=b.dataset.act;
  if(a==='approve'){box.querySelector('[data-confirm]').hidden=false;return;}if(a==='cancel'){box.querySelector('[data-confirm]').hidden=true;return;}
  try{if(a==='exclude'){const ids=[...box.querySelectorAll('[data-exclude]:checked')].map(x=>x.dataset.exclude);const r=await api(`/bank/who-training/proposals/${pid}/exclude`,{ids:ids.join(',')});
    toast(`Rule corrected: not when the description contains ${r.words.join(', ')}. ${r.before} → ${r.after} movements${r.still_intercepted?` · ${r.still_intercepted} ticked still intercepted`:''}.`);}
   else{await api(`/bank/who-training/proposals/${pid}/${a==='confirm'?'approve':'reject'}`,{confirm:'yes'});toast(a==='confirm'?'Rule approved and active.':'Proposal rejected.');}
   await load();const d=document.querySelector(`[data-proposal="${pid}"]`);if(d){d.open=true;}}
  catch(e){msg(e.message);}});
}
$('wt-all').onchange=()=>{shown().forEach(r=>$('wt-all').checked?sel.add(r.id):sel.delete(r.id));renderRows();renderTeach();};
['wt-q','wt-source','wt-min','wt-max','wt-from','wt-to','wt-status'].forEach(id=>$(id).addEventListener('input',renderRows));
$('wt-focus').onchange=focusChanged;
$('wt-create').onclick=async()=>{const n=$('wt-who').value.trim();if(!n){$('wt-teach-status').textContent='Write the name of the new WHO first.';return;}
 try{const r=await api('/bank/who-training/who',{name:n});$('wt-who').value=r.who;await load();toast(`WHO “${r.who}” ready.`);}catch(e){$('wt-teach-status').textContent=e.message;}};
$('wt-save').onclick=async()=>{
 const ext=$('wt-external').checked;
 try{const r=await api('/bank/who-training/examples',{ids:[...sel].join(','),who:$('wt-who').value.trim(),external:ext?'yes':'',single:$('wt-single').checked?'yes':'',
   focus:$('wt-focus').value,span:JSON.stringify(ext?null:span()),variables:JSON.stringify([...marks.vars].map(i=>[tokens[i].s,tokens[i].e]))});
  $('wt-teach-status').textContent=`${r.saved} examples saved.`;await load();}catch(e){$('wt-teach-status').textContent=e.message;}};
$('wt-remove').onclick=async()=>{try{await api('/bank/who-training/examples/remove',{ids:[...sel].join(',')});$('wt-teach-status').textContent='Examples removed.';await load();}catch(e){$('wt-teach-status').textContent=e.message;}};
$('wt-propose').onclick=async()=>{$('wt-propose').disabled=true;try{const r=await api('/bank/who-training/propose',{});$('wt-propose-status').textContent=r.added?`${r.added} new proposals, tested on every movement.`:'No new proposal: mark the WHO on the description of at least one example, or the same rule is already proposed.';await load();}
 catch(e){$('wt-propose-status').textContent=e.message;}finally{$('wt-propose').disabled=false;}};
load().catch(e=>{$('wt-summary').textContent='Unable to load: '+e.message;});
