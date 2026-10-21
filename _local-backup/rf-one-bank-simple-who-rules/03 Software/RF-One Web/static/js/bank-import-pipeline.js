(() => {
 const cells=[...document.querySelectorAll('[data-pipeline-id]')];if(!cells.length)return;
 const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const labels={QUEUED:'Queued',RUNNING:'In progress',MATCHED:'Reconciled',PROPOSED:'Needs review',AMBIGUOUS:'Needs clarification',ERROR:'Retry needed',STALE:'Needs review',SKIPPED:'Skipped'};
 async function refresh(){
  try{
   const response=await fetch('/bank/import-reconciliation/status?ids='+cells.map(c=>c.dataset.pipelineId).join(','),{cache:'no-store'});
   if(!response.ok)return;const data=await response.json();if(!data.ok)return;
   for(const item of data.items){
    const cell=cells.find(c=>c.dataset.pipelineId===String(item.id));if(!cell)continue;
    const p=item.proposal;
    cell.innerHTML=`<small>${escape(labels[item.status]||item.status)}</small>${item.error?`<details><summary>Reason</summary><p>${escape(item.error)}</p></details>`:''}${p?`<details><summary>View suggestion</summary><p>${escape(p.probable_who||p.who||'WHO to review')} · ${escape(p.summary)}</p>${p.suggested_why?`<p>WHY: ${escape(p.suggested_why)}</p>`:''}${(p.sources||[]).map(s=>`<a href="${escape(s.url)}" target="_blank" rel="noopener">${escape(s.title)} ↗</a>`).join(' · ')}<p><a href="/bank/ai-rules?transaction_id=${item.id}">Discuss</a></p></details>`:''}${item.status==='ERROR'?`<button type="button" class="btn-secondary" data-pipeline-retry="${item.id}">Retry</button>`:''}`;
   }
   document.querySelectorAll('[data-pipeline-retry]').forEach(b=>b.addEventListener('click',async()=>{
    b.disabled=true;const csrf=document.querySelector('input[name="csrf_token"]')?.value||document.querySelector('meta[name="bank-csrf"]')?.content;
    try{const result=await fetch(`/bank/import-reconciliation/${b.dataset.pipelineRetry}/retry`,{method:'POST',body:new URLSearchParams({csrf_token:csrf||''})});const answer=await result.json();if(!answer.ok)throw Error(answer.error);refresh();}
    catch(error){b.textContent=error.message;b.disabled=false;}
   }));
   if(data.items.some(i=>['QUEUED','RUNNING'].includes(i.status)))setTimeout(refresh,5000);
  }catch{/* a failed status read never alters a transaction */}
 }
 refresh();
})();
