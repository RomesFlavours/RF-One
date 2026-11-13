// AI rules check (BANK_AI_RULE_CHECK_001): read-only display of every operative rule on every movement.
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function get(path){const r=await fetch(path,{credentials:'same-origin',cache:'no-store'});const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Unable to load.');return v;}
const same=(a,b)=>a&&b&&a.trim().toUpperCase()===b.trim().toUpperCase();
let R=null;
function table(rows,withRule){
 return `<div class="who-scroll"><table class="who-table"><thead><tr><th>Source</th><th>Date</th><th>Description</th><th>Amount</th>${withRule?'<th>WHO by this rule</th><th>WHY by this rule</th>':'<th>What the rules give</th>'}<th>Human decision</th><th>Engine (last run)</th></tr></thead><tbody>
 ${rows.map(r=>{const h=[r.human_who,r.human_why||r.human_what].filter(Boolean).join(' · ');const e=r.engine?[r.engine.who,r.engine.why,r.engine.status].filter(Boolean).join(' · '):'—';
  const bad=withRule&&((r.who&&r.human_who&&!same(r.who,r.human_who))||(r.why&&r.human_why&&!same(r.why,r.human_why)));
  const rules=withRule?`<td><strong>${esc(r.who||'—')}</strong></td><td>${esc(r.why||'—')}</td>`:`<td>${(r.others||[]).map(o=>`<div><small>#${o.rule} ${esc(o.title||'')}</small>: <strong>${esc(o.who||'—')}</strong>${o.why?' · '+esc(o.why):''}</div>`).join('')||'—'}</td>`;
  return `<tr class="${bad?'who-wrong rc-bad':''}"><td>${esc(r.source)}</td><td>${esc(r.date)}</td><td>${esc(r.description)}</td><td class="num">${esc(r.amount)}</td>${rules}<td>${esc(h||'—')}</td><td>${esc(e)}</td></tr>`;}).join('')}
 </tbody></table></div>`;
}
function renderRules(){
 const q=$('rc-q').value.toLowerCase();const rules=R.rules.filter(r=>((r.title||'')+' '+(r.text||'')).toLowerCase().includes(q));$('rc-count').textContent=rules.length;
 $('rc-rules').innerHTML=rules.map(r=>`<div class="flow-item"><h3>#${r.id} ${esc(r.title)}</h3><p class="flow-chat-text">${esc(r.text)}</p>
  <p><span class="badge">${esc(r.kind)} · version ${r.version}</span> Intercepts <strong>${r.movements}</strong> movements · gives WHO on ${r.gives_who} · WHY on ${r.gives_why} · compared with human decisions: ${r.human_agree} agree, <strong>${r.human_disagree} differ</strong></p>
  ${r.movements?`<details data-rule="${r.id}"><summary>Show the ${r.movements} movements</summary><p class="muted">Loading…</p></details>`:'<p class="muted">This rule reads no movement of the database.</p>'}</div>`).join('');
 document.querySelectorAll('[data-rule]').forEach(d=>d.ontoggle=async()=>{if(!d.open||d.dataset.loaded)return;d.dataset.loaded=1;try{const v=await get(`/bank/ai-rules/check/rules/${d.dataset.rule}`);d.innerHTML=`<summary>${v.rows.length} movements (rows that differ from the human decision are highlighted in red)</summary>`+table(v.rows,true);}catch(e){d.innerHTML=`<summary>Error</summary><p>${esc(e.message)}</p>`;}});
}
document.querySelectorAll('[data-list]').forEach(d=>d.ontoggle=async()=>{if(!d.open||d.dataset.loaded)return;d.dataset.loaded=1;try{const v=await get(`/bank/ai-rules/check/list/${d.dataset.list}`);d.innerHTML=`<summary>${v.rows.length} movements</summary>`+table(v.rows,false);}catch(e){d.innerHTML=`<summary>Error</summary><p>${esc(e.message)}</p>`;}});
$('rc-q').oninput=()=>R&&renderRules();
get('/bank/ai-rules/check/data').then(v=>{R=v;const s=v.summary;
 $('rc-summary').innerHTML=`<table class="who-table"><tbody>
  <tr><td>Movements in the database</td><td>${s.movements}</td></tr>
  <tr><td>Operative rules</td><td>${s.rules} (${s.rules_matching} intercept at least one movement)</td></tr>
  <tr><td>Movements read by at least one rule</td><td>${s.read}</td></tr>
  <tr><td>…with a WHO from a rule</td><td>${s.with_who}</td></tr>
  <tr><td>…with a WHY from a rule</td><td>${s.with_why}</td></tr>
  <tr><td>Movements where rules give different WHO or WHY</td><td><strong>${s.conflicts}</strong></td></tr>
  <tr><td>Movements no rule reads</td><td>${s.unread}</td></tr>
  <tr><td>Engine run compared</td><td>${s.engine_run?'#'+s.engine_run:'none'}</td></tr></tbody></table>`;renderRules();})
 .catch(e=>{$('rc-summary').textContent='Unable to run the check: '+e.message;});
