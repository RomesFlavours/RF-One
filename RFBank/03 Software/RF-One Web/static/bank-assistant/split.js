// Split (BANK_SPLIT_ALLOCATION_001): one bank movement, several classification lines that add up to it exactly.
(()=>{
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>v==null?'—':(v/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
async function api(path,data){const o={credentials:'same-origin',cache:'no-store'};if(data){const b=new URLSearchParams({csrf_token:document.querySelector('meta[name="bank-csrf"]').content});data.forEach(([k,v])=>b.append(k,v??''));o.method='POST';o.body=b;}
 const r=await fetch(path,o);const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||'Operation could not be completed.');return v;}
function toast(t){$('toast').textContent=t;$('toast').hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>$('toast').hidden=true,6000);}
const LINK={CERTAIN:'Certain',CODE_ONLY:'Code, not verified',CANDIDATE:'Candidate',AMBIGUOUS:'Ambiguous'};
const reasons=rs=>rs.map(r=>`<li><strong>${esc(r.label)}</strong>${r.detail?` — ${esc(r.detail)}`:''}</li>`).join('');
const txn=Number(document.body.dataset.txn)||null;
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));

// -- list -------------------------------------------------------------------------------------------------
async function list(){
 const who=new URLSearchParams(location.search).get('who');
 const D=await api('/bank/split/data'+(who?`?who=${encodeURIComponent(who)}`:''));
 $('sp-count').textContent=D.movements.length;
 $('sp-tiles').innerHTML=Object.entries(LINK).map(([k,l])=>`<div class="sp-tile"><strong>${D.counts[k]||0}</strong>${l}</div>`).join('')
  +`<div class="sp-tile"><strong>${D.complete}</strong>Certain and complete</div>`;
 $('sp-rows').innerHTML=D.movements.length?D.movements.map(r=>`<tr><td>${esc(r.date)}</td><td><a href="/bank/split/${r.id}">${esc(r.description)}</a><br><small class="sp-muted">${esc(r.codes.join(', '))}</small></td>
  <td>${esc(r.source)}<br><small class="sp-muted">${esc(r.owner?.name||'owner unknown')}</small></td><td class="num">${money(r.amount_minor)}</td>
  <td><span class="sp-pill">${esc(LINK[r.link]||r.link)}</span></td>
  <td>${r.status==='COMPLETE'?`<span class="sp-ok">Complete · ${r.lines} line(s)</span>`:`<span class="sp-bad">Incomplete</span><ul>${reasons(r.reasons.slice(0,3))}</ul>`}</td></tr>`).join('')
  :'<tr><td colspan="6" class="sp-muted">No Amazon order report is linked to a bank movement. Load the report on the Amazon page.</td></tr>';
 $('sp-free-count').textContent=D.unmatched.length;
 $('sp-free').innerHTML=D.unmatched.map(c=>`<tr><td>${esc(c.code)}</td><td>${esc(c.orders.join(', '))}</td><td>${esc(c.payment_dates.join(', '))}</td><td class="num">${money(c.expected_minor)}</td><td class="num">${c.rows}</td></tr>`).join('')||'<tr><td colspan="5" class="sp-muted">None.</td></tr>';
 $('sp-done-count').textContent=D.split.length;
 $('sp-done').innerHTML=D.split.map(r=>`<tr><td>${esc(r.date)}</td><td><a href="/bank/split/${r.id}">${esc(r.description)}</a></td><td>${esc(r.source)}</td><td class="num">${money(r.amount_minor)}</td><td class="num">${r.lines}</td></tr>`).join('')||'<tr><td colspan="5" class="sp-muted">None.</td></tr>';
}

// -- one movement ---------------------------------------------------------------------------------------
let D=null,lines=[];
const cents=v=>{const s=String(v??'').trim().replace(/[$,\s]/g,'');if(!s)return null;if(!/^-?\d+(\.\d{1,2})?$/.test(s))return NaN;const [i,f='']=s.replace('-','').split('.');const n=Number(i)*100+Number((f+'00').slice(0,2));return s.startsWith('-')?-n:n;};
function fromProposal(){
 const sign=D.movement.amount_minor<0?-1:1;
 lines=D.proposal.lines.map(l=>({amount:l.amount_minor==null?'':(Math.abs(l.amount_minor)/100).toFixed(2),why_id:l.why_id||'',description:l.description||'',items:l.items||[]}));
 if(!lines.length)lines=[{amount:(Math.abs(D.movement.amount_minor)/100).toFixed(2),why_id:'',description:'',items:[]}];
 lines.sign=sign;
}
function payload(){
 const sign=D.movement.amount_minor<0?-1:1;
 return lines.map(l=>{const c=cents(l.amount);return {amount_minor:c==null||Number.isNaN(c)?null:sign*Math.abs(c),why_id:l.why_id||null,description:l.description,items:l.items};});
}
function renderLines(){
 const opts=w=>'<option value="">— WHY —</option>'+D.whys.map(y=>`<option value="${y.id}" ${String(y.id)===String(w)?'selected':''}>${esc(y.why)}</option>`).join('');
 $('sp-lines').innerHTML=lines.map((l,i)=>{const w=D.whys.find(y=>String(y.id)===String(l.why_id));
  return `<tr><td><input inputmode="decimal" aria-label="Amount" data-i="${i}" data-f="amount" value="${esc(l.amount)}"></td>
   <td><select aria-label="WHY" data-i="${i}" data-f="why_id">${opts(l.why_id)}</select></td><td><small>${esc(w?.what||'—')}</small></td>
   <td><input aria-label="Description" data-i="${i}" data-f="description" value="${esc(l.description)}"></td><td class="num">${l.items.length}</td>
   <td>${lines.length>1?`<button type="button" class="btn-secondary" data-del="${i}" aria-label="Remove line">✕</button>`:''}</td></tr>`;}).join('');
 totals();
}
function totals(){
 const p=payload(),total=D.movement.amount_minor,alloc=p.reduce((s,l)=>s+(l.amount_minor||0),0),diff=total-alloc;
 const missing=p.some(l=>l.amount_minor==null),nowhy=p.some(l=>!l.why_id);
 $('sp-total').textContent=money(total);$('sp-alloc').textContent=money(alloc);
 $('sp-diff').textContent=money(diff);$('sp-diff').className=diff?'sp-bad':'sp-ok';
 const ok=!diff&&!missing&&!nowhy&&p.length;
 $('sp-state').textContent=ok?'Complete':'Incomplete';
 const own=[];if(missing)own.push({label:'Importi di dettaglio mancanti',detail:'a line has no amount'});
 if(nowhy)own.push({label:'WHY mancante',detail:'a line has no WHY'});
 if(!missing&&diff)own.push({label:'Differenza non spiegata',detail:`${money(diff)} not allocated`});
 const prop=D.proposal.reasons.filter(r=>!['DETAIL_AMOUNTS_MISSING','ITEM_WHY_MISSING','DIFFERENCE_UNEXPLAINED'].includes(r.code));
 $('sp-reasons').innerHTML=(prop.length||own.length)?`<ul class="sp-bad">${reasons(prop.concat(own))}</ul>`:'<p class="sp-ok">The lines add up to the movement exactly.</p>';
 $('sp-confirm').disabled=!ok;
}
async function detail(){
 D=await api(`/bank/split/${txn}/data`);
 const mv=D.movement;
 $('sp-mv-h').textContent=`${mv.description}`;
 $('sp-mv').innerHTML=`<p><strong>${money(mv.amount_minor)}</strong> ${esc(mv.currency||'')} · ${esc(mv.date)} · ${esc(mv.source)} (${esc(mv.source_type||'')})<br>
  Source owner at the date: ${esc(mv.owner?.name||'not configured')} · WHOM of the lines: ${esc(D.whom?.name||'not known')}</p>`;
 const p=D.proposal,items=p.lines.flatMap(l=>l.items.map(it=>({...it,why:l.why})));
 $('sp-doc-count').textContent=items.length;
 $('sp-link').innerHTML=p.link?`<p>Link <span class="sp-pill">${esc(LINK[p.link.state]||p.link.state)}</span> by Charge Identifier ${esc(p.link.codes.join(', '))}
  · amount ${p.link.checks.amount?'equal':'different'} · date ${p.link.checks.date?'compatible':'not compatible'} · currency ${esc({OK:'equal',MISMATCH:'different',SOURCE_NOT_CONFIGURED:'not configured on the Source (report: USD)'}[p.link.checks.currency]||'—')}
  ${p.documents.length?`· file ${esc(p.documents.map(d=>d.file_name).join(', '))}`:''}</p>`:'<p class="sp-muted">No document is linked to this movement: the lines can still be entered by hand.</p>';
 $('sp-items').innerHTML=items.map(it=>`<tr><td>${esc(it.order_id)}</td><td>${esc(it.title)}${it.why?`<br><small class="sp-muted">WHY: ${esc(it.why)}</small>`:''}</td>
  <td><small>${esc([it.family,it.klass,it.commodity].filter(Boolean).join(' · '))}</small></td><td><small>${esc(it.category)}</small></td><td class="num">${esc(it.quantity)}</td>
  <td><small>${esc(it.file_name||'')} line ${esc(it.line)} · ${esc(it.asin)} · order total ${esc(it.order_net_total)}</small></td></tr>`).join('')||'<tr><td colspan="6" class="sp-muted">None.</td></tr>';
 if(D.draft){lines=D.draft.lines.map(l=>({amount:l.amount_minor==null?'':(Math.abs(l.amount_minor)/100).toFixed(2),why_id:l.why_id||'',description:l.description,items:l.items||[]}));
  $('sp-draft-note').textContent=`Draft #${D.draft.id} of ${String(D.draft.saved_at).slice(0,16)} loaded.`;}
 else fromProposal();
 renderLines();
 $('sp-saved').innerHTML=D.allocations.length?`<div class="table-wrap"><table><thead><tr><th class="num">Amount</th><th>WHY</th><th>WHAT</th><th>Description</th><th>Status</th></tr></thead><tbody>${D.allocations.map(a=>`<tr><td class="num">${money(a.amount_minor)}</td><td>${esc(a.why)}</td><td>${esc(a.what)}</td><td><small>${esc(a.description||'')}</small></td><td>${esc(a.status)} · ${esc(a.decision_source||'')}</td></tr>`).join('')}</tbody></table></div>
  <p>${esc(D.allocation_state.status)} · split ${money(D.allocation_state.allocated_minor)} · difference ${money(D.allocation_state.difference_minor)}</p>`:'<p class="sp-muted">No allocation is written for this movement.</p>';
 $('sp-qbo').innerHTML=D.qbo?`<p>${D.qbo.ready?'<span class="sp-ok">Ready</span>':`<span class="sp-bad">Blocked</span><ul>${reasons(D.qbo.blockers)}</ul>`}
  One Purchase, ${D.qbo.line_count} line(s), total ${money(D.qbo.total_minor)}, requestid <code>${esc(D.qbo.request_id)}</code>.</p><pre class="sp-json">${esc(JSON.stringify(D.qbo.payload,null,2))}</pre>`:'<p class="sp-muted">Confirm a split first.</p>';
}
function bind(){
 $('sp-lines').addEventListener('input',e=>{const i=e.target.dataset.i;if(i==null)return;lines[i][e.target.dataset.f]=e.target.value;if(e.target.dataset.f==='why_id')renderLines();else totals();});
 $('sp-lines').addEventListener('click',e=>{const i=e.target.dataset.del;if(i==null)return;const [gone]=lines.splice(i,1);lines[0].items=lines[0].items.concat(gone.items);renderLines();});
 $('sp-add').addEventListener('click',()=>{lines.push({amount:'',why_id:'',description:'',items:[]});renderLines();});
 $('sp-reset').addEventListener('click',()=>{fromProposal();renderLines();$('sp-draft-note').textContent='Proposal reloaded (the draft is kept).';});
 $('sp-draft').addEventListener('click',async()=>{try{const r=await api(`/bank/split/${txn}/draft`,[['lines',JSON.stringify(payload())]]);toast(`Draft #${r.draft_id} kept. Nothing is allocated.`);}catch(e){toast(e.message);}});
 $('sp-confirm').addEventListener('click',()=>{const p=payload();
  $('sp-dialog-text').textContent=`${p.length} line(s) for ${money(D.movement.amount_minor)} will be written as the allocations of this movement, replacing any existing ones. WHAT comes from each WHY; WHOM is ${D.whom?.name||'unknown'}.`;
  $('sp-dialog').showModal();});
 $('sp-dialog-ok').addEventListener('click',async()=>{try{const link=D.proposal.link;
  const r=await api(`/bank/split/${txn}/confirm`,[['lines',JSON.stringify(payload())],['confirm','yes'],['evidence_kind',link?'AMAZON_ORDER':'SPLIT'],['evidence_reference',link?link.codes.join(', '):'']]);
  $('sp-dialog').close();toast(`Split confirmed: ${r.lines} line(s).`);await detail();}catch(e){$('sp-dialog').close();toast(e.message);}});
}
if(txn){bind();detail().catch(e=>toast(e.message));}else list().catch(e=>toast(e.message));
})();
