/* One row-return implementation for all RF-One lists using data-rr-key. */
document.addEventListener('DOMContentLoaded',()=>{
 const key='rf-one-row-return:'+location.pathname+location.search;
 const pending=new WeakMap();
 const locate=id=>document.querySelector(`[data-rr-key="${CSS.escape(id)}"]`);
 const snapshot=(row,button)=>{
  const rows=[...row.parentElement.querySelectorAll('[data-rr-key]')],index=rows.indexOf(row);
  const container=row.closest('.tw-table-scroll');
  return {row:row.dataset.rrKey,top:row.getBoundingClientRect().top,
   next:rows[index+1]?.dataset.rrKey,previous:rows[index-1]?.dataset.rrKey,
   focus:[...row.querySelectorAll('button,a,input,select')].indexOf(button),
   left:container?.scrollLeft||0,time:Date.now()};
 };
 const restore=saved=>{
  const row=locate(saved.row)||(saved.next&&locate(saved.next))||(saved.previous&&locate(saved.previous));
  if(!row)return;
  const container=row.closest('.tw-table-scroll');if(container)container.scrollLeft=saved.left;
  window.scrollBy(0,row.getBoundingClientRect().top-saved.top);
  if(!document.querySelector('dialog[open]')){
   const controls=row.querySelectorAll('button,a,input,select');
   (controls[saved.focus]||controls[0])?.focus({preventScroll:true});
  }
 };
 document.addEventListener('click',event=>{
  const button=event.target.closest('[data-open]'),row=button?.closest('[data-rr-key]');
  if(!row)return;
  const dialog=document.getElementById(button.dataset.open);if(!dialog)return;
  pending.set(dialog,snapshot(row,button));
 },true);
 document.addEventListener('submit',event=>{
  const dialog=event.target.closest('dialog'),row=event.target.closest('[data-rr-key]');
  const saved=(dialog&&pending.get(dialog))||(row&&snapshot(row,event.submitter));
  if(saved)sessionStorage.setItem(key,JSON.stringify({...saved,time:Date.now()}));
 },true);
 document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('close',()=>{
  sessionStorage.removeItem(key);
  const saved=pending.get(dialog);if(saved){restore(saved);pending.delete(dialog);}
 }));
 try{
  const saved=JSON.parse(sessionStorage.getItem(key));sessionStorage.removeItem(key);
  if(saved&&Date.now()-saved.time<60000){restore(saved);
   document.querySelectorAll('dialog[open]').forEach(dialog=>pending.set(dialog,saved));
  }
 }catch{sessionStorage.removeItem(key);}
});
