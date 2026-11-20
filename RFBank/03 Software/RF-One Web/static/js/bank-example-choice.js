(() => {
 const dialog=document.getElementById('bank-example-choice');if(!dialog)return;
 let opener;
 document.addEventListener('click',event=>{
  const button=event.target.closest('.bank-example-open');if(!button)return;
  opener=button;document.getElementById('bank-example-description').textContent=button.dataset.exampleDescription;
  document.getElementById('bank-example-rule').href=button.dataset.exampleRule;
  document.getElementById('bank-example-photo').href=button.dataset.examplePhoto;
  dialog.showModal();
 });
 document.getElementById('bank-example-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>opener?.focus());
})();
