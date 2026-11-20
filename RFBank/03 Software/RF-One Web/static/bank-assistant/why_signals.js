// WHY page, section 2 (BANK_WHO_WHY_MODE_001): recognised WHO whose WHY is not determinable, WHO WHY mode, WHO WHY rules.
// BANK_WHO_RECOGNISE_MODAL_001 (2026-11-05): the same file is the ONE WHO WHY rule editor elsewhere too. Without the WHY page
// (no #ws-rows) it only serves the editor dialog (`_bank_why_rule_dialog.html`), opened by window.BankWhyRuleEditor.open(ctx)
// with the context of the caller (WHO, movement, Source, owner); it reads the catalogs only, never runs the engine.
(()=>{
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>(v/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
async function api(path,data){const o={credentials:'same-origin',cache:'no-store'};if(data){const b=new URLSearchParams({csrf_token:document.querySelector('meta[name="bank-csrf"]').content});data.forEach(([k,v])=>b.append(k,v??''));o.method='POST';o.body=b;}
 const r=await fetch(path,o);const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
function toast(t){$('toast').textContent=t;$('toast').hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>$('toast').hidden=true,5000);}
const PAGE=!!$('ws-rows');
let D=null,reason='',simulated=false,editorCtx=null;
const ORDER=['WHO_SOURCE_CLASSIFICATION_MISSING','WHY_RULE_MISSING','WHY_DOCUMENT_MISSING','WHY_RULES_CONFLICT','WHY_SPLIT_INCOMPLETE'];
// The condition vocabulary of the WHY rules (why_patterns): field → operators and the kind of value.
const FIELDS={source:['Source',['is','is_not'],'source'],subject:['Accounting subject at the date (Source owner)',['is'],['Personal','Company']],
 source_type:['Source type',['is','is_not'],['card','bank account']],direction:['Direction',['is'],['money out','money in']],
 description:['Description',['contains','not_contains','starts_with'],'text'],amount:['Amount between',['between'],'range'],
 extra:['Source information (column)',['is','is_not','contains'],'extra']};
const OPS={is:'is',is_not:'is not',contains:'contains',not_contains:'does not contain',starts_with:'starts with',between:'between'};

function renderTiles(){
 $('ws-tiles').innerHTML=ORDER.map(c=>`<button type="button" class="ws-tile" data-reason="${c}" aria-pressed="${reason===c}"><strong>${D.counts[c]||0}</strong>${esc(D.labels[c])}</button>`).join('');
}
function action(g){
 if(g.action==='OPEN_SPLIT')return `<a class="btn-secondary" href="/bank/split?who=${g.who_id}">Open splits</a>`;
 if(g.action==='CONFIGURE_WHO')return `<button type="button" class="btn-secondary" data-who-edit="${g.who_id}">Edit WHO → WHY</button> <button type="button" class="btn-secondary" data-define="${g.key}">Define rule</button>`;
 if(g.action==='DEFINE_RULE')return `<button type="button" data-define="${g.key}">Define rule</button>`;
 if(g.action==='PROVIDE_DOCUMENT')return (g.missing.some(x=>/Amazon/i.test(x))?'<a class="btn-secondary" href="/bank/amazon">Amazon order report</a> ':'')+`<button type="button" class="btn-secondary" data-rules-of="${g.who_id}">Review rules</button>`;
 return `<button type="button" class="btn-secondary" data-rules-of="${g.who_id}">Review rules</button>`;
}
function renderGroups(){
 const q=$('ws-q').value.trim().toLowerCase();
 const rows=D.groups.filter(g=>(!reason||g.reason===reason)&&(!q||`${g.who} ${g.source}`.toLowerCase().includes(q)));
 $('ws-count').textContent=`${rows.reduce((s,g)=>s+g.count,0)} movements · ${rows.length} groups`;
 $('ws-rows').innerHTML=rows.length?rows.map(g=>`<tr><td>${esc(g.who)}<span class="ws-mode ${g.mode==='MULTIPLE'?'multiple':''}">${esc(g.mode)}</span></td>
  <td>${esc(g.source)}<br><small class="ws-muted">${esc(g.owner||'owner unknown')}</small></td>
  <td>${esc(g.label)}${g.missing.length?`<br><small class="ws-muted">${esc(g.missing.slice(0,3).join('; '))}</small>`:''}</td>
  <td class="num"><button type="button" class="btn-secondary" data-movements="${g.key}">${g.count}</button></td><td class="num">${money(g.total_minor)}</td>
  <td class="ws-actions">${action(g)}</td></tr>`).join(''):'<tr><td colspan="6" class="ws-muted">Nothing to determine here.</td></tr>';
}
function renderRules(filterWho){
 const rules=D.rules.filter(r=>!filterWho||r.who_ids.includes(filterWho));
 $('ws-rules-count').textContent=D.rules.length;
 $('ws-rules').innerHTML=rules.length?rules.map(r=>`<tr><td>${esc(r.text)}</td><td>${esc(r.status)}</td><td>${esc(r.created_at)}</td>
  <td><button type="button" class="btn-secondary" data-state="${r.id}" data-action="${r.status==='ACTIVE'?'deactivate':'activate'}">${r.status==='ACTIVE'?'Deactivate':'Activate'}</button></td></tr>`).join('')
  :'<tr><td colspan="4" class="ws-muted">No WHO WHY rule'+(filterWho?' for this WHO':'')+'.</td></tr>';
}
function renderModes(){
 $('ws-modes-count').textContent=D.multiple.length;
 $('ws-modes').innerHTML=D.multiple.length?D.multiple.map(w=>`<li>${esc(w.name)} <button type="button" class="btn-secondary" data-unique="${w.id}">Back to UNIQUE</button></li>`).join(''):'<li class="ws-muted">No WHO is MULTIPLE.</li>';
 $('ws-mode-who').innerHTML=D.whos.map(w=>`<option value="${w.id}">${esc(w.name)}</option>`).join('');
}
async function load(refresh){
 if(!PAGE){D=await api('/bank/why-signals/editor-data');return;}
 D=await api('/bank/why-signals/data'+(refresh?'?refresh=1':''));
 D.groups.forEach((g,i)=>g.key=i);
 renderTiles();renderGroups();renderRules();renderModes();
}

function showMovements(g){
 $('ws-movements-h').textContent=`${g.who} · ${g.source}`;
 $('ws-movements-note').textContent=`${g.label} — ${g.count} movement(s). WHO is ${g.mode}.`;
 $('ws-movements-rows').innerHTML=g.movements.map(mv=>`<tr><td>${esc(mv.date)}</td><td><a href="/bank/split/${mv.id}" title="Split of this movement">${esc(mv.description)}</a></td><td class="num">${money(mv.amount_minor)}</td><td><small>${esc(mv.detail||'')}</small></td></tr>`).join('');
 $('ws-movements').showModal();
}

// -- rule editor ---------------------------------------------------------------
function valueInput(kind,c){
 if(kind==='source')return `<select data-v>${D.sources.map(s=>`<option ${c&&c.value===s.name?'selected':''}>${esc(s.name)}</option>`).join('')}</select>`;
 if(Array.isArray(kind))return `<select data-v>${kind.map(v=>`<option ${c&&c.value===v?'selected':''}>${esc(v)}</option>`).join('')}</select>`;
 if(kind==='range')return `<span><input data-v type="number" step="0.01" min="0" placeholder="min" value="${c?c.value[0]/100:''}"> – <input data-v2 type="number" step="0.01" min="0" placeholder="max" value="${c?c.value[1]/100:''}"></span>`;
 if(kind==='extra')return `<span><input data-x placeholder="column, e.g. Memo" value="${esc(c?c.field.slice(6):'')}"> <input data-v placeholder="value" value="${esc(c?c.value:'')}"></span>`;
 return `<input data-v value="${esc(c?c.value:'')}">`;
}
function condRow(c){
 const key=c?(c.field.startsWith('extra:')?'extra':c.field):'source';
 const row=document.createElement('div');row.className='ws-cond';
 const draw=k=>{const [label,ops,kind]=FIELDS[k];
  row.innerHTML=`<label>Field<select data-f>${Object.entries(FIELDS).map(([f,[l]])=>`<option value="${f}" ${f===k?'selected':''}>${esc(l)}</option>`).join('')}</select></label>
   <label>Operator<select data-o>${ops.map(o=>`<option value="${o}" ${c&&c.op===o?'selected':''}>${OPS[o]}</option>`).join('')}</select></label>
   <label>Value${valueInput(kind,c&&key===k?c:null)}</label><button type="button" class="btn-secondary" data-remove aria-label="Remove condition">&times;</button>`;
  row.querySelector('[data-f]').onchange=e=>{c=null;draw(e.target.value);dirty();};};
 draw(key);$('ws-conds').appendChild(row);
}
function conditions(){
 return [...$('ws-conds').children].map(row=>{
  const f=row.querySelector('[data-f]').value,op=row.querySelector('[data-o]').value,v=row.querySelector('[data-v]').value.trim();
  if(f==='amount'){const a=Math.round(+v*100),b=Math.round(+row.querySelector('[data-v2]').value*100);return {field:'amount',op,value:[a,b]};}
  if(f==='extra'){const x=row.querySelector('[data-x]').value.trim().toLowerCase().replace(/[^a-z0-9]+/g,'_');return {field:'extra:'+x,op,value:v};}
  return {field:f,op,value:v};});
}
function spec(){
 const result=document.querySelector('input[name="ws-result"]:checked').value;
 return {who_ids:[...$('ws-rule-who').selectedOptions].map(o=>+o.value),conditions:conditions(),
  why_id:result==='why'?+$('ws-rule-why').value:null,document:result==='document'?$('ws-rule-doc').value:null};
}
function dirty(){simulated=false;$('ws-save-inactive').disabled=$('ws-save-active').disabled=true;}
function openRule(g,ctx){
 editorCtx=ctx||null;
 if($('ws-rule-context')){$('ws-rule-context').textContent=ctx&&ctx.context||'';$('ws-rule-context').hidden=!(ctx&&ctx.context);}
 if($('ws-rule-movements-box')){const mv=ctx&&ctx.movements||[];$('ws-rule-movements-box').hidden=!mv.length;$('ws-rule-movements-box').open=mv.length>0;
  $('ws-rule-movements-count').textContent=mv.length+(ctx&&ctx.movements_total>mv.length?' / '+ctx.movements_total:'');
  $('ws-rule-movements').innerHTML=mv.map(x=>`<tr><td>${esc(x.date)}</td><td translate="no">${esc(x.source||'—')}<br><small class="ws-muted">${esc(x.owner||'')}</small></td><td translate="no">${esc(x.description)}</td><td class="num">${money(x.amount_minor)}</td><td translate="no">${x.open?`<span class="ws-error">${esc(T('open'))}</span>`:esc(x.why||'—')}</td></tr>`).join('');}
 $('ws-rule-who').innerHTML=D.whos.map(w=>`<option value="${w.id}" ${g&&g.who_id===w.id?'selected':''}>${esc(w.name)}</option>`).join('');
 $('ws-rule-why').innerHTML=D.whys.map(y=>`<option value="${y.id}">${esc(y.name)} — ${esc(y.what)}</option>`).join('');
 $('ws-rule-doc').innerHTML=Object.entries(D.documents).map(([k,l])=>`<option value="${k}">${esc(l)}</option>`).join('');
 $('ws-conds').innerHTML='';condRow(g&&g.source?{field:'source',op:'is',value:g.source}:null);
 $('ws-rule-error').textContent='';$('ws-sim').hidden=true;dirty();
 $('ws-rule').showModal();
 const sel=$('ws-rule-who').selectedOptions[0];if(sel)sel.scrollIntoView({block:'nearest'});
}
async function simulate(){
 $('ws-rule-error').textContent='';$('ws-simulate').disabled=true;$('ws-simulate').textContent='Simulating…';
 try{
  const r=await api('/bank/why-signals/simulate',[['spec',JSON.stringify(spec())]]);
  const s=r.summary;
  $('ws-sim-text').textContent=r.text;
  $('ws-sim-summary').innerHTML=[['new_why','new WHY'],['changed_why','different WHY'],['unchanged','unchanged'],['still_open','still open'],['protected','human, protected']]
   .map(([k,l])=>`<span><strong>${s[k]}</strong> ${l}</span>`).join('')+`<span class="ws-muted">of ${r.movements} movement(s) of this WHO</span>`;
  $('ws-sim-rows').innerHTML=r.rows.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.source)}</td><td>${esc(x.description)}</td><td class="num">${money(x.amount_minor)}</td>
   <td>${esc(x.rule)}${x.missing.length?`<br><small class="ws-muted">${esc(x.missing.join('; '))}</small>`:''}</td><td>${esc(x.before||'—')}</td><td>${esc(x.after||x.open_label||'—')}</td></tr>`).join('');
  $('ws-sim').hidden=false;simulated=true;$('ws-save-inactive').disabled=$('ws-save-active').disabled=false;
 }catch(e){$('ws-rule-error').textContent=e.message;}
 finally{$('ws-simulate').disabled=false;$('ws-simulate').textContent='Simulate';}
}
async function save(active){
 if(!simulated){$('ws-rule-error').textContent='Simulate the rule first.';return;}
 if(active&&!confirm('Activate this rule? The engine will use it on its next run; movements confirmed by a person stay protected.'))return;
 try{const r=await api('/bank/why-signals/rules',[['spec',JSON.stringify(spec())],['simulated','yes'],['active',active?'yes':'']]);
  const c=editorCtx;$('ws-rule').close();toast(`Rule #${r.id} saved (${r.status}).`);if(PAGE)await load(true);if(c&&c.onSaved)c.onSaved(r);}
 catch(e){$('ws-rule-error').textContent=e.message;}
}

document.addEventListener('click',async e=>{
 const t=e.target;
 const c=t.closest('[data-cancel]');if(c){$(c.dataset.cancel).close();return;}
 const tile=t.closest('[data-reason]');if(tile){reason=reason===tile.dataset.reason?'':tile.dataset.reason;renderTiles();renderGroups();return;}
 const mv=t.closest('[data-movements]');if(mv){showMovements(D.groups[+mv.dataset.movements]);return;}
 const def=t.closest('[data-define]');if(def){openRule(D.groups[+def.dataset.define]);return;}
 const of=t.closest('[data-rules-of]');if(of){renderRules(+of.dataset.rulesOf);$('ws-rules-h').scrollIntoView({behavior:'smooth'});return;}
 if(t.closest('[data-remove]')){t.closest('.ws-cond').remove();dirty();return;}
 const st=t.closest('[data-state]');if(st){try{await api(`/bank/why-signals/rules/${st.dataset.state}/${st.dataset.action}`,[]);toast('Rule updated.');await load(true);}catch(x){toast(x.message);}return;}
 const un=t.closest('[data-unique]');if(un){try{await api('/bank/why-signals/mode',[['who_id',un.dataset.unique],['mode','UNIQUE']]);toast('WHO set back to UNIQUE.');await load(true);}catch(x){toast(x.message);}}
});
$('ws-rule').addEventListener('close',()=>{const c=editorCtx;editorCtx=null;if(c&&c.onClose)c.onClose();});
window.BankWhyRuleEditor={open:async ctx=>{await load();openRule({who_id:ctx.who_id,source:ctx.source},ctx);}};
$('ws-rule').addEventListener('input',dirty);$('ws-rule').addEventListener('change',e=>{if(!e.target.closest('[data-f]'))dirty();});
if(PAGE){$('ws-q').oninput=renderGroups;$('ws-refresh').onclick=()=>load(true).catch(e=>toast(e.message));
$('ws-new-rule').onclick=()=>openRule(null);}$('ws-add-cond').onclick=()=>{condRow(null);dirty();};
$('ws-simulate').onclick=simulate;$('ws-save-inactive').onclick=()=>save(false);$('ws-save-active').onclick=()=>save(true);
if(PAGE)$('ws-mode-save').onclick=async()=>{$('ws-mode-error').textContent='';
 try{await api('/bank/why-signals/mode',[['who_id',$('ws-mode-who').value],['mode',$('ws-mode-value').value],['note',$('ws-mode-note').value]]);
  toast('WHO WHY mode saved.');await load(true);}catch(e){$('ws-mode-error').textContent=e.message;}};
if(PAGE)load().catch(e=>{$('ws-rows').innerHTML=`<tr><td colspan="6" class="ws-error">${esc(e.message)}</td></tr>`;});

// -- WHO → WHY configuration (BANK_WHO_WHY_CONFIG_001, 2026-11-06) --------------------------------------------------
// One configuration per WHO, whatever the account or card: single WHY, Personal / Company WHY (from the owner at the
// movement date) or From rule (MULTIPLE), plus company exceptions. Simulate (read-only, the engine's evaluation of the
// WHO's movements before/after) and only then Save, with an explicit confirmation. WHAT is shown, never chosen.
let W=null,wcSimulated=false,wcCtx=null;
const T=v=>(window.rfT?window.rfT(v):v);
const REPLACES={SINGLE:'SINGLE',BY_SUBJECT:'COMPANY',RULE:'RULE'};
const REPLACES_LABEL={SINGLE:'Single WHY',COMPANY:'Company WHY',RULE:'From rule'};
const num=v=>v===''||v==null?null:+v;
function whatOf(id){const y=W.whys.find(x=>x.id===+id);return y?y.what:'—';}
function whySelect(sel,current,blank){sel.setAttribute('translate','no');
 sel.innerHTML=(blank?'<option value="">—</option>':'')+W.whys.map(y=>`<option value="${y.id}" ${y.id===current?'selected':''}>${esc(y.name)}</option>`).join('');}
function wcBehaviour(){const r=document.querySelector('input[name="wc-behaviour"]:checked');return r?r.value:null;}
function wcShow(){const b=wcBehaviour();
 $('wc-single').hidden=b!=='SINGLE';$('wc-subject').hidden=b!=='BY_SUBJECT';$('wc-rule').hidden=b!=='RULE';
 $('wc-replaces').textContent=b?T(REPLACES_LABEL[REPLACES[b]]):'—';
 [['why','wc-why-what'],['personal','wc-personal-what'],['company','wc-company-what']].forEach(([k,w])=>{$(w).textContent=$('wc-'+k).value?whatOf($('wc-'+k).value):'—';});
 [...$('wc-exc-rows').children].forEach(tr=>{tr.querySelector('[data-x-what]').textContent=whatOf(tr.querySelector('[data-x-why]').value);});
 $('wc-exc-count').textContent=$('wc-exc-rows').children.length;}
function excRow(x){const tr=document.createElement('tr');
 tr.innerHTML=`<td><select data-x-entity translate="no">${W.companies.map(c=>`<option value="${c.id}" ${x&&x.entity_id===c.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></td>
  <td><select data-x-why></select></td><td><small data-x-what translate="no">—</small></td>
  <td><select data-x-whom><option value="">${esc(T('Owner of the account or card'))}</option>${W.entities.map(e=>`<option value="${e.id}" translate="no" ${x&&x.whom_id===e.id?'selected':''}>${esc(e.name)}</option>`).join('')}</select>
   ${x&&!x.applies?`<br><small class="ws-error"><span>${esc(T('Saved as replacing'))}</span>: <span>${esc(T(REPLACES_LABEL[x.replaces]))}</span></small>`:''}</td>
  <td><button type="button" class="btn-secondary" data-x-remove aria-label="${esc(T('Remove exception'))}">&times;</button></td>`;
 whySelect(tr.querySelector('[data-x-why]'),x?x.why_id:null,false);$('wc-exc-rows').appendChild(tr);}
function wcDraft(){const b=wcBehaviour();
 return {who_id:W.who_id,behaviour:b,why_id:b==='SINGLE'?num($('wc-why').value):null,
  personal_why_id:b==='BY_SUBJECT'?num($('wc-personal').value):null,company_why_id:b==='BY_SUBJECT'?num($('wc-company').value):null,
  exceptions:[...$('wc-exc-rows').children].map(tr=>({entity_id:num(tr.querySelector('[data-x-entity]').value),
   why_id:num(tr.querySelector('[data-x-why]').value),whom_id:num(tr.querySelector('[data-x-whom]').value)}))};}
function wcDirty(){wcSimulated=false;$('wc-save').disabled=true;$('wc-sim').hidden=true;wcShow();}
async function openWho(id,ctx){
 try{W=await api('/bank/why-signals/who/'+id);}catch(e){toast(e.message);return;}
 wcCtx=ctx||null;
 $('wc-context').hidden=!(ctx&&ctx.context);$('wc-context').textContent='';
 if(ctx&&ctx.context){const p=document.createElement('p');p.textContent=ctx.context;$('wc-context').appendChild(p);
  (ctx.differences||[]).forEach(d=>{const q=document.createElement('div');q.setAttribute('translate','no');
   q.textContent=`${d.owner}: ${d.whys.join(', ')}${d.sources&&d.sources.length?' ('+d.sources.join(', ')+')':''}`;$('wc-context').appendChild(q);});}
 $('wc-who').textContent=W.who;$('wc-error').textContent='';
 $('wc-conflict').hidden=!W.conflict;$('wc-conflict').textContent=W.conflict?T('To decide')+': '+W.conflict:'';
 const p=W.proposal,b=W.behaviour||(p&&p.behaviour)||null;
 $('wc-proposal').hidden=!(p&&!W.behaviour);$('wc-proposal').textContent=p&&!W.behaviour?T('Proposal from the former WHY per account or card: check it and save.'):'';
 document.querySelectorAll('input[name="wc-behaviour"]').forEach(r=>{r.checked=r.value===b;});
 const src=W.behaviour?W:(p||{});
 whySelect($('wc-why'),src.why_id,true);whySelect($('wc-personal'),src.personal_why_id,true);whySelect($('wc-company'),src.company_why_id,true);
 $('wc-rule-count').textContent=W.rules.filter(r=>r.status==='ACTIVE').length;
 $('wc-exc-rows').innerHTML='';W.exceptions.forEach(excRow);$('wc-exc-box').open=W.exceptions.length>0||!!(ctx&&ctx.focus==='exceptions');
 $('wc-pairs-box').hidden=!W.pairs.length;$('wc-pairs-box').open=!!W.conflict;$('wc-pairs-count').textContent=W.pairs.length;
 $('wc-pairs-rows').innerHTML=W.pairs.map(x=>`<tr><td translate="no">${esc(x.source)}</td><td translate="no">${esc(x.owner||T('owner unknown'))}</td><td translate="no">${esc(x.why||'—')}</td></tr>`).join('');
 wcDirty();$('wc-dialog').showModal();}
async function wcSimulate(){
 $('wc-error').textContent='';$('wc-simulate').disabled=true;$('wc-simulate').textContent=T('Simulating…');
 try{const r=await api('/bank/why-signals/who/simulate',[['draft',JSON.stringify(wcDraft())]]);const s=r.summary;
  $('wc-sim-summary').innerHTML=[['new_why','new WHY'],['changed_why','different WHY or WHOM'],['unchanged','unchanged'],['still_open','still open'],['protected','human, protected']]
   .map(([k,l])=>`<span><strong>${s[k]}</strong> <span>${esc(T(l))}</span></span>`).join('')+`<span class="ws-muted"><span>${esc(T('movements of this WHO'))}</span>: ${r.movements}</span>`;
  $('wc-sim-rows').innerHTML=r.rows.length?r.rows.map(x=>`<tr><td>${esc(x.date)}</td><td translate="no">${esc(x.source)}<br><small class="ws-muted">${esc(x.owner||T('owner unknown'))}</small></td><td translate="no">${esc(x.description)}</td><td class="num">${money(x.amount_minor)}</td>
   <td translate="no">${esc(x.before||'—')}</td><td translate="no">${esc(x.after||'—')}${!x.after&&x.open_label?`<br><small class="ws-muted">${esc(x.open_label)}</small>`:''}</td><td translate="no">${esc(x.whom_before||'—')}</td><td translate="no">${esc(x.whom_after||'—')}</td></tr>`).join('')
   :`<tr><td colspan="8" class="ws-muted">${esc(T('No movement of this WHO.'))}</td></tr>`;
  $('wc-sim').hidden=false;wcSimulated=true;$('wc-save').disabled=false;
 }catch(e){$('wc-error').textContent=e.message;}
 finally{$('wc-simulate').disabled=false;$('wc-simulate').textContent=T('Simulate');}}
async function wcSave(){
 if(!wcSimulated){$('wc-error').textContent=T('Simulate the change first.');return;}
 if(!confirm('Save this WHO configuration? The engine uses it on its next run: no movement is changed now, and movements confirmed by a person stay protected.'))return;
 try{await api('/bank/why-signals/who/save',[['draft',JSON.stringify(wcDraft())],['simulated','yes'],['confirmed','yes']]);
  const c=wcCtx;$('wc-dialog').close();toast(T('WHO configuration saved.'));if(c&&c.onSaved)c.onSaved();else location.reload();}
 catch(e){$('wc-error').textContent=e.message;}}
if($('wc-dialog')){
 $('wc-dialog').addEventListener('change',e=>{if(e.target.closest('#wc-exc-rows,#wc-single,#wc-subject')||e.target.name==='wc-behaviour')wcDirty();});
 $('wc-exc-add').onclick=()=>{if(!W.companies.length){$('wc-error').textContent=T('No company is configured.');return;}excRow(null);wcDirty();};
 $('wc-exc-rows').addEventListener('click',e=>{if(e.target.closest('[data-x-remove]')){e.target.closest('tr').remove();wcDirty();}});
 $('wc-simulate').onclick=wcSimulate;$('wc-save').onclick=wcSave;
 $('wc-define-rule').onclick=async()=>{try{if(!D)D=await api('/bank/why-signals/editor-data');}catch(e){$('wc-error').textContent=e.message;return;}
  openRule({who_id:W.who_id},{context:T('Rule for this WHO, opened from its WHO → WHY window.'),onSaved:async()=>{
   try{const v=await api('/bank/why-signals/who/'+W.who_id);W.rules=v.rules;$('wc-rule-count').textContent=v.rules.filter(r=>r.status==='ACTIVE').length;}catch(_){}}});};
 document.addEventListener('click',e=>{const b=e.target.closest('[data-who-edit]');if(b){e.preventDefault();openWho(+b.dataset.whoEdit);}});
 $('wc-dialog').addEventListener('close',()=>{const c=wcCtx;wcCtx=null;if(c&&c.onClose)c.onClose();});
 // BANK_WHO_WHY_UPLOAD_CHECK_001: opened from Carica e riconcilia with the context of the upload check.
 window.BankWhoConfig={open:(id,ctx)=>openWho(id,ctx)};
}
})();
