// WHO Search Text (BANK_WHO_SEARCH_TEXT_001). The text that recognises a WHO; then, if missing, its WHO-WHY-WHAT association.
// The recognition rules section above is flow.js (shared with Rules and profiles): this file is scoped so the two never collide.
(()=>{
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,data){const o={credentials:'same-origin',cache:'no-store'};if(data){const b=new URLSearchParams({csrf_token:document.querySelector('meta[name="bank-csrf"]').content});data.forEach(([k,v])=>b.append(k,v??''));o.method='POST';o.body=b;}
 const r=await fetch(path,o);const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
function toast(t){$('toast').textContent=t;$('toast').hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>$('toast').hidden=true,5000);}
let D=null,current=null,assocWho=null;
const BY={RULE:'Rule',TEXT:'Search Text (name / alias)',RULES_DISAGREE:'Rules disagree — review',TEXT_AMBIGUOUS:'Several WHO — review'};
const whoCell=r=>r.whos.length?r.whos.map(w=>esc(w)+(r.by==='RULE'&&!r.known?' <small class="st-null">not a WHO yet</small>':'')).join('<br>'):'<span class="st-null">null</span>';

function renderRows(){
 const q=$('st-q').value.trim().toLowerCase(),show=$('st-show').value;
 const rows=D.movements.filter(r=>(!show||(show==='null'?!r.by:show==='review'?(r.by==='RULES_DISAGREE'||r.by==='TEXT_AMBIGUOUS'):r.by===show))&&(!q||(r.description+' '+r.whos.join(' ')).toLowerCase().includes(q)));
 $('st-count').textContent=`${rows.length} of ${D.movements.length}`;
 $('st-rows').innerHTML=rows.map(r=>`<tr><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td>${whoCell(r)}</td><td>${esc(BY[r.by]||'')}</td><td><button type="button" class="btn-secondary" data-open="${r.id}">Text</button></td></tr>`).join('');
}
async function load(){D=await api('/bank/who-search-text/data');renderRows();}

async function openText(id){
 const t=await api(`/bank/who-search-text/movement/${id}`);current=id;
 $('st-desc').textContent=t.description;
 $('st-fields').innerHTML=t.fields.map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
 $('st-input').value='';$('st-text-error').textContent='';$('st-save').disabled=false;
 $('st-who').innerHTML='<option value=""></option>'+D.whos.map(w=>`<option value="${w.id}">${esc(w.name)}</option>`).join('');
 $('st-text').showModal();$('st-input').focus();
}
async function saveText(){
 const text=$('st-input').value.trim();if(!text){$('st-text-error').textContent='Write the text to search.';return;}
 $('st-save').disabled=true;
 try{
  const r=await api('/bank/who-search-text/save',[['text',text],['who_id',$('st-who').value],['transaction_id',current]]);
  $('st-text').close();
  toast(r.outcome==='created'?`WHO ${r.who} created.`:r.outcome==='reused'?`WHO ${r.who} already existed.`:r.outcome==='alias'?`“${text}” saved as alias of ${r.who}.`:`“${text}” already recognises ${r.who}.`);
  if(r.needs_association)openAssoc(r.who_id,r.who);
  await load();
 }catch(e){$('st-text-error').textContent=e.message;$('st-save').disabled=false;}
}

function openAssoc(id,name){
 assocWho=id;$('st-assoc-who').textContent=name;$('st-why-q').value='';$('st-assoc-error').textContent='';$('st-assoc-save').disabled=false;
 $('st-whys').innerHTML=D.whys.map(y=>`<label data-hay="${esc((y.name+' '+y.what).toLowerCase())}"><input type="checkbox" value="${y.id}"> ${esc(y.name)} <small>${esc(y.what)}</small></label>`).join('');
 syncDefault();$('st-assoc').showModal();
}
function chosen(){return [...$('st-whys').querySelectorAll('input:checked')].map(c=>c.value);}
function syncDefault(){
 const ids=chosen(),keep=$('st-default').value;
 $('st-default').innerHTML=`<option value="">${ids.length?'— No default —':'Choose possible WHY first'}</option>`+ids.map(id=>`<option value="${id}">${esc(D.whys.find(y=>String(y.id)===id).name)}</option>`).join('');
 $('st-default').value=ids.length===1?ids[0]:(ids.includes(keep)?keep:'');
}
async function saveAssoc(){
 const ids=chosen();if(!ids.length){$('st-assoc-error').textContent='Choose at least one WHY.';return;}
 $('st-assoc-save').disabled=true;
 try{const r=await api('/bank/who-search-text/association',[['who_id',assocWho],['default_why_id',$('st-default').value],...ids.map(id=>['why_ids',id])]);
  $('st-assoc').close();toast(`WHO-WHY-WHAT association of ${r.who} saved.`);}
 catch(e){$('st-assoc-error').textContent=e.message;$('st-assoc-save').disabled=false;}
}

document.addEventListener('click',e=>{const o=e.target.closest('[data-open]');if(o)openText(+o.dataset.open).catch(x=>toast(x.message));
 const c=e.target.closest('[data-cancel]');if(c)$(c.dataset.cancel).close();});
$('st-q').oninput=renderRows;$('st-show').onchange=renderRows;$('st-save').onclick=saveText;$('st-assoc-save').onclick=saveAssoc;
$('st-whys').onchange=syncDefault;
$('st-why-q').oninput=()=>{const q=$('st-why-q').value.toLowerCase();$('st-whys').querySelectorAll('label').forEach(l=>l.hidden=q&&!l.dataset.hay.includes(q));};
// A rule saved, renamed or deleted in the editor changes what is recognised: read the movements again.
document.addEventListener('bank-flow-refreshed',()=>{if(D)load().catch(e=>toast(e.message));});
load().catch(e=>{$('st-rows').innerHTML=`<tr><td colspan="7" class="st-error">${esc(e.message)}</td></tr>`;});
})();
