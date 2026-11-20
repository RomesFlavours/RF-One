document.addEventListener('DOMContentLoaded',()=>{
  const dialog=document.getElementById('vm-editor-dialog');if(!dialog)return;
  const form=document.getElementById('vm-editor-form');let saving=false,loading=false,url=null,saved=null;
  const showError=(id,message)=>{const n=document.getElementById(id);n.textContent=message||'';n.hidden=!message;};
  const request=async(target,options={})=>{
    const response=await fetch(target,{credentials:'same-origin',...options});let data;
    try{data=await response.json();}catch{throw new Error('Could not confirm the response. Your draft remains available; close and reopen before retrying.');}
    if(!response.ok)throw new Error(data.error||'Could not load or save this dish card.');return data.card;
  };
  document.getElementById('vm-restaurant').addEventListener('change',()=>{
    const menu=document.getElementById('vm-menu-filter');menu.replaceChildren(new Option('',''));menu.disabled=true;
    document.getElementById('vm-restaurant-form').requestSubmit();
  });
  document.getElementById('vm-menu-filter').addEventListener('change',()=>document.getElementById('vm-restaurant-form').requestSubmit());
  document.querySelectorAll('[data-editorial-url]').forEach(button=>button.addEventListener('click',async()=>{
    if(loading||saving)return;loading=true;button.disabled=true;showError('vm-manager-error','');
    try{
      const card=await request(button.dataset.editorialUrl);url=button.dataset.editorialUrl;saved={trigger:button,x:scrollX,y:scrollY};form.reset();
      form.elements.namedItem('version').value=card.content_version;
      form.elements.namedItem('description_phrases').value=card.description_phrases.join('\n');
      form.elements.namedItem('sales_phrases').value=card.sales_phrases.join('\n');
      document.getElementById('vm-editor-title').textContent=card.title;
      document.getElementById('vm-editor-restaurant').textContent=card.restaurant_name;
      const photo=document.getElementById('vm-editor-photo');photo.hidden=!card.photo_url;if(card.photo_url)photo.src=card.photo_url;else photo.removeAttribute('src');
      showError('vm-editor-error','');dialog.showModal();
    }catch(exc){showError('vm-manager-error',exc.message);}finally{loading=false;button.disabled=false;}
  }));
  document.querySelectorAll('[data-editorial-close]').forEach(button=>button.addEventListener('click',()=>{if(!saving)button.closest('dialog').close();}));
  dialog.addEventListener('cancel',event=>{if(saving)event.preventDefault();});
  dialog.addEventListener('close',()=>{saved?.trigger.focus({preventScroll:true});if(saved)scrollTo(saved.x,saved.y);});
  document.getElementById('vm-editor-help').addEventListener('click',()=>{
    const content=document.querySelector('#rf-help #visual-menu-manage').cloneNode(true);content.removeAttribute('id');
    document.getElementById('vm-editor-help-body').replaceChildren(content);document.getElementById('vm-editor-help-dialog').showModal();
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(saving)return;const body=new FormData(form);saving=true;showError('vm-editor-error','');
    const controls=[...form.querySelectorAll('input,textarea,button')].map(n=>[n,n.disabled]);controls.forEach(([n])=>n.disabled=true);
    try{
      const card=await request(url,{method:'POST',body});const row=saved.trigger.closest('tr');
      row.querySelector('[data-description-count]').textContent=card.description_phrases.length;row.querySelector('[data-sales-count]').textContent=card.sales_phrases.length;dialog.close();
    }catch(exc){showError('vm-editor-error',exc.message);document.getElementById('vm-editor-error').scrollIntoView({block:'nearest'});}finally{saving=false;controls.forEach(([n,disabled])=>n.disabled=disabled);}
  });
});
