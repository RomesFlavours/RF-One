// --- Review > rules of every scope, WHO category and declarations (BANK_RULE_SCOPE_AND_WHO_CATEGORY_001) --------
// One implementation for both languages (RT is the dictionary of the page). Inside the Review window of a group:
// the WHO's category (AI proposal with evidence, a person's confirmation) and contextual declarations; the WHY
// rules of every scope that concern the WHO; one rule lifecycle: define -> simulate -> save draft, or save and
// apply now. Every edit invalidates the simulation; nothing is saved without the person's confirmation.
const RK={};
function rkKey(){return W.who?String(W.who):'';}
async function loadRules(force){const k=rkKey();if(!k)return;if(RK[k]&&!force){W.rk=RK[k];return;}
 W.rk={loading:true};
 try{const r=await fetch(B+`/api/who/${k}/rules?run_id=${runId}`,{headers:{'X-CBank-Token':token}});const v=await r.json();if(!r.ok||v.ok===false)throw Error(v.error||r.statusText);RK[k]=W.rk=v;}
 catch(e){W.rk={error:e.message};}
 if(wiz.open&&rkKey()===k)renderWizard();}
const catLabel=c=>(RT.cats[c]||c);
function rulesPanel(){if(!W.who)return '';if(!W.rk){loadRules();return `<section class="gpanel" id="rules-panel"><p class="m">${RT.loading}</p></section>`;}
 const k=W.rk;let h=`<section class="gpanel" id="rules-panel"><h4 style="margin:2px 0 6px">${RT.title} <button class="sec hq" type="button" data-help="h-rules" aria-label="${RT.helpRules}">?</button></h4>`;
 if(k.loading)return h+`<p class="m">${RT.loading}</p></section>`;
 if(k.error)return h+`<p class="neg">${esc(k.error)}</p><button class="sec" type="button" data-ract="reload">${RT.retry}</button></section>`;
 // category
 const c=k.category;h+=`<div class="sub"><b>${RT.category}</b> <button class="sec hq" type="button" data-help="h-category" aria-label="${RT.helpCategory}">?</button><br>`;
 if(!c)h+=`<span class="m">${RT.noCategory}</span>`;
 else{h+=`<span class="st ${c.status==='CONFIRMED'?'st-ok':c.status==='REJECTED'?'st-lim':'st-new'}">${RT.catStatus[c.status]}</span> <b>${esc(catLabel(c.category))}</b> · ${RT.certainty}: ${RT.cert[c.certainty]||c.certainty} · ${RT.origin[c.origin]||c.origin}`;
  if(c.evidence)h+=`<br><span class="m">${esc(c.evidence)}</span>`;
  if((c.sources||[]).length)h+=`<br>${c.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(' · ')}`;
  if(c.status==='PROPOSED')h+=`<div class="row" style="margin-top:4px"><button type="button" data-ract="cat-confirm">${RT.confirm}</button><button class="sec" type="button" data-ract="cat-reject">${RT.reject}</button></div>`;}
 h+=`<div class="row" style="margin-top:6px"><button class="sec" type="button" data-ract="cat-propose">${RT.propose}</button>
  <select id="r-cat-choose" aria-label="${RT.chooseCat}"><option value="">${RT.chooseCat}</option>${k.categories.map(x=>`<option value="${x.code}">${esc(catLabel(x.code))}</option>`).join('')}</select>
  <button class="sec" type="button" data-ract="cat-choose">${RT.confirmChosen}</button></div><p class="m" style="margin:2px 0">${RT.catNote}</p></div>`;
 // declarations
 h+=`<div class="sub"><b>${RT.declarations}</b>`;
 h+=k.declarations.length?`<ul style="margin:4px 0">${k.declarations.map(d=>`<li>«${esc(d.text)}» → ${esc(catLabel(d.category))} · ${RT.onSources}: ${esc(d.source_ids.map(i=>(k.sources.find(s=>s.id===i)||{name:'#'+i}).name).join(', '))} <button class="sec" type="button" data-ract="decl-withdraw" data-id="${d.record_id}">${RT.withdraw}</button> <button class="sec" type="button" data-ract="decl-rule" data-id="${d.record_id}">${RT.ruleFromDecl}</button></li>`).join('')}</ul>`:`<br><span class="m">${RT.noDecl}</span>`;
 h+=`<details id="r-decl" style="margin-top:4px" ${W.declOpen?'open':''}><summary>${RT.addDecl}</summary><label>${RT.declText}<br><textarea id="r-decl-text" rows="2" style="width:100%">${esc(W.declDraft||'')}</textarea></label>
  <label>${RT.declCat} <select id="r-decl-cat">${k.categories.map(x=>`<option value="${x.code}">${esc(catLabel(x.code))}</option>`).join('')}</select></label>
  <div>${RT.declSources}: ${k.sources.map(s=>`<label style="margin-right:10px"><input type="checkbox" data-decl-src value="${s.id}" checked> ${esc(s.name)} (${RT.subject[s.subject]||s.subject||'—'})</label>`).join('')}</div>
  <button type="button" data-ract="decl-save">${RT.declSave}</button><p class="m">${RT.declNote}</p></details></div>`;
 // rules of every scope
 h+=`<div class="sub"><b>${RT.rules}</b>`;
 h+=k.rules.length?`<table><tbody>${k.rules.map(r=>`<tr><td>${RT.scope[r.scope]}</td><td><span class="b ${r.status==='ACTIVE'?'RECONCILED':''}">${RT.status[r.status]||r.status}</span></td><td>#${r.id} v${r.version} — ${esc(r.text)}</td><td><button class="sec" type="button" data-ract="revise" data-id="${r.id}">${RT.revise}</button></td></tr>`).join('')}</tbody></table>`:`<br><span class="m">${RT.noRules}</span>`;
 if((k.replacements||[]).length)h+=`<details><summary>${RT.replacements}</summary><ul>${k.replacements.map(x=>`<li>${RT.replacedBy(x)} ${x.restored?`<span class="m">${RT.restored}</span>`:`<button class="sec" type="button" data-ract="restore" data-id="${x.record_id}">${RT.restore}</button>`}</li>`).join('')}</ul></details>`;
 h+=`<div class="row" style="margin-top:6px"><button class="sec" type="button" data-ract="new">${RT.newRule}</button>${W.shell?`<button class="sec" type="button" data-ract="profile">${RT.profileEditor}</button>`:''}</div>${W.shell?`<p class="m" style="margin:2px 0">${RT.profileNote}</p>`:''}</div>`;
 if(W.ed)h+=editorPanel();
 return h+`<p class="m" data-rstatus role="status">${esc(W.rmsg||'')}</p></section>`;}
function newEditor(base){const k=W.rk||{};W.ed=Object.assign({scope:'WHO',category:null,why_id:null,conditions:[],exceptions:[],title:'',replace:[],keep:[],sim:null},base||{});
 if(W.ed.scope==='CATEGORY'&&!W.ed.category)W.ed.category=whoCategories()[0]||null;W.rmsg='';}
function whoCategories(){const k=W.rk||{},out=[];if(k.category&&k.category.status==='CONFIRMED')out.push(k.category.category);(k.declarations||[]).forEach(d=>{if(!out.includes(d.category))out.push(d.category);});
 return out.filter(c=>!((k.categories||[]).find(x=>x.code===c)||{}).heterogeneous);}
function edSpec(){const e=W.ed,s={scope:e.scope,why_id:e.why_id,conditions:e.conditions,exceptions:e.exceptions.map(x=>({conditions:x}))};
 if(e.scope==='WHO')s.who_ids=[+W.who];if(e.scope==='CATEGORY')s.categories=e.category?[e.category]:[];if(!s.exceptions.length)delete s.exceptions;return s;}
function editorPanel(){const e=W.ed,k=W.rk,cats=whoCategories(),why=(k.whys||[]).find(x=>x.id===e.why_id);
 let h=`<div class="sub ed" id="rule-editor"><b>${RT.editor}</b> <button class="sec hq" type="button" data-help="h-rules" aria-label="${RT.helpRules}">?</button>`;
 h+=`<div class="row">${['WHO','CATEGORY','GENERAL'].map(s=>`<label><input type="radio" name="r-scope" value="${s}" ${e.scope===s?'checked':''} ${s==='CATEGORY'&&!cats.length?'disabled':''}> ${RT.scopeChoice[s](k.who,cats)}</label>`).join(' ')}</div>`;
 if(e.scope==='CATEGORY')h+=`<label>${RT.category} <select id="r-ed-cat">${cats.map(c=>`<option value="${c}" ${c===e.category?'selected':''}>${esc(catLabel(c))}</option>`).join('')}</select></label>`;
 h+=`<div><label>WHY <select id="r-ed-why"><option value="">${RT.chooseWhy}</option>${(k.whys||[]).map(w=>`<option value="${w.id}" ${w.id===e.why_id?'selected':''}>${esc(w.name)}</option>`).join('')}</select></label> → WHAT <b>${esc(why?(why.what||RT.balance):'—')}</b> <span class="m">${RT.whatFromWhy}</span></div>`;
 h+=`<div><b>${RT.conditions}</b><ul style="margin:2px 0">${e.conditions.map((c,i)=>`<li>${esc(RT.cond(c))} <button class="sec" type="button" data-ract="cond-del" data-i="${i}" aria-label="${RT.remove}">✕</button></li>`).join('')||`<li class="m">${RT.noConditions}</li>`}</ul>
  <div class="row"><select id="r-ed-subject"><option value="">${RT.addSubject}</option><option value="Personal">${RT.subject.Personal}</option><option value="Company">${RT.subject.Company}</option></select>
  <input id="r-ed-contains" placeholder="${RT.descContains}"><button class="sec" type="button" data-ract="cond-add">${RT.add}</button></div></div>`;
 h+=`<div><b>${RT.exceptions}</b><ul style="margin:2px 0">${e.exceptions.map((x,i)=>`<li>${RT.except} ${esc(x.map(c=>RT.cond(c)).join(RT.and))} <button class="sec" type="button" data-ract="exc-del" data-i="${i}" aria-label="${RT.remove}">✕</button></li>`).join('')||`<li class="m">${RT.noExceptions}</li>`}</ul>
  <div class="row"><input id="r-ed-exc" placeholder="${RT.excContains}"><button class="sec" type="button" data-ract="exc-add">${RT.add}</button></div></div>`;
 h+=`<label>${RT.ruleTitle} <input id="r-ed-title" value="${esc(e.title)}" style="width:60%"></label>`;
 h+=`<div class="row" style="margin-top:6px"><button type="button" data-ract="simulate">${RT.simulate}</button><button class="sec" type="button" data-ract="ed-close">${RT.closeEditor}</button></div>`;
 if(e.simErr)h+=`<p class="neg">${esc(e.simErr)}</p>`;
 if(e.busy)h+=`<p><span class="st st-run">${RT.simulating}</span></p>`;
 if(e.sim){const s=e.sim,sm=s.summary;
  h+=`<div class="okbox"><b>${RT.simTitle}</b> — ${esc(RT.ruleText(s))}<br>${RT.simSummary(s)}<br><span class="m">${RT.verifiedOn}</span></div>`;
  if(s.rules.length)h+=`<table><thead><tr><th>${RT.otherRule}</th><th>${RT.relation}</th><th>${RT.decision}</th></tr></thead><tbody>${s.rules.map(r=>`<tr><td>${RT.scope[r.scope]} #${r.rule_id} — ${esc(r.text)}</td><td>${RT.kind[r.kind]}${r.kind==='EQUIVALENT'?` · ${r.future?RT.futureYes:RT.futureNo}`:''}<br><span class="m">${RT.kindCounts(r)}</span></td>
   <td>${r.replaceable?`<label><input type="checkbox" data-rrep="${r.rule_id}" ${e.replace.includes(r.rule_id)?'checked':''}> ${RT.replaceIt}</label>`:''}${r.keepable?`<label><input type="checkbox" data-rkeep="${r.rule_id}" ${e.keep.includes(r.rule_id)?'checked':''}> ${RT.keepIt}</label>`:''}</td></tr>`).join('')}</tbody></table>`;
  h+=`<details><summary>${RT.movesTitle(s)}</summary><div style="overflow:auto;max-height:36vh"><table><tbody>${s.rows.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.description)}</td><td class="num">${usd(x.amount_minor)}</td><td>${esc(x.source||'')}</td><td class="m">${esc(x.before||'—')} → ${esc(x.after||'—')} · ${RT.effect[x.effect]}${x.in_group?' · '+RT.inGroup:''}</td></tr>`).join('')}</tbody></table></div></details>`;
  const changes=sm.new_why+sm.changed_why+sm.lost_why;
  h+=s.open_conflicts?`<p class="neg">${RT.conflictsOpen(s.open_conflicts)}</p>`:'';
  h+=`<div class="row"><button class="sec" type="button" data-ract="save-draft">${RT.saveDraft}</button><button type="button" data-ract="save-apply" ${s.open_conflicts?'disabled':''}>${RT.saveApply(changes)}</button></div><p class="m">${RT.saveNote}</p>`;}
 return h+'</div>';}
function invalidate(){if(W.ed){W.ed.sim=null;W.ed.simErr=null;}}
function readEditorInputs(){const e=W.ed;if(!e)return;const t=$('#r-ed-title');if(t)e.title=t.value;}
async function simulateRule(){const e=W.ed;readEditorInputs();e.busy=true;e.sim=null;e.simErr=null;renderWizard();
 try{e.sim=await post(B+`/api/runs/${runId}/rules/simulate`,{exc:W.g.exc,group:W.g.group,spec:JSON.stringify(edSpec()),replace:JSON.stringify(e.replace),keep:JSON.stringify(e.keep)});}
 catch(x){e.simErr=uiMessage(x.message);}e.busy=false;if(wiz.open)renderWizard();}
async function saveRule(mode){const e=W.ed,s=e.sim;if(!s)return;readEditorInputs();
 const sm=s.summary,changes=sm.new_why+sm.changed_why+sm.lost_why;
 if(mode==='APPLY'&&!confirm(RT.confirmApply(s,changes)))return;
 W.rmsg=RT.saving;renderWizard();
 try{const v=await post(B+`/api/runs/${runId}/rules/save`,{exc:W.g.exc,group:W.g.group,spec:JSON.stringify(edSpec()),replace:JSON.stringify(e.replace),keep:JSON.stringify(e.keep),token:s.token,mode,title:e.title});
  if(mode==='APPLY'){try{sessionStorage.setItem('cbank-wiz-next',JSON.stringify({exc:W.g.exc,group:W.g.group,y:window.scrollY,msg:RT.applied(v)}));}catch{}location.reload();return;}
  W.ed=null;W.rmsg=RT.drafted(v);await loadRules(true);}
 catch(x){W.rmsg=uiMessage(x.message);if(e)e.sim=null;renderWizard();}}
async function rAct(b){const a=b.dataset.ract,k=W.rk,id=+b.dataset.id;
 const call=async(url,data,msg)=>{W.rmsg=RT.working;renderWizard();try{const v=await post(B+url,data);W.rmsg=msg?msg(v):'';await loadRules(true);}catch(x){W.rmsg=uiMessage(x.message);renderWizard();}};
 if(a==='reload')return loadRules(true);
 if(a==='cat-propose')return call(`/api/who/${W.who}/category`,{action:'propose'},v=>v.proposed?RT.proposed:RT.noneSupported);
 if(a==='cat-confirm')return call(`/api/who/${W.who}/category`,{action:'confirm'});
 if(a==='cat-reject')return call(`/api/who/${W.who}/category`,{action:'reject'});
 if(a==='cat-choose'){const c=$('#r-cat-choose').value;if(!c)return;return call(`/api/who/${W.who}/category`,{action:'choose',category:c});}
 if(a==='decl-save'){const ids=[...document.querySelectorAll('[data-decl-src]:checked')].map(x=>+x.value);
  return call(`/api/who/${W.who}/declaration`,{text:$('#r-decl-text').value,category:$('#r-decl-cat').value,source_ids:JSON.stringify(ids)},()=>{W.declDraft='';W.declOpen=false;return RT.declared;});}
 if(a==='decl-withdraw')return call(`/api/declarations/${id}/withdraw`,{});
 if(a==='decl-rule'){const d=k.declarations.find(x=>x.record_id===id);const subj=[...new Set(d.source_ids.map(i=>(k.sources.find(s=>s.id===i)||{}).subject).filter(Boolean))];
  newEditor({scope:'CATEGORY',category:d.category,conditions:subj.length===1?[{field:'subject',op:'is',value:subj[0]}]:[]});W.rmsg=RT.fromDecl(subj);return renderWizard();}
 if(a==='restore')return call(`/api/rules/replacements/${id}/restore`,{run_id:runId},()=>RT.restoredMsg);
 if(a==='new'){newEditor();return renderWizard();}
 if(a==='profile')return defineRule(null);
 if(a==='revise'){const r=k.rules.find(x=>x.id===id),s=r.spec;newEditor({scope:s.scope,category:(s.categories||[])[0]||null,why_id:s.why_id||null,conditions:s.conditions||[],
  exceptions:(s.exceptions||[]).filter(x=>!x.kept_apart).map(x=>x.conditions),replace:r.status==='ACTIVE'?[r.id]:[],title:''});W.rmsg=RT.revising(r);return renderWizard();}
 if(a==='ed-close'){W.ed=null;return renderWizard();}
 if(a==='simulate')return simulateRule();
 if(a==='save-draft')return saveRule('DRAFT');
 if(a==='save-apply')return saveRule('APPLY');
 const e=W.ed;if(!e)return;readEditorInputs();
 if(a==='cond-del')e.conditions.splice(+b.dataset.i,1);
 if(a==='exc-del')e.exceptions.splice(+b.dataset.i,1);
 if(a==='cond-add'){const s=$('#r-ed-subject').value,t=$('#r-ed-contains').value.trim();if(s)e.conditions.push({field:'subject',op:'is',value:s});if(t)e.conditions.push({field:'description',op:'contains',value:t});}
 if(a==='exc-add'){const t=$('#r-ed-exc').value.trim();if(t)e.exceptions.push([{field:'description',op:'contains',value:t}]);}
 invalidate();renderWizard();}
function bindRulesPanel(){document.querySelectorAll('[data-ract]').forEach(b=>b.onclick=()=>rAct(b));
 const dt=$('#r-decl-text');if(dt)dt.oninput=()=>{W.declDraft=dt.value;};const dd=$('#r-decl');if(dd)dd.ontoggle=()=>{W.declOpen=dd.open;};
 const e=W.ed;if(!e)return;
 document.querySelectorAll('input[name=r-scope]').forEach(r=>r.onchange=()=>{readEditorInputs();e.scope=r.value;if(e.scope==='CATEGORY'&&!e.category)e.category=whoCategories()[0]||null;e.replace=[];e.keep=[];invalidate();renderWizard();});
 const c=$('#r-ed-cat');if(c)c.onchange=()=>{readEditorInputs();e.category=c.value;invalidate();renderWizard();};
 const w=$('#r-ed-why');if(w)w.onchange=()=>{readEditorInputs();e.why_id=+w.value||null;invalidate();renderWizard();};
 const t=$('#r-ed-title');if(t)t.oninput=()=>{e.title=t.value;};
 document.querySelectorAll('[data-rrep]').forEach(x=>x.onchange=()=>{readEditorInputs();const i=+x.dataset.rrep;e.replace=x.checked?[...e.replace,i]:e.replace.filter(y=>y!==i);invalidate();renderWizard();});
 document.querySelectorAll('[data-rkeep]').forEach(x=>x.onchange=()=>{readEditorInputs();const i=+x.dataset.rkeep;e.keep=x.checked?[...e.keep,i]:e.keep.filter(y=>y!==i);invalidate();renderWizard();});}
// Contextual help: the "?" of a window or panel opens the guide at its own section, on top of the window
// (a dialog over the dialog), so fields, drafts, selection and position stay as they are.
function openHelp(id,from){help.showModal();const el=document.getElementById(id);if(el){el.scrollIntoView({block:'start'});el.classList.add('hl');setTimeout(()=>el.classList.remove('hl'),1600);}
 help.dataset.back=from&&from.id||'';W.helpFrom=from||null;}
document.addEventListener('click',ev=>{const b=ev.target.closest('[data-help]');if(b){ev.preventDefault();openHelp(b.dataset.help,b);}});
help.addEventListener('close',()=>{if(W.helpFrom&&document.contains(W.helpFrom))W.helpFrom.focus();W.helpFrom=null;});
