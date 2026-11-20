// WHO Status, formerly WHO Search Text (BANK_WHO_SEARCH_TEXT_001; renamed BANK_SECTION_NAV_001, 2026-11-05). The text that recognises a WHO; then, if missing, its WHO-WHY-WHAT association.
// The recognition rules section above is flow.js (shared with Rules and profiles): this file is scoped so the two never collide.
(()=>{
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,data){const o={credentials:'same-origin',cache:'no-store'};if(data){const b=new URLSearchParams({csrf_token:document.querySelector('meta[name="bank-csrf"]').content});data.forEach(([k,v])=>b.append(k,v??''));o.method='POST';o.body=b;}
 const r=await fetch(path,o);const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
function toast(t){$('toast').textContent=t;$('toast').hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>$('toast').hidden=true,5000);}
let D=null,current=null,page=1,loadSerial=0,searchTimer;
const BY={RULE:'Rule',TEXT:'Name or alias',RULES_DISAGREE:'Rules disagree — review',TEXT_AMBIGUOUS:'Several WHO — review'};
const whoCell=r=>r.whos.length?r.whos.map(w=>esc(w)+(r.by==='RULE'&&!r.known?' <small class="st-null">not a WHO yet</small>':'')).join('<br>'):'<span class="st-null">null</span>';

function renderRows(){
 if(!$('st-rows'))return; // WHO Status is on the Regole page only
 const rows=D.movements;
 $('st-count').textContent=`${D.filtered} of ${D.total}`;
 $('st-page').textContent=`${D.page} / ${D.pages}`;
 $('st-prev').disabled=D.page<=1;$('st-next').disabled=D.page>=D.pages;
 $('st-rows').innerHTML=rows.map(r=>`<tr><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td>${whoCell(r)}</td><td>${esc(BY[r.by]||'')}</td><td style="white-space:nowrap"><button type="button" class="btn-secondary" data-ai-rule="${r.id}">+ AI Rule</button> <button type="button" class="btn-secondary" data-open="${r.id}">By Text</button></td></tr>`).join('');
}
// Product Owner, 2026-11-17: WHO multipli ("+ AI", routines come later) and WHO univoci (one fixed WHY, WHAT follows).
function renderWhos(){
 if(!$('known-rows'))return; // the WHO lists are on the WHO page only
 const disc=D.discovery||{candidates:[]};
 $('new-count').textContent=String(disc.candidates.length);
 $('new-status').textContent=disc.searched_at?`Ultima ricerca: ${new Date(disc.searched_at).toLocaleString('it-IT')} · ${disc.read} movimenti letti su ${disc.movements}.`:'Premi «Cerca nuovi WHO»: RF-One trova i pattern, estrae i WHO e mostra qui quelli che non esistono ancora.';
 $('new-rows').innerHTML=disc.candidates.length?disc.candidates.map(c=>`<tr><td translate="no">${esc(c.name)}${c.uncertain?' <small class="st-null">nome da verificare</small>':''}</td><td class="num">${c.count}</td><td translate="no"><small>${esc(c.example)}</small></td><td style="white-space:nowrap;text-align:right"><button type="button" class="btn-secondary" data-new-who="${esc(c.name)}" data-new-kind="single">Singolo</button> <button type="button" class="btn-secondary" data-new-who="${esc(c.name)}" data-new-kind="multiple">Più WHY</button> <button type="button" class="btn-secondary" data-new-who="${esc(c.name)}" data-new-kind="intermediary">Intermediario</button> <button type="button" class="btn-secondary" data-new-alias="${esc(c.name)}">È alias di…</button></td></tr>`).join(''):`<tr><td colspan="4" class="st-null">${disc.searched_at?'Nessun WHO nuovo.':'—'}</td></tr>`;
 const whys=D.fixed_whys||[],byId=Object.fromEntries((D.whys||[]).map(w=>[w.id,w]));
 const q=($('known-q')?$('known-q').value:'').trim().toLocaleLowerCase('it');
 // Product Owner, 2026-11-18: intermediaries (not WHO), WHO con più WHY, WHO univoci.
 const via=D.whos.filter(w=>w.intermediary),multiple=D.whos.filter(w=>w.multiple&&!w.intermediary),single=D.whos.filter(w=>!w.multiple&&!w.intermediary&&w.name.toLocaleLowerCase('it').includes(q));
 $('intermediary-count').textContent=String(via.length);
 $('intermediary-rows').innerHTML=via.length?via.map(w=>`<tr data-rr-key="who-${w.id}"><td translate="no">${esc(w.name)}</td><td style="white-space:nowrap;text-align:right"><button type="button" class="btn-secondary" data-who-kind="single" data-who="${w.id}">Non è intermediario</button></td></tr>`).join(''):'<tr><td colspan="2" class="st-null">Nessun intermediario.</td></tr>';
 $('multiple-count').textContent=String(multiple.length);
 $('multiple-rows').innerHTML=multiple.length?multiple.map(w=>`<tr data-rr-key="who-${w.id}"><td translate="no">${esc(w.name)}</td><td style="white-space:nowrap;text-align:right"><button type="button" class="btn-secondary" data-known-ai="${w.id}">+ AI</button> <button type="button" class="btn-secondary" data-who-kind="single" data-who="${w.id}">Univoco</button> <button type="button" class="btn-secondary" data-who-kind="intermediary" data-who="${w.id}">Intermediario</button></td></tr>`).join(''):'<tr><td colspan="2" class="st-null">Nessun WHO con più WHY.</td></tr>';
 $('known-count').textContent=String(D.whos.length-multiple.length-via.length);
 $('known-rows').innerHTML=single.map(w=>{const cur=byId[w.why_id];const opts=['<option value="">—</option>'].concat(whys.map(x=>`<option value="${x.id}"${x.id===w.why_id?' selected':''}>${esc(x.name)}</option>`));
  if(cur&&!whys.some(x=>x.id===cur.id))opts.push(`<option value="${cur.id}" selected>${esc(cur.name)}</option>`);
  return `<tr data-rr-key="who-${w.id}"><td translate="no">${esc(w.name)}</td><td><select data-fixed-why="${w.id}" aria-label="WHY di ${esc(w.name)}">${opts.join('')}</select>${w.other_config?'<br><small class="st-null">Configurazione WHY diversa nella pagina WHY</small>':''}</td><td data-what="${w.id}">${esc(cur?cur.what:'')}</td><td style="white-space:nowrap;text-align:right"><button type="button" class="btn-secondary" data-who-kind="multiple" data-who="${w.id}">Più WHY</button> <button type="button" class="btn-secondary" data-who-kind="intermediary" data-who="${w.id}">Intermediario</button></td></tr>`;}).join('')||'<tr><td colspan="4" class="st-null">Nessun WHO.</td></tr>';
}
if($('who-discover'))$('who-discover').onclick=async()=>{const b=$('who-discover');b.disabled=true;$('new-status').textContent='Ricerca in corso: RF-One legge tutti i movimenti…';
 try{const r=await api('/bank/who-search-text/discover',[]);toast(`${r.found} WHO nuovi trovati.`);await load();}catch(err){toast(err.message);$('new-status').textContent=err.message;}finally{b.disabled=false;}};
document.addEventListener('click',async e=>{const b=e.target.closest('button[data-new-who]');if(!b)return;
 const name=b.dataset.newWho,kind=b.dataset.newKind;b.disabled=true;
 try{const r=await api('/bank/who-search-text/discovered/create',[['name',name],['kind',kind]]);
  D.discovery.candidates=D.discovery.candidates.filter(c=>c.name!==name);D.whos.push(r.who);D.whos.sort((x,y)=>x.name.localeCompare(y.name));renderWhos();
  toast(kind==='intermediary'?`${name}: creato tra gli intermediari.`:kind==='multiple'?`${name}: creato tra i WHO con più WHY.`:`${name}: creato tra i WHO univoci.`);}
 catch(err){b.disabled=false;toast(err.message);}});
// «È alias di…» (Product Owner, 2026-11-18): the new name is the same counterparty as an existing WHO.
document.addEventListener('click',e=>{const b=e.target.closest('button[data-new-alias]');if(!b)return;
 const cell=b.closest('td'),name=b.dataset.newAlias;cell.dataset.actions=cell.innerHTML;
 if(!$('who-names-list')){const dl=document.createElement('datalist');dl.id='who-names-list';document.body.appendChild(dl);}
 $('who-names-list').innerHTML=D.whos.map(w=>`<option value="${esc(w.name)}"></option>`).join('');
 cell.innerHTML=`<input list="who-names-list" data-alias-input placeholder="Scrivi o scegli il WHO esistente" aria-label="WHO di cui ${esc(name)} è alias" style="width:16rem"> <button type="button" class="btn-primary" data-alias-save="${esc(name)}">Salva alias</button> <button type="button" class="btn-secondary" data-alias-cancel>Annulla</button>`;
 cell.querySelector('input').focus();});
document.addEventListener('click',async e=>{const c=e.target.closest('button[data-alias-cancel]');
 if(c){const cell=c.closest('td');cell.innerHTML=cell.dataset.actions;cell.querySelector('[data-new-alias]').focus();return;}
 const b=e.target.closest('button[data-alias-save]');if(!b)return;
 const name=b.dataset.aliasSave,typed=b.closest('td').querySelector('input').value.trim();
 const who=D.whos.find(w=>w.name.toLocaleLowerCase('it')===typed.toLocaleLowerCase('it'));
 if(!who){toast('Scegli un WHO esistente dall\'elenco.');return;}
 b.disabled=true;
 try{const r=await api('/bank/who-search-text/discovered/alias',[['name',name],['who_id',who.id]]);
  D.discovery.candidates=D.discovery.candidates.filter(x=>x.name!==name);renderWhos();
  toast(r.outcome==='already'?`${name} riconosce già ${r.who}.`:`${name}: salvato come alias di ${r.who}.`);}
 catch(err){b.disabled=false;toast(err.message);}});
document.addEventListener('change',async e=>{const sel=e.target.closest('select[data-fixed-why]');if(!sel)return;
 const id=Number(sel.dataset.fixedWhy),why=sel.value?Number(sel.value):null;sel.disabled=true;
 try{await api('/bank/who-search-text/fixed-why',[['who_id',id],['why_id',why??'']]);const w=D.whos.find(x=>x.id===id);if(w)w.why_id=why;
  const cell=document.querySelector(`[data-what="${id}"]`);const x=(D.whys||[]).find(v=>v.id===why);if(cell)cell.textContent=x?x.what:'';toast('WHY salvato.');}
 catch(err){toast(err.message);}finally{sel.disabled=false;sel.focus();}});
document.addEventListener('click',async e=>{const b=e.target.closest('button[data-who-kind]');if(!b)return;
 const id=Number(b.dataset.who),kind=b.dataset.whoKind;b.disabled=true;
 try{await api('/bank/who-search-text/who-kind',[['who_id',id],['kind',kind]]);const w=D.whos.find(x=>x.id===id);if(w){w.multiple=kind==='multiple';w.intermediary=kind==='intermediary';}renderWhos();
  toast(kind==='intermediary'?'Spostato negli intermediari.':kind==='multiple'?'Spostato nei WHO con più WHY.':'Spostato nei WHO univoci.');}
 catch(err){b.disabled=false;toast(err.message);}});
async function load(){const serial=++loadSerial;
 const query=new URLSearchParams({page,per_page:100,show:$('st-show')?$('st-show').value:'null',q:$('st-q')?$('st-q').value.trim():''});
 const data=await api('/bank/who-search-text/data?'+query);
 if(serial!==loadSerial)return;D=data;page=D.page;renderRows();renderWhos();}

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
if($('known-q'))$('known-q').oninput=()=>{if(D)renderWhos();};
if($('st-q'))$('st-q').oninput=()=>{clearTimeout(searchTimer);page=1;++loadSerial;searchTimer=setTimeout(()=>load().catch(e=>toast(e.message)),200);};
if($('st-show'))$('st-show').onchange=()=>{page=1;load().catch(e=>toast(e.message));};$('st-save').onclick=saveText;
if($('st-prev'))$('st-prev').onclick=()=>{page=Math.max(1,page-1);load().catch(e=>toast(e.message));};
if($('st-next'))$('st-next').onclick=()=>{page++;load().catch(e=>toast(e.message));};
$('rw-ai').onclick=suggest;$('rw-define').onclick=defineRule;
$('st-who').onchange=()=>{const v=+$('st-who').value;pick={id:v||null,name:'',created:false};if(v)$('rw-new').value='';showPick();};
$('rw-new').oninput=()=>{const v=$('rw-new').value.trim();if(v){pick={id:null,name:v,created:false};$('st-who').value='';}else if(!pick.id)pick={id:null,name:'',created:false};showPick();};
// A rule saved, renamed or deleted in the editor changes what is recognised: read the movements again.
document.addEventListener('bank-flow-refreshed',()=>{if(D)load().catch(e=>toast(e.message));});
load().catch(e=>{if($('st-rows'))$('st-rows').innerHTML=`<tr><td colspan="7" class="st-error">${esc(e.message)}</td></tr>`;});
})();
