(() => {
 const dialog=document.getElementById('bank-example-choice');if(!dialog)return;
 let opener;
 document.querySelectorAll('.bank-example-open').forEach(button=>button.addEventListener('click',()=>{
  opener=button;document.getElementById('bank-example-description').textContent=button.dataset.exampleDescription;
  document.getElementById('bank-example-rule').href=button.dataset.exampleRule;
  document.getElementById('bank-example-photo').href=button.dataset.examplePhoto;
  dialog.showModal();
 }));
 document.getElementById('bank-example-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>opener?.focus());
})();
