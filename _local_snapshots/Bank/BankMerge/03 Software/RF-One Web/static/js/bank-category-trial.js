(() => {
'use strict';
const by = id => document.getElementById(id);
const data = JSON.parse(by('trial-data').textContent);
const key = 'bankmerge.category-trial.v1';
let categories = data.defaults;
try { const saved = JSON.parse(localStorage.getItem(key)); if (Array.isArray(saved)) categories = saved; } catch {}
const tests = {direct:'Comando diretto',lookup:'Confronto con le fonti',check:'Assegno con numero', text:'Testo nella descrizione',employee:'Nome nell’anagrafica dipendenti',
 adp:'Pagamento ADP: persona, importo esatto e data',restaurant:'Ricerca internet · ristorante',fuel:'Ricerca internet · carburante',ev:'Ricerca internet · ricarica EV'};
const actions = {next:'Prosegui al livello successivo',manual:'Riconcilio manuale',why:'Assegna un WHY',payroll:'Payroll secondo il ruolo',dining:'Ristorazione · WHY secondo il titolare'};
function el(tag, text) { const n=document.createElement(tag); if(text!=null)n.textContent=text; return n; }
function button(label, click) { const b=el('button',label); b.type='button'; b.className='btn-secondary'; b.onclick=click; return b; }
function changed() { try {localStorage.setItem(key,JSON.stringify(categories));} catch {by('storage-message').textContent='Bozza disponibile solo in questa pagina.';} }
function words(level) {
 const days = level.days ?? 0;
 const conditions = {
  check:'Controlla se la descrizione inizia con CHECK o CHEQUE seguito dal numero di assegno.',
  text:'Controlla se la descrizione contiene le parole «'+(level.value || '')+'».',
  employee:'Confronta il WHO già riconosciuto con l’anagrafica dipendenti. Se il WHO manca, cerca il nome completo nella descrizione.',
  adp:'Nel report ADP cerca un solo pagamento per il dipendente del passaggio precedente, con lo stesso importo netto in uscita e data entro ±'+days+' giorni.',
  restaurant:'Verifica dalle ricerche internet disponibili se l’esercente ancora irrisolto è un ristorante.',
  fuel:'Verifica dalle ricerche internet disponibili se il pagamento è un acquisto di carburante.',
  ev:'Verifica dalle ricerche internet disponibili se il pagamento è una ricarica elettrica.'
 };
 const outcomes = {next: level.test==='employee' ? 'Conserva il dipendente e il ruolo valido alla data del movimento, poi prosegui.' : 'Prosegui al passaggio successivo.',
  why:'Assegna il WHY «'+(level.why || '')+'».', manual:'Destina il movimento al riconcilio manuale.',
  dining:'Classifica come Ristorazione e usa il WHY personale o aziendale secondo il titolare.',
  payroll:'Usa il ruolo conservato per il ristorante del pagamento ADP e assegna il WHY payroll FOH, BOH o Manager. Se il riscontro non è univoco, passa al manuale.'};
 return [conditions[level.test] || '',outcomes[level.action] || ''];
}
function instruction(level) {
 if (typeof level.command === 'string') return level.command;
 const [condition,outcome]=words(level);
 return [level.condition ?? condition,level.outcome ?? outcome].filter(Boolean).join(' ');
}
function command(value, oninput){
 const n=el('textarea');n.rows=2;n.maxLength=4000;n.value=value;n.oninput=()=>oninput(n.value);return n;
}
function input(value,fn){const n=el('input'); n.value=value||''; n.oninput=()=>fn(n.value); return n;}
function field(label, control){const n=el('label',label); n.append(control); return n;}

function chooseWhy(description, owner){
 const start=description.selectionStart,end=description.selectionEnd;
 const dialog=el('dialog');dialog.className='rule-dialog why-dialog';
 dialog.setAttribute('aria-label','Scegli un WHY esistente');
 const head=el('header');head.className='rule-head';
 const help=button('?');help.dataset.howWorks='category-trial-editor';help.setAttribute('aria-label','Come inserire un WHY');
 head.append(el('h2','Scegli un WHY'),help,button('Chiudi',()=>dialog.close()));
 const body=el('div');body.className='rule-body';
 const search=el('input');search.type='search';
 const list=el('select');list.size=10;list.setAttribute('aria-label','WHY esistenti');
 const message=el('p');message.setAttribute('role','status');
 const insert=button('Inserisci nel passaggio',()=>{
  if(!list.value)return;
  const value='«'+list.value+'»';
  if(description.value.length-(end-start)+value.length>description.maxLength){message.textContent='Il testo del passaggio supera il limite di 4000 caratteri.';return;}
  description.setRangeText(value,start,end,'end');
  description.dispatchEvent(new Event('input',{bubbles:true}));
  dialog.close();
 });
 function filter(){
  list.replaceChildren();
  for(const why of data.whys.filter(w=>w.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))){
   const option=el('option',why);option.value=why;list.append(option);
  }
  list.selectedIndex=list.options.length?0:-1;insert.disabled=!list.value;
  message.textContent=list.options.length?'':'Nessun WHY trovato.';
 }
 search.oninput=filter;list.onchange=()=>{insert.disabled=!list.value;};
 body.append(field('Cerca WHY',search),list,message,insert);dialog.append(head,body);owner.append(dialog);
 dialog.addEventListener('close',()=>{dialog.remove();description.focus();},{once:true});
 filter();dialog.showModal();search.focus();
}

function redraw(i){changed();render(i);}
function render(open=-1){
 const root=by('categories');root.replaceChildren();
 categories.forEach((cat,i)=>{
  const row=el('section');row.className='category-row';
  const info=el('div'),title=el('h3'),description=el('p');info.append(title,description);
  const dialog=el('dialog');dialog.className='rule-dialog';
  const head=el('header');head.className='rule-head';
  const heading=el('h2');heading.id='rule-title-'+i;dialog.setAttribute('aria-labelledby',heading.id);
  const help=button('?');help.dataset.howWorks='category-trial-editor';help.setAttribute('aria-label','Come formulare la regola');
  const close=button('Chiudi',()=>dialog.close());head.append(heading,help,close);
  const panel=el('div');panel.className='rule-body';dialog.append(head,panel);
  function updateSummary(){
   title.textContent=heading.textContent=cat.name;
   const phrases=cat.levels.map(l=>{
    const step=l.compiled?.step || l;
    if(step.test==='lookup')return l.compiled?.explanation || instruction(l);
    if(!l.compiled && (l.command || l.condition || l.outcome))return instruction(l);
    return [tests[step.test],step.action==='why'?step.why:step.action==='next'?'':actions[step.action]].filter(Boolean).join(' → ');
   }).filter(Boolean);
   description.textContent=phrases.join('. ') || 'Regola da formulare.';
  }
  const launch=button('Apri regola',()=>dialog.showModal());row.append(info,launch);
  dialog.addEventListener('close',()=>{updateSummary();launch.focus();});
  const name=input(cat.name,v=>{cat.name=v;updateSummary();invalidate();changed();});
  panel.append(field('Categoria',name));
  const invalidate=categoryActions(cat,panel);updateSummary();
  const tools=el('div');tools.className='actions';
  for(const [label,step] of [['Sposta su',-1],['Sposta giù',1]]){const j=i+step;const b=button(label,()=>{[categories[i],categories[j]]=[categories[j],categories[i]];redraw(j);});b.disabled=j<0||j>=categories.length;tools.append(b);}
  tools.append(button('Rimuovi categoria',()=>{categories.splice(i,1);redraw();}));panel.append(tools);
  root.append(row,dialog);if(i===open)dialog.showModal();
 });
}
async function post(path,params){
 const r=await fetch(location.pathname+'/'+path,{method:'POST',body:new URLSearchParams({csrf_token:data.csrf,...params})});
 const value=await r.json();if(!r.ok)throw Error(value.error||'Richiesta non riuscita.');return value;
}
by('add').onclick=()=>{categories.push({name:'Nuova categoria',levels:[{command:''}]});redraw(categories.length-1);};
function categoryActions(cat,panel){
 // Recover saved drafts created with the former category-wide editor.
 if ('goal' in cat) {
  const generated=cat.generated?.categories?.[0]?.levels;
  if(generated?.length)cat.levels=generated.map(level=>({command:instruction(level)}));
  else if(cat.goal?.trim())cat.levels=[{command:cat.goal}];
  delete cat.goal;delete cat.generated;
 }
 if(!cat.levels.length)cat.levels.push({command:''});
 let revision=0, reviewed=null;
 const message=el('p');message.setAttribute('role','status');
 const out=el('section');out.hidden=true;
 const simulateButton=button('Simula');
 let editing=false;
 let simulating=false;
 const coherence=el('p');coherence.setAttribute('role','status');
 function refresh(){

  const seen=new Set();
  const complete=cat.levels.every(l=>l.compiled?.step && l.compiled.ticket);
  let issue='';
  cat.levels.forEach((level,index)=>{
   const step=level.compiled?.step;
   if(!complete || issue)return;
   if(step.test==='adp' && !seen.has('employee'))issue='Identifica prima il dipendente.';
   seen.add(step.test);
   if(step.test==='lookup' && step.action==='next' && step.sources?.some(source=>source.endsWith('.employees')))seen.add('employee');
   if(!issue && ((step.action==='payroll' && !seen.has('adp')) || (step.action==='dining' && !seen.has('restaurant'))))issue='Manca il riscontro richiesto per questo esito.';
   if(issue)issue='Passaggio '+(index+1)+': '+issue;
  });
  const missing=cat.levels.flatMap((level,i)=>level.compiled?.ticket ? [] : [i+1]);
  coherence.textContent=issue || (missing.length ? 'Da generare o completare: '+missing.join(', ')+'.' : '');
  reviewed=complete && !issue ? {steps:cat.levels.map(l=>l.compiled),categories:[{name:cat.name,levels:cat.levels.map(l=>l.compiled.step)}]} : null;
  simulateButton.disabled=simulating || editing || !reviewed;
 }
 function invalidate(index){
  revision++;
  if(index!==undefined){
   delete cat.levels[index].compiled;
  }
  out.hidden=true;message.textContent='';refresh();changed();
 }
 const table=el('table');
 const editor=el('section');editor.hidden=true;editor.className='step-editor';
 const editorTitle=el('h3'),summary=el('textarea');summary.readOnly=true;summary.rows=3;
 const transcript=el('div');transcript.className='step-chat';transcript.setAttribute('role','log');
 const composer=command('',()=>syncEditor());composer.rows=3;
 const status=el('p');status.setAttribute('role','status');
 const send=button('Invia',sendMessage),save=button('Salva passaggio',saveStep);
 const why=button('WHY',()=>chooseWhy(composer,panel.closest('dialog')));
 const cancel=button('Chiudi passaggio',closeEditor);
 const controls=el('div');controls.className='actions';controls.append(send,why,save,cancel);
 editor.append(editorTitle,field('Passaggio in lavorazione',summary),transcript,field('Messaggio',composer),controls,status);
 let active=-1,history=[],ready=false,pending=false;
 function syncEditor(){
  send.disabled=pending || !composer.value.trim();
  save.disabled=pending || !ready || !!composer.value.trim();
  cancel.disabled=pending;composer.disabled=pending;why.disabled=pending;
  table.querySelectorAll('button').forEach(b=>b.disabled=pending);
  add.disabled=pending || cat.levels.length>=20;
 }
 function showHistory(){
  transcript.replaceChildren();
  for(const turn of history){const bubble=el('div');bubble.className='chat-'+turn.role;
   bubble.append(el('strong',turn.role==='user'?'Tu':'AI'),el('p',turn.content));transcript.append(bubble);}
  transcript.scrollTop=transcript.scrollHeight;
 }
 function openEditor(index){
  active=index;const level=cat.levels[index];
  history=structuredClone(level?.conversation || []);
  summary.value=level?.summary || (level ? instruction(level) : '');
  composer.value='';ready=false;status.textContent='';
  editorTitle.textContent='Passaggio '+(index+1);
  editing=true;editor.hidden=false;showHistory();syncEditor();refresh();
  editor.scrollIntoView({block:'nearest'});composer.focus();
 }
 function closeEditor(){editing=false;editor.hidden=true;active=-1;refresh();}
 function drawTable(){
  table.replaceChildren();const header=el('tr');
  for(const title of ['Passaggio','Descrizione',''])header.append(el('th',title));table.append(header);
  cat.levels.forEach((level,index)=>{const row=el('tr'),actions=el('td');
   row.append(el('td',index+1),el('td',level.summary || instruction(level) || 'Da definire'));
   actions.append(button('Modifica',()=>openEditor(index)));
   if(cat.levels.length>1)actions.append(button('Rimuovi passaggio',()=>{
    cat.levels.splice(index,1);closeEditor();invalidate();drawTable();syncEditor();
   }));row.append(actions);table.append(row);
  });
 }
 async function sendMessage(){
  if(pending || !composer.value.trim())return;
  history.push({role:'user',content:composer.value.trim()});composer.value='';ready=false;
  pending=true;status.textContent='L’AI sta leggendo il passaggio…';showHistory();syncEditor();
  try{
   const r=await post('chat',{name:cat.name,history:JSON.stringify(history),current:summary.value,
    context:JSON.stringify(cat.levels.slice(0,active).map(l=>l.summary || instruction(l)))});
   history.push({role:'assistant',content:r.reply});summary.value=r.summary;ready=r.ready;
   status.textContent=ready?'Se corrisponde alla tua richiesta, premi Salva passaggio.':'Rispondi nella chat per chiarire il passaggio.';
  }catch(e){status.textContent=e.message;}
  finally{pending=false;showHistory();syncEditor();composer.focus();}
 }
 async function saveStep(){
  if(pending || !ready || composer.value.trim())return;
  pending=true;status.textContent='Traduzione e salvataggio del passaggio…';syncEditor();
  try{
   const r=await post('assist',{name:cat.name,goal:summary.value,dialogue:'[]',
    context:JSON.stringify(cat.levels.slice(0,active).map(l=>l.summary || instruction(l)))});
   if(r.issues.length){history.push({role:'assistant',content:r.issues.join(' ')});ready=false;showHistory();status.textContent='Chiarisci nella chat prima di salvare.';return;}
   const level={command:summary.value,summary:summary.value,conversation:structuredClone(history),
    compiled:{step:r.step,ticket:r.ticket,explanation:r.explanation}};
   if(active===cat.levels.length)cat.levels.push(level);else cat.levels[active]=level;
   invalidate();drawTable();closeEditor();message.textContent='Passaggio salvato.';
  }catch(e){status.textContent=e.message;}
  finally{pending=false;syncEditor();}
 }
 const add=button('Aggiungi passaggio',()=>openEditor(cat.levels.length));
 panel.append(table,add,editor,simulateButton,coherence,message,out);drawTable();refresh();syncEditor();
 async function busy(fn){
  simulating=true;simulateButton.disabled=true;message.textContent='Simulazione in corso…';
  try{await fn();}catch(e){message.textContent=e.message;}finally{simulating=false;refresh();}
 }
simulateButton.onclick=()=>busy(async()=>{
 const start=revision;out.hidden=true;
 const plan=reviewed.categories;
 const r=await post('simulate',{name:cat.name,steps:JSON.stringify(reviewed.steps)});message.textContent='';
 if(start!==revision){message.textContent='La bozza è cambiata. Ripeti la simulazione.';return;}
 out.replaceChildren(el('h3','Risultato della simulazione'));out.hidden=false;
 out.append(el('p',r.total+' movimenti · '+r.excluded+' già riconciliati, protetti o duplicati · '+(r.total-r.excluded)+' esaminati.'));
 let solved=0, manual=0;for(const levels of r.stats)for(const s of levels){solved+=s.solved;manual+=s.manual;}
 out.append(el('p',solved+' risolti · '+manual+' al riconcilio manuale · '+r.remaining+' ancora in esame, di cui '+r.web+' candidati a una ricerca internet.'));
 for(const w of r.warnings)out.append(el('p',w));
 plan.forEach((c,i)=>{
  out.append(el('h4',c.name));
  const table=el('table'),header=el('tr');
  for(const h of ['Passaggio','Esaminati','Record riconosciuti','Risolti','Da verificare'])header.append(el('th',h));
  table.append(header);
  c.levels.forEach((l,j)=>{
   const s=r.stats[i][j],row=el('tr');
   const identifies=l.test!=='direct' && !(l.test==='lookup' && !l.sources?.length);
   const labels={employee:'Riconoscimento del dipendente',adp:'Corrispondenza con i pagamenti ADP',
    check:'Riconoscimento degli assegni',text:'Ricerca del testo «'+(l.value || '')+'»',
    restaurant:'Riconoscimento dei ristoranti',fuel:'Riconoscimento dei distributori di carburante',ev:'Riconoscimento delle ricariche EV'};
   const label=labels[l.test] || (l.test==='direct' && l.action==='why' ? 'Assegnazione del WHY «'+l.why+'» ai rimanenti' :
    cat.levels[j].compiled?.explanation || instruction(cat.levels[j]));
   for(const value of [(j+1)+' · '+label,s.entered,identifies?s.matched:'—',s.solved,s.manual])row.append(el('td',value));
   table.append(row);
  });
  out.append(table);
 });
 out.append(el('p','Record riconosciuti: corrispondenze trovate dal passaggio. 0 = nessuna corrispondenza; — = il passaggio non esegue un riconoscimento. Risolti: movimenti classificati da quel passaggio.'));
 if(r.examples.length){const details=el('details');details.append(el('summary','Movimenti risolti o destinati al manuale ('+r.examples.length+')'));for(const x of r.examples)details.append(el('p',x.category+' · '+x.description+' → '+x.result));out.append(details);}
 out.scrollIntoView({block:'start'});
});
 return invalidate;
}
render();
})();
