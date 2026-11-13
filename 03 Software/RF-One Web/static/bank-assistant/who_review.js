// Review of the WHO formats proposed by Find standard formats (BANK_WHO_FORMAT_REVIEW_001).
// Uses the page helpers of flow.js ($, esc, api, toast). Ticks are review notes only: they never change a WHO.
window.whoReview=(()=>{
 let scan=null;const open=new Set(),ticks={},loaded={};
 const base=i=>`/bank/flow/discover/${scan}/formats/${i}`;
 async function coverage(){
  const node=$('who-coverage');if(!node||!scan)return;
  try{const c=await api(`/bank/flow/discover/${scan}/coverage`);
   node.innerHTML=`<div class="flow-item who-summary"><h3>WHO coverage</h3><table class="who-table"><tbody>
    <tr><td>Description structures examined (not read by an approved rule)</td><td>${c.groups??'—'} · ${c.structures_once??0} seen only once · ${c.passes??1} search passes</td></tr>
    <tr><td>Proposed WHO rules</td><td>${c.proposals}: ${c.proposals_recurring} recurring · ${c.proposals_once} observed once (candidates) · ${c.generic_rules} general (WHO opens the description, used only where no specific rule reads)</td></tr>
    <tr><td>Movements selected by the proposed rules (each counted once)</td><td>${c.selected} of ${c.movements} (${c.selected_pct}%)</td></tr>
    <tr><td>Distinct WHO extracted</td><td>${c.distinct_who}</td></tr>
    <tr><td>Movements read differently by two proposed rules (to resolve in the review)</td><td>${c.conflicts}</td></tr>
    <tr><td>Movements with one single proposed WHO</td><td>${c.unique} (${c.unique_pct}%)</td></tr>
    <tr><td>Recognitions marked wrong</td><td>${c.flagged_wrong}</td></tr>
    <tr><td>Verified recognitions (rule reviewed, not marked wrong)</td><td>${c.verified} (${c.verified_pct}%) · ${c.reviewed_rules} rules reviewed</td></tr>
    <tr><td>Already recognized by approved WHO rules</td><td>${c.approved_selected} (${c.approved_rules} rules)</td></tr>
    <tr><td>Recognized by approved or proposed rules</td><td>${c.recognized} of ${c.movements} (${c.recognized_pct}%)</td></tr>
    <tr><td>Movements without a recognized WHO</td><td>${c.without_who}</td></tr>
    <tr><td>…of which the AI says the description names no counterparty (transfers, checks, interest, fees)</td><td>${c.no_name} (${c.no_name_groups} structures) — proposed, not verified</td></tr>
    <tr><td>Recognized among movements whose description names a counterparty</td><td>${c.recognized} of ${c.with_name} (${c.recognized_of_with_name_pct}%)</td></tr></tbody></table>
    <p class="muted">Proposed = what the rules would extract. Verified = you reviewed the rule and did not mark the movement as wrong.</p></div>`;
   return c;
  }catch(error){node.textContent=error.message;}
 }
 function diffTable(d){
  if(!d)return '';
  const rows=[...d.changed.map(r=>({...r,what:'WHO changes'})),...d.removed.map(r=>({...r,what:'No longer selected'})),...d.added.map(r=>({...r,what:'Newly selected'}))];
  return `<div class="who-diff"><p><strong>Corrected rule tested on the whole history:</strong> ${d.before} selected before, ${d.after} now · ${d.unchanged} unchanged · ${d.changed.length} with a different WHO · ${d.removed.length} no longer selected · ${d.added.length} newly selected · ${d.wrong_fixed} of ${d.wrong_marked} marked wrong are fixed.</p>
   ${rows.length?`<div class="who-scroll"><table class="who-table"><thead><tr><th>Change</th><th>Source</th><th>Date</th><th>Description</th><th>Amount</th><th>WHO before</th><th>WHO now</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.what)}</td><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td>${esc(r.before||'—')}</td><td>${esc(r.after||'—')}</td></tr>`).join('')}</tbody></table></div>`:''}</div>`;
 }
 function render(i,data){
  const box=document.querySelector(`[data-review-index="${i}"]`);if(!box)return;
  const t=ticks[i]||(ticks[i]=new Set(data.review.wrong||[]));
  box.innerHTML=`<details ${open.has(i)?'open':''}><summary>Movements selected by this rule (${data.rows.length})${data.rows.length===1?' · observed once: candidate, not recurring':''}${data.review.reviewed?' · reviewed':''}${t.size?` · ${t.size} marked wrong`:''}</summary>
   ${data.generic?`<p class="muted">General rule (the WHO opens the description): it reads only the movements no more specific rule reads${data.taken_by_anchored?` — ${data.taken_by_anchored} more are read by more specific rules and are not listed here`:''}.</p>`:''}
   <p class="muted">Tick only the movements whose WHO is wrong. Ticks are review notes: they change no WHO and no classification.</p>
   <div class="who-scroll"><table class="who-table"><thead><tr><th>Wrong</th><th>Source</th><th>Date</th><th>Description</th><th>Amount</th><th>WHO extracted</th></tr></thead><tbody>
   ${data.rows.map(r=>`<tr class="${t.has(r.id)?'who-wrong':''}"><td><input type="checkbox" aria-label="WHO wrong for movement ${r.id}" data-wrong="${r.id}" ${t.has(r.id)?'checked':''}></td><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td><td><strong>${esc(r.who)}</strong></td></tr>`).join('')}
   </tbody></table></div>
   <div class="flow-actions"><button class="btn-secondary" data-save-review>Save review</button><label class="who-note">What is wrong (optional)<input maxlength="1000" data-note placeholder="E.g. the city is included in the name"></label><button data-revise>Correct the rule with AI</button></div>
   <p role="status" data-review-status></p>${diffTable(data.last_diff)}</details>`;
  const d=box.querySelector('details');d.ontoggle=()=>{d.open?open.add(i):open.delete(i);};
  box.querySelectorAll('[data-wrong]').forEach(c=>c.onchange=()=>{const id=Number(c.dataset.wrong);c.checked?t.add(id):t.delete(id);c.closest('tr').classList.toggle('who-wrong',c.checked);});
  const status=text=>box.querySelector('[data-review-status]').textContent=text;
  box.querySelector('[data-save-review]').onclick=async()=>{try{await api(`${base(i)}/review`,{wrong:[...t].join(',')});status('Review saved. Nothing was changed in Bank.');await load(i);await coverage();}catch(error){status(error.message);}};
  box.querySelector('[data-revise]').onclick=async e=>{e.target.disabled=true;status('The AI is correcting the rule; RF-One then tests it on every movement…');
   try{const r=await api(`${base(i)}/revise`,{wrong:[...t].join(','),note:box.querySelector('[data-note]').value});toast('Corrected rule proposed. Nothing is active until you approve it.');delete ticks[i];if(window.pollScan)await window.pollScan();else await load(i);}
   catch(error){status(error.message);e.target.disabled=false;}};
 }
 async function load(i){
  const box=document.querySelector(`[data-review-index="${i}"]`);if(!box)return;
  if(!loaded[i])box.innerHTML='<p class="muted">Loading the movements this rule selects…</p>';
  try{loaded[i]=await api(`${base(i)}/movements`);render(i,loaded[i]);}catch(error){box.textContent=error.message;}
 }
 let counts={};
 function closed(i){
  // The movements are read when the rule is opened: 57 rules never load all at once.
  const box=document.querySelector(`[data-review-index="${i}"]`);if(!box)return;
  const n=counts[i];
  box.innerHTML=`<details><summary>Movements selected by this rule${n==null?'':` (${n})`}${n===1?' · observed once: candidate, not recurring':''}</summary><p class="muted">Loading…</p></details>`;
  const d=box.querySelector('details');d.ontoggle=()=>{if(d.open){open.add(i);load(i);}};
 }
 async function attach(scanId){
  if(scan!==scanId){scan=scanId;open.clear();for(const k in ticks)delete ticks[k];for(const k in loaded)delete loaded[k];}
  const c=await coverage();counts=(c&&c.per_format)||{};
  document.querySelectorAll('[data-review-index]').forEach(b=>{const i=Number(b.dataset.reviewIndex);delete loaded[i];open.has(i)?load(i):closed(i);});
 }
 return {attach,coverage};
})();
