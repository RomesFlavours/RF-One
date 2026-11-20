// BANK_WHO_WHY_UPLOAD_CHECK_001 (Product Owner, 2026-11-06) — Carica e riconcilia: after an upload, the WHO -> WHY
// questions raised by its new movements, one row per WHO, each with one "Gestisci" that opens the existing window:
// the WHO configuration (why_signals.js BankWhoConfig), the same window on its company exceptions, or the WHO WHY rule
// editor (BankWhyRuleEditor) with the movements to distinguish. Nothing is saved here: the windows keep their own
// simulation and explicit confirmation. Closing a window returns to this list; after a save the list is evaluated
// again. Never more than one window opened at a time, never opened automatically.
(()=>{
const box=document.getElementById('who-why-check');if(!box)return;
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let D=null;
function focusRow(whoId){
 const btn=box.querySelector(`tr[data-rr-key="wwc-${whoId}"] [data-wwc]`)||box.querySelector('[data-wwc]')||$('wwc-h');
 if(btn){btn.focus({preventScroll:true});btn.scrollIntoView({block:'nearest'});}
}
function render(){
 const n=D.issues.length;
 $('wwc-count').textContent=n;
 $('wwc-state').textContent=!D.scope?'Questo caricamento non ha aggiunto movimenti nuovi: non ci sono configurazioni WHO → WHY da verificare.'
  :(n?`${D.scope} movimenti nuovi, ${D.affected} WHO riconosciuti: ${D.applicable} con configurazione già applicabile, ${n} da gestire.`
     :`${D.scope} movimenti nuovi, ${D.affected} WHO riconosciuti: per tutti la configurazione WHO → WHY è già applicabile.`);
 $('wwc-table').hidden=!n;
 $('wwc-rows').innerHTML=D.issues.map((x,i)=>`<tr data-rr-key="wwc-${x.who_id}">
  <td data-label="WHO" translate="no">${esc(x.who)}</td>
  <td data-label="Motivo">${esc(x.reason)}</td>
  <td data-label="Movimenti" class="num">${x.count}${x.count_new!==x.count?` <span class="muted small">(${x.count_new} nuovi)</span>`:''}</td>
  <td>${x.action==='INFO'&&x.link?`<a class="btn-secondary" data-wwc href="${esc(x.link)}">Gestisci</a>`:`<button type="button" class="btn-secondary" data-wwc="${i}">Gestisci</button>`}</td></tr>`).join('');
}
async function load(refresh){
 $('wwc-state').textContent=refresh?'Rivaluto le questioni dopo il salvataggio…':'Analisi dei WHO di questo caricamento in corso (motore di riconciliazione, sola lettura)…';
 try{
  const r=await fetch(box.dataset.url+(refresh?'?refresh=1':''),{credentials:'same-origin',cache:'no-store'});
  const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Analisi non riuscita.');
  D=v;render();
 }catch(e){$('wwc-state').textContent=e.message;$('wwc-retry').hidden=false;}
}
// BANK_COMPLETE_MODAL_001 (Product Owner, 2026-11-06): ONE completion procedure. "Gestisci" opens the "Completa"
// window on the first open movement of this WHO in the upload (the window reuses the WHO configuration and the rule
// editor itself); only when no such movement is found does it open the configuration window directly, as before.
async function manage(x){
 if(window.BankComplete){
  try{const r=await fetch('/bank/complete/queue?who_id='+x.who_id,{credentials:'same-origin',cache:'no-store'});const v=await r.json();
   if(r.ok&&v.ok&&v.ids&&v.ids.length){
    window.BankComplete.open(v.ids[0],{queue:v.ids,autoSkip:true,onClose:async changed=>{if(changed)await load(true);focusRow(x.who_id);}});return;}
  }catch(_){}
 }
 manageWindow(x);
}
function manageWindow(x){
 const back=()=>focusRow(x.who_id);
 const saved=async()=>{await load(true);focusRow(x.who_id);};
 const context=`Dal caricamento: ${x.reason}`;
 if(x.action==='RULE'){
  if(!window.BankWhyRuleEditor)return;
  window.BankWhyRuleEditor.open({who_id:x.who_id,context,movements:x.movements||[],movements_total:x.movements_total,onSaved:saved,onClose:back});
 }else if(window.BankWhoConfig){
  window.BankWhoConfig.open(x.who_id,{context,differences:x.differences||[],focus:x.action==='EXCEPTIONS'?'exceptions':null,onSaved:saved,onClose:back});
 }
}
box.addEventListener('click',e=>{const b=e.target.closest('button[data-wwc]');if(b&&D){manage(D.issues[+b.dataset.wwc]);}});
$('wwc-retry').addEventListener('click',()=>{$('wwc-retry').hidden=true;load(false);});
load(false);
})();
