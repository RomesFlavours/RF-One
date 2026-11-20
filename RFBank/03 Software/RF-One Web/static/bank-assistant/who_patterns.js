// WHO Pattern Training (BANK_WHO_PATTERN_SEARCH_001, Product Owner, 2026-11-06). "Search patterns" asks the server for
// the recurring patterns of every loaded movement (read-only, recomputed each time); "Define rule" opens the one AI rule
// editor of flow.js (openChat) with that pattern: the server recomputes it and passes its example, structure, count,
// descriptions and movement ids to the conversation. Scoped: flow.js already owns the global names.
(()=>{
const $=id=>document.getElementById(id);
const T=s=>window.rfT?window.rfT(s):s;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>Number(n).toLocaleString(document.documentElement.lang==='it'?'it-IT':'en-US');
const button=(key,variant)=>`<button type="button" class="btn-secondary" data-pattern="${esc(key)}"${variant?` data-variant="${esc(variant)}"`:''}>Define rule</button>`;
function subs(p){
 if(!p.variants.length)return '';
 return `<details class="wp-subs"><summary><span>Sub-families</span> (${p.variants.length}) · <span>already included in the total</span></summary><table class="who-table"><tbody>${p.variants.map(v=>
  `<tr><td translate="no">${esc(v.name)}</td><td class="wp-num">${num(v.count)}</td><td>${button(p.key,v.variant)}</td></tr>`).join('')}</tbody></table></details>`;
}
async function search(){
 $('wp-search').disabled=true;$('wp-status').textContent=T('Searching for patterns in every movement…');
 try{
  const r=await fetch('/bank/who-training/patterns',{credentials:'same-origin',cache:'no-store'});const v=await r.json();
  if(!r.ok||v.ok===false)throw Error(v.error||T('Operation could not be completed.'));
  // Already sorted by the server; sorted again here so the order never depends on transport.
  const rows=v.patterns.slice().sort((a,b)=>b.count-a.count);
  $('wp-rows').innerHTML=rows.map(p=>`<tr data-rr-key="${esc(p.key)}"><td><strong translate="no">${esc(p.title)}</strong>${subs(p)}</td><td class="wp-structure" translate="no">${esc(p.template)}</td><td class="wp-num">${num(p.count)}</td><td>${button(p.key)}</td></tr>`).join('');
  $('wp-count').textContent=num(rows.length);$('wp-list').hidden=false;
  $('wp-status').innerHTML=`<span>Movements analysed</span>: ${num(v.total)} · <span>in a pattern</span>: ${num(v.covered)}`;
 }catch(e){$('wp-status').textContent=e.message;}
 finally{$('wp-search').disabled=false;}
}
$('wp-search').onclick=search;
// UI rule 5: closing the editor brings the person back to the same row, with focus on the button used.
let opener=null;
document.addEventListener('click',e=>{const b=e.target.closest('[data-pattern]');if(!b)return;opener=b;
 openChat({kind:'EXTRACTOR',pattern:b.dataset.pattern,variant:b.dataset.variant||''});});
$('flow-chat').addEventListener('close',()=>{if(opener&&opener.isConnected)setTimeout(()=>opener.focus(),0);});
})();
