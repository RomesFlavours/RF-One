/* Failed course saves retain the editor's fields and selected files. */
document.addEventListener('DOMContentLoaded',()=>{
 const form=document.getElementById('course-editor-form');if(!form)return;
 const list=document.getElementById('course-lessons'),template=document.getElementById('course-lesson-template');
 const error=document.getElementById('course-error');
 const number=()=>{const rows=[...list.children];rows.forEach((row,index)=>{
  row.querySelector('h4').textContent=`Lezione ${index+1}`;
  row.querySelector('[data-lesson-up]').disabled=index===0;
  row.querySelector('[data-lesson-down]').disabled=index===rows.length-1;
 });document.getElementById('add-course-lesson').disabled=rows.length>=30;};
 const add=(data={})=>{
  const row=template.content.firstElementChild.cloneNode(true);
  for(const [key,name] of Object.entries({title:'lesson_title',kind:'lesson_kind',url:'lesson_url',text:'lesson_text',file_id:'lesson_file_id'})){
   row.querySelector(`[name=${name}]`).value=data[key]??(key==='kind'?'text':'');
  }
  row.querySelector('[data-file-name]').textContent=data.filename?`File salvato: ${data.filename}. Seleziona un file solo per sostituirlo.`:'';
  const show=()=>{const kind=row.querySelector('[name=lesson_kind]').value;
   row.querySelector('[data-lesson-field=text]').hidden=kind!=='text';
   row.querySelector('[data-lesson-field=url]').hidden=!['internal','link'].includes(kind);
   row.querySelector('[data-lesson-field=file]').hidden=kind!=='file';
  };
  row.querySelector('[name=lesson_kind]').addEventListener('change',show);show();
  row.querySelector('[data-lesson-remove]').addEventListener('click',()=>{row.remove();number();});
  row.querySelector('[data-lesson-up]').addEventListener('click',()=>{const previous=row.previousElementSibling;if(previous)list.insertBefore(row,previous);number();});
  row.querySelector('[data-lesson-down]').addEventListener('click',()=>{const next=row.nextElementSibling;if(next)list.insertBefore(next,row);number();});
  list.append(row);number();
 };
 const fill=(record=null)=>{
  form.reset();list.replaceChildren();error.hidden=true;
  const data=record?.data||{};
  form.elements.id.value=record?.id||'';form.elements.edit_revision.value=record?.edit_revision||0;
  for(const key of ['title','description','objective'])form.elements[key].value=data[key]||'';
  document.getElementById('course-editor-title').textContent=record?'Gestisci corso':'Nuovo corso';
  document.getElementById('course-version-note').textContent=record?.active_version?
   `La versione ${record.active_version} resta disponibile. «Salva bozza» conserva le modifiche; «Rendi disponibile» crea la versione successiva. Le assegnazioni esistenti conservano la loro versione.`:
   'La bozza non è visibile nelle assegnazioni. Per rendere disponibile il corso completa descrizione, obiettivo e almeno una lezione.';
  (data.lessons?.length?data.lessons:[{}]).forEach(add);
 };
 document.querySelectorAll('[data-open=course-editor]').forEach(button=>button.addEventListener('click',()=>fill(button.dataset.editCourse?JSON.parse(button.dataset.editCourse):null)));
 document.getElementById('add-course-lesson').addEventListener('click',()=>add());
 const draft=document.getElementById('course-draft-data');if(draft){fill(JSON.parse(draft.textContent));error.hidden=false;}
 form.addEventListener('submit',async event=>{
  event.preventDefault();error.hidden=true;
  const data=new FormData(form);data.set('action',event.submitter?.value||'draft');
  const files=[...data.getAll('lesson_file')];
  if(files.some(file=>file.size>25*1024*1024)||files.reduce((sum,file)=>sum+file.size,0)>29*1024*1024){error.textContent='Massimo 25 MB per file e circa 29 MB di file per salvataggio. Salva i materiali in più passaggi.';error.hidden=false;return;}
  const buttons=[...form.querySelectorAll('button[type=submit]')];buttons.forEach(button=>button.disabled=true);
  try{
   const response=await fetch(form.action,{method:'POST',body:data,headers:{Accept:'application/json'}});
   if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('La sessione o la connessione non è disponibile. I dati restano nel modulo: riprova.');
   const result=await response.json();
   if(!response.ok)throw new Error(result.error||'Salvataggio non riuscito. Controlla i dati.');
   window.location.reload();
  }catch(problem){error.textContent=problem.message||'Connessione interrotta. I dati restano nel modulo: riprova.';error.hidden=false;error.scrollIntoView({block:'nearest'});buttons.forEach(button=>button.disabled=false);}
 });
});
