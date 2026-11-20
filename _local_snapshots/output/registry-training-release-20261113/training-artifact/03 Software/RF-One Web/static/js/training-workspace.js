/* Local Training dialogs preserve drafts and return focus to their trigger. */
document.addEventListener('DOMContentLoaded',()=>{
 const triggers=new WeakMap();
 const open=(dialog,trigger)=>{triggers.set(dialog,trigger);dialog.showModal();};
 const editor=document.querySelector('#student-editor');
 const form=document.querySelector('#student-editor-form');
 document.querySelectorAll('[data-open]').forEach(button=>button.addEventListener('click',()=>{
  if(button.dataset.open==='student-editor'){
   form.reset();form.elements.id.value='';
   document.querySelector('#student-archive').hidden=true;
   const student=button.dataset.editStudent?JSON.parse(button.dataset.editStudent):null;
   // New student: name and surname only (username/password generated). Edit: existing fields.
   editor.querySelectorAll('[data-mode]').forEach(part=>{const on=part.dataset.mode===(student?'edit':'create');part.hidden=!on;if(part.tagName==='FIELDSET')part.disabled=!on;});
   if(student){for(const key of ['name','email','phone','username','id'])form.elements[key].value=student[key]||'';
    document.querySelector('#student-archive').hidden=false;
    document.querySelector('#student-archive').elements.id.value=student.id;
   }
   form.elements.password.required=false;
   form.elements.password_confirm.required=false;
   document.querySelector('#student-editor-title').textContent=student?'Manage student':'New student';
  }
  if(button.dataset.open==='student-assignment-editor'){
   const assignmentForm=document.getElementById('student-assignment-form');
   assignmentForm.reset();assignmentForm.action=button.dataset.assignUrl;
   document.getElementById('student-assignment-name').textContent=button.dataset.assignStudentName;
   document.getElementById('student-assignment-error').hidden=true;
   assignmentForm.dispatchEvent(new Event('change',{bubbles:true}));
  }
  open(document.getElementById(button.dataset.open),button);
 }));
 document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
 document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('close',()=>triggers.get(dialog)?.focus()));
 document.querySelectorAll('[data-modal-help]').forEach(button=>button.addEventListener('click',()=>{
  const help=document.querySelector('#rf-help');open(help,button);
  help.querySelector('#'+button.dataset.modalHelp)?.scrollIntoView({block:'start'});
 }));
 document.querySelectorAll('[data-reopen]').forEach(dialog=>open(dialog,document.querySelector('#new-student')));
 document.querySelectorAll('[data-filter]').forEach(input=>input.addEventListener('input',()=>{
  const query=input.value.toLocaleLowerCase('en');
  document.getElementById(input.dataset.filter).querySelectorAll('.tw-check').forEach(row=>row.hidden=!row.textContent.toLocaleLowerCase('en').includes(query));
 }));
 const assignment=document.getElementById('student-assignment-form');
 if(assignment){
  let saving=false;
  const confirm=document.getElementById('student-assignment-confirm');
  const update=()=>{const count=assignment.querySelectorAll('[name=pills]:checked').length;
   confirm.disabled=saving||count===0;
   document.getElementById('student-assignment-summary').textContent=count?`${count} content items selected for this student. They are saved when you confirm.`:'Select at least one content item to assign.';
  };
  assignment.addEventListener('change',update);update();
  assignment.addEventListener('submit',async event=>{
   event.preventDefault();if(saving)return;
   const error=document.getElementById('student-assignment-error');error.hidden=true;
   saving=true;update();
   try{
    const response=await fetch(assignment.action,{method:'POST',body:new FormData(assignment),headers:{Accept:'application/json'}});
    if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('Your session is unavailable. Your selections remain in the form; try again.');
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Assignment failed. Check your selections.');
    window.location.reload();
   }catch(problem){error.textContent=problem.message;error.hidden=false;saving=false;update();}
  });
 }
});
