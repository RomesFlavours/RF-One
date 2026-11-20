// WHO Status, formerly WHO Search Text (BANK_WHO_SEARCH_TEXT_001; renamed BANK_SECTION_NAV_001, 2026-11-05). The text that recognises a WHO; then, if missing, its WHO-WHY-WHAT association.
// The recognition rules section above is flow.js (shared with Rules and profiles): this file is scoped so the two never collide.
(()=>{
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,data){const o={credentials:'same-origin',cache:'no-store'};if(data){const b=new URLSearchParams({csrf_token:document.querySelector('meta[name="bank-csrf"]').content});data.forEach(([k,v])=>b.append(k,v??''));o.method='POST';o.body=b;}
 const r=await fetch(path,o);const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
function toast(t){$('toast').textContent=t;$('toast').hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>$('toast').hidden=true,5000);}
let D=null,current=null;
const BY={RULE:'Rule',TEXT:'Name or alias',RULES_DISAGREE:'Rules disagree — review',TEXT_AMBIGUOUS:'Several WHO — review'};
const whoCell=r=>r.whos.length?r.whos.map(w=>esc(w)+(r.by==='RULE'&&!r.known?' <small class="st-null">not a WHO yet</small>':'')).join('<br>'):'<span class="st-null">null</span>';

function renderRows(){
 const q=$('st-q').value.trim().toLowerCase(),show=$('st-show').value;
 const rows=D.movements.filter(r=>(!show||(show==='null'?!r.by:show==='review'?(r.by==='RULES_DISAGREE'||r.by==='TEXT_AMBIGUOUS'):r.by===show))&&(!q||(r.description+' '+r.whos.join(' ')).toLowerCase().includes(q)));
 $('st-count').textContent=`${rows.length} of ${D.movements.length}`;
 $('st-rows').innerHTML=rows.map(r=>`<tr><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td>${whoCell(r)}</td><td>${esc(BY[r.by]||'')}</td><td style="white-space:nowrap"><button type="button" class="btn-secondary" data-ai-rule="${r.id}">+ AI Rule</button> <button type="button" class="btn-secondary" data-open="${r.id}">By Text</button></td></tr>`).join('');
}
// BANK-2026-11-04: layout only — Known WHO list; associated rules and "+ AI" have no data or behaviour yet.
function renderWhos(){
 $('known-count').textContent=String(D.whos.length);
 $('known-rows').innerHTML=D.whos.map(w=>`<tr><td>${esc(w.name)}</td><td><span class="st-null">—</span></td><td><button type="button" class="btn-secondary" data-known-ai="${w.id}">+ AI</button></td></tr>`).join('');
}
async function load(){D=await api('/bank/who-search-text/data');renderRows();renderWhos();}

// -- Riconosci WHO (BANK_WHO_RECOGNISE_MODAL_001, 2026-11-05) -------------------------------------------------
// One movement -> a SPECIFIC or GENERIC WHO and the text that recognises the next movements. The AI suggests only on
// request and writes nothing. "Salva associazione" saves WHO + text (no WHY, no reconciliation); "Definisci regola
// WHO → WHY" / "Crea WHO e definisci regola" opens the one WHO WHY rule editor (why_signals.js) above this window,
// which stays open with its fields: closing the editor comes back here.
const T=s=>window.rfT?window.rfT(s):s;
let mv=null,pick={id:null,name:'',created:false},busy=false;
const money=v=>(v/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const kind=()=>document.querySelector('input[name="rw-kind"]:checked').value;
function whoOptions(){$('st-who').innerHTML=`<option value="">${esc(T('— Choose a WHO —'))}</option>`+D.whos.map(w=>`<option value="${w.id}" ${pick.id===w.id?'selected':''}>${esc(w.name)}</option>`).join('');}
function context(){return `${mv.description} · ${mv.date} · ${money(mv.amount_minor)} · ${mv.source?mv.source.name:'—'}${mv.owner?' · '+mv.owner.name:''}`;}
async function showPick(){
 const has=pick.id||pick.name;$('rw-who-line').hidden=!has;
 $('rw-who-name').textContent=pick.id?(D.whos.find(w=>w.id===pick.id)||{}).name||pick.name:pick.name;
 $('rw-who-badge').textContent=pick.id?(pick.created?T('created now'):T('already present')):T('new');
 $('rw-define').hidden=true;$('rw-why').textContent='';
 if(!has)return;
 if(!pick.id){$('rw-why').textContent=T('New WHO: its WHY is still to define.');$('rw-define').textContent=T('Create WHO and define rule');$('rw-define').hidden=false;return;}
 try{
  const s=await api(`/bank/who-search-text/why-status?who_id=${pick.id}&source_id=${mv.source?mv.source.id:''}`);
  $('rw-why').textContent=s.state==='PAIR'?`${T('WHY on this Source:')} ${s.why}`
   :s.state==='RULES'?`${T('WHO → WHY rules for this WHO:')} ${s.active_rules} ${T('active')}${s.mode==='MULTIPLE'?' · MULTIPLE':''}`
   :T('WHY still to define for this Source.')+(s.inactive_rules?` (${s.inactive_rules} ${T('inactive rule(s)')})`:'');
  if(s.state==='MISSING'){$('rw-define').textContent=T('Define WHO → WHY rule');$('rw-define').hidden=false;}
 }catch(e){$('rw-why').textContent=e.message;}
}
async function openText(id){
 const r=await api(`/bank/who-search-text/recognise/${id}`);current=id;mv=r.movement;D.whos=r.whos;
 pick={id:null,name:'',created:false};
 $('rw-desc').textContent=mv.description;
 $('rw-meta').textContent=`${mv.date} · ${money(mv.amount_minor)} · ${mv.source?mv.source.name:'—'} · ${mv.owner?mv.owner.name:T('owner unknown')}`;
 document.querySelector('input[name="rw-kind"][value="SPECIFIC"]').checked=true;
 $('st-input').value='';$('rw-new').value='';$('st-text-error').textContent='';$('rw-ai-status').textContent='';$('rw-ai-result').hidden=true;
 $('st-save').disabled=false;whoOptions();await showPick();
 $('st-text').showModal();$('rw-ai').focus();
}
async function suggest(){
 $('rw-ai').disabled=true;$('rw-ai-status').textContent=T('Asking ChatGPT…');$('rw-ai-result').hidden=true;$('st-text-error').textContent='';
 try{
  const r=await api('/bank/who-search-text/suggest',[['transaction_id',current],['kind',kind()]]);
  pick={id:r.who_id||null,name:r.who_id?'':r.who,created:false};
  $('rw-new').value=r.who_id?'':r.who;whoOptions();
  if(r.text)$('st-input').value=r.text;
  $('rw-ai-result').innerHTML=`<strong>${esc(T('Suggestion'))}:</strong> ${esc(r.who)} <small>(${esc(T(r.new?'new':'already present'))})</small>${r.reason?`<br><small>${esc(r.reason)}</small>`:''}`
   +(r.sources.length?`<br><small>${r.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title||s.url)}</a>`).join(' · ')}</small>`:'');
  $('rw-ai-result').hidden=false;$('rw-ai-status').textContent=T('Suggestion only: nothing is saved until you confirm.');
  await showPick();
 }catch(e){$('rw-ai-status').textContent='';$('st-text-error').textContent=e.message;}
 finally{$('rw-ai').disabled=false;}
}
async function persist(){
 const text=$('st-input').value.trim();if(!text){$('st-text-error').textContent=T('Write the text to recognise in the next transactions.');return null;}
 if(!pick.id&&!pick.name){$('st-text-error').textContent=T('Choose a WHO or write the name of the new WHO.');return null;}
 const r=await api('/bank/who-search-text/recognise-save',[['text',text],['who_id',pick.id||''],['new_who',pick.id?'':pick.name],['transaction_id',current]]);
 if(!D.whos.some(w=>w.id===r.who_id))D.whos.push({id:r.who_id,name:r.who});
 pick={id:r.who_id,name:'',created:pick.created||r.created};$('rw-new').value='';whoOptions();
 return r;
}
async function saveText(){
 if(busy)return;busy=true;$('st-save').disabled=true;$('st-text-error').textContent='';
 try{const r=await persist();if(!r)return;
  $('st-text').close();
  toast(r.created?`${T('WHO created and text saved:')} ${r.who}.`:r.outcome==='already'?`“${$('st-input').value.trim()}” ${T('already recognises')} ${r.who}.`:`${T('Text saved for')} ${r.who}.`);
  await load();
 }catch(e){$('st-text-error').textContent=e.message;}
 finally{busy=false;$('st-save').disabled=false;}
}
async function defineRule(){
 if(busy)return;$('st-text-error').textContent='';
 if(!window.BankWhyRuleEditor){$('st-text-error').textContent=T('The WHO → WHY rule editor is not available.');return;}
 busy=true;
 try{
  if(!pick.id){const r=await persist();if(!r)return;toast(`${T('WHO created:')} ${r.who}.`);await showPick();load().catch(()=>{});}
  await window.BankWhyRuleEditor.open({who_id:pick.id,source:mv.source?mv.source.name:null,context:`${T('Movement:')} ${context()}`,
   onClose:()=>{showPick();$('rw-define').focus();}});
 }catch(e){$('st-text-error').textContent=e.message;}
 finally{busy=false;}
}

document.addEventListener('click',e=>{const o=e.target.closest('[data-open]');if(o)openText(+o.dataset.open).catch(x=>toast(x.message));
 const c=e.target.closest('[data-cancel]');if(c)$(c.dataset.cancel).close();});
$('st-q').oninput=renderRows;$('st-show').onchange=renderRows;$('st-save').onclick=saveText;
$('rw-ai').onclick=suggest;$('rw-define').onclick=defineRule;
$('st-who').onchange=()=>{const v=+$('st-who').value;pick={id:v||null,name:'',created:false};if(v)$('rw-new').value='';showPick();};
$('rw-new').oninput=()=>{const v=$('rw-new').value.trim();if(v){pick={id:null,name:v,created:false};$('st-who').value='';}else if(!pick.id)pick={id:null,name:'',created:false};showPick();};
// A rule saved, renamed or deleted in the editor changes what is recognised: read the movements again.
document.addEventListener('bank-flow-refreshed',()=>{if(D)load().catch(e=>toast(e.message));});
load().catch(e=>{$('st-rows').innerHTML=`<tr><td colspan="7" class="st-error">${esc(e.message)}</td></tr>`;});
})();
