document.addEventListener('DOMContentLoaded',()=>{
  const root=document.getElementById('recipe-workspace');if(!root)return;
  const meta=document.getElementById('recipe-form-dialog'),composition=document.getElementById('recipe-composition-dialog');
  const form=document.getElementById('recipe-form'),cform=document.getElementById('composition-form'),tbody=document.getElementById('composition-rows');
  const plating=document.getElementById('recipe-plating-dialog'),pform=document.getElementById('plating-form');
  let platingId=null,previewObject=null,savedPlatingImage=null;
  const preview=url=>{const image=document.getElementById('plating-preview');image.hidden=!url;document.getElementById('plating-no-image').hidden=Boolean(url);if(url)image.src=url;else image.removeAttribute('src');};
  let draft=null,loading=false,saving=false;const returnTo=new WeakMap();
  const field=name=>form.elements.namedItem(name);
  const option=(label,value)=>{const o=document.createElement('option');o.textContent=label;o.value=value;return o;};
  const error=(dialog,message)=>{const p=dialog.querySelector('.recipe-error');p.textContent=message||'';p.hidden=!message;};
  const request=async(url,params)=>{
    const r=await fetch(url,{credentials:'same-origin',...params});let data;
    try{data=await r.json();}catch{throw new Error('Could not confirm the response. Close and reopen the record before retrying.');}
    if(!r.ok)throw new Error(data.error||'Unable to save this recipe.');return data;
  };
  const open=(dialog,trigger)=>{returnTo.set(dialog,{trigger,x:scrollX,y:scrollY});error(dialog,'');dialog.showModal();};
  root.querySelectorAll('dialog').forEach(dialog=>{
    dialog.addEventListener('cancel',e=>{if(saving)e.preventDefault();});
    dialog.addEventListener('close',()=>{const saved=returnTo.get(dialog);if(saved){saved.trigger?.focus({preventScroll:true});scrollTo(saved.x,saved.y);}});
  });
  const updateRow=recipe=>{
    let row=root.querySelector('[data-recipe-id="'+recipe.id+'"]');
    if(!row){row=document.getElementById('recipe-list-row').content.firstElementChild.cloneNode(true);
      row.dataset.recipeId=recipe.id;row.dataset.rrKey='recipe-'+recipe.id;
      row.querySelector('[data-edit-recipe]').dataset.editRecipe=recipe.id;
      row.querySelector('[data-compose-recipe]').dataset.composeRecipe=recipe.id;
      row.querySelector('[data-plating-recipe]').dataset.platingRecipe=recipe.id;
      root.querySelector('[data-kind="'+recipe.kind+'"] tbody').prepend(row);}
    row.querySelector('[data-recipe-name]').textContent=recipe.name;row.querySelector('[data-recipe-category]').textContent=recipe.category||'—';
    root.querySelectorAll('.recipe-section').forEach(section=>section.querySelector('[data-section-count]').textContent=section.querySelectorAll('tbody tr').length);
  };
  const total=()=>{
    let sum=0,unknown=false;
    tbody.querySelectorAll('tr').forEach(row=>{
      const source=row.querySelector('[data-component]').value||row.querySelector('[data-preparation]').value,value=row.querySelector('[data-grams]').value;
      if(source&&value==='')unknown=true;else if(source&&Number.isFinite(Number(value)))sum+=Number(value);
    });
    document.getElementById('composition-total').textContent=new Intl.NumberFormat('en-US',{maximumFractionDigits:6}).format(sum)+(unknown?' + unknown weight':'');
  };
  const checkSource=row=>{
    const conflict=Boolean(row.querySelector('[data-component]').value&&row.querySelector('[data-preparation]').value);
    row.classList.toggle('recipe-row-conflict',conflict);
    let warning=row.querySelector('[data-source-warning]');
    if(!warning){warning=document.createElement('span');warning.dataset.sourceWarning='';warning.className='recipe-source-warning';row.firstElementChild.append(warning);}
    warning.textContent=conflict?'Imported row: clear one selection. A row can contain a component or a preparation, never both.':'';
    warning.hidden=!conflict;return conflict;
  };
  const addLine=(line={})=>{
    const row=document.createElement('tr');row.dataset.lineId=line.id||'';row.dataset.stepId=line.step_id||'';
    const addSelect=(items,selected,label,attribute,legacy)=>{
      const td=document.createElement('td'),select=document.createElement('select');select.setAttribute(attribute,'');select.setAttribute('aria-label',label);select.append(option('—',''));
      items.filter(x=>!x.archived||'id:'+x.id===selected).forEach(x=>select.append(option(x.name+(x.archived?' (archived)':''),'id:'+x.id)));
      if(selected==='legacy')select.append(option('Imported: '+legacy,'legacy'));
      select.value=selected||'';td.append(select);row.append(td);
    };
    addSelect(draft.components,line.component,'Component','data-component',line.component_label);
    addSelect(draft.preparations.filter(x=>x.id!==draft.recipe.id),line.preparation,'Preparation used','data-preparation',line.preparation_label);
    const gramsCell=document.createElement('td'),grams=document.createElement('input');grams.type='number';grams.min='0';grams.step='0.000001';grams.value=line.grams||'';grams.dataset.grams='';grams.setAttribute('aria-label','Grams');gramsCell.append(grams);row.append(gramsCell);
    const noteCell=document.createElement('td'),note=document.createElement('textarea');note.rows=2;note.maxLength=20000;note.value=line.instructions||'';note.dataset.instructions='';note.setAttribute('aria-label','Instructions');noteCell.append(note);row.append(noteCell);
    const action=document.createElement('td'),remove=document.createElement('button');remove.type='button';remove.className='btn-secondary';remove.textContent='Remove';remove.dataset.removeLine='';action.append(remove);row.append(action);
    tbody.append(row);checkSource(row);total();return row;
  };
  root.addEventListener('click',async event=>{
    const close=event.target.closest('[data-close-dialog]');if(close){if(!saving)close.closest('dialog').close();return;}
    const help=event.target.closest('[data-modal-help]');if(help){
      const source=document.querySelector('#rf-help #'+help.dataset.modalHelp),dialog=document.getElementById('recipe-modal-help'),body=document.getElementById('recipe-modal-help-body');
      body.replaceChildren();const content=source.cloneNode(true);content.removeAttribute('id');body.append(content);returnTo.set(dialog,{trigger:help,x:scrollX,y:scrollY});dialog.showModal();return;}
    if(event.target.closest('[data-remove-line]')){event.target.closest('tr').remove();total();return;}
    const trigger=event.target.closest('[data-new-recipe],[data-edit-recipe],[data-compose-recipe],[data-plating-recipe]');if(!trigger||loading||saving)return;
    loading=true;trigger.disabled=true;document.getElementById('recipe-page-error').hidden=true;
    try{
      const id=trigger.dataset.editRecipe||trigger.dataset.composeRecipe||trigger.dataset.platingRecipe;
      const data=await request(id?root.dataset.baseUrl+'/'+id+(trigger.hasAttribute('data-plating-recipe')?'/plating':'/data'):root.dataset.optionsUrl);
      if(trigger.hasAttribute('data-plating-recipe')){
        pform.reset();platingId=id;pform.elements.namedItem('revision').value=data.recipe.revision;
        document.getElementById('plating-description').value=data.description;
        document.getElementById('recipe-plating-title').textContent='Plating · '+data.recipe.name;
        if(previewObject){URL.revokeObjectURL(previewObject);previewObject=null;}
        savedPlatingImage=data.image_url;document.getElementById('plating-file-name').textContent='No file selected';preview(data.image_url);open(plating,trigger);
      }else if(trigger.hasAttribute('data-compose-recipe')){
        draft=data;tbody.replaceChildren();for(const line of data.rows)addLine(line);
        document.getElementById('composition-work').value=data.work_minutes;document.getElementById('recipe-composition-title').textContent='Components · '+data.recipe.name;
        total();open(composition,trigger);
      }else{
        form.reset();const recipe=data.recipe;
        field('id').value=recipe?.id||'';field('revision').value=recipe?.revision||'';field('kind').value=recipe?.kind||trigger.dataset.newRecipe;
        field('draft_key').value=crypto.randomUUID();field('name').value=recipe?.name||'';
        field('category_id').replaceChildren(option('Unassigned',''));
        data.categories.filter(x=>!x.archived||x.id===recipe?.category_id).forEach(x=>field('category_id').append(option(x.name+(x.archived?' (archived)':''),x.id)));
        field('category_id').value=recipe?.category_id||'';document.getElementById('recipe-form-title').textContent=(recipe?'Edit ':'New ')+(field('kind').value==='dish'?'recipe':'preparation');
        open(meta,trigger);field('name').focus({preventScroll:true});}
    }catch(exc){const p=document.getElementById('recipe-page-error');p.textContent=exc.message;p.hidden=false;}
    finally{loading=false;trigger.disabled=false;}
  });
  document.getElementById('composition-add-row').addEventListener('click',()=>addLine().querySelector('select').focus());
  tbody.addEventListener('input',total);
  tbody.addEventListener('change',event=>{
    const select=event.target.closest('[data-component],[data-preparation]');
    if(select){const row=select.closest('tr');
      if(select.value)row.querySelector(select.hasAttribute('data-component')?'[data-preparation]':'[data-component]').value='';
      checkSource(row);}
    total();
  });
  const submit=async(dialog,url,body)=>{
    saving=true;error(dialog,'');const controls=[...dialog.querySelectorAll('button,input,select,textarea')].map(el=>[el,el.disabled]);controls.forEach(([el])=>el.disabled=true);
    try{const data=await request(url,{method:'POST',body});updateRow(data.recipe);dialog.close();}
    catch(exc){error(dialog,exc.message);}finally{saving=false;controls.forEach(([el,disabled])=>el.disabled=disabled);}
  };
  form.addEventListener('submit',event=>{event.preventDefault();if(!saving)submit(meta,root.dataset.saveUrl,new FormData(form));});
  document.getElementById('plating-choose-file').addEventListener('click',()=>document.getElementById('plating-image').click());
  document.getElementById('plating-image').addEventListener('change',event=>{
    const file=event.target.files[0];if(!file)return;
    if(file.size>10*1024*1024){error(plating,'Choose an image up to 10 MB.');event.target.value='';document.getElementById('plating-file-name').textContent='No file selected';preview(savedPlatingImage);return;}
    document.getElementById('plating-file-name').textContent=file.name;
    if(previewObject)URL.revokeObjectURL(previewObject);
    previewObject=URL.createObjectURL(file);preview(previewObject);error(plating,'');
  });
  pform.addEventListener('submit',event=>{event.preventDefault();if(!saving)submit(plating,root.dataset.baseUrl+'/'+platingId+'/plating',new FormData(pform));});
  cform.addEventListener('submit',event=>{
    event.preventDefault();if(saving)return;
    if([...tbody.querySelectorAll('tr')].some(checkSource)){
      error(composition,'Each row must contain either a component or a preparation, never both. Clear one selection in the highlighted row.');return;
    }
    const rows=[...tbody.querySelectorAll('tr')].map(row=>({id:row.dataset.lineId||null,step_id:row.dataset.stepId||null,component:row.querySelector('[data-component]').value,preparation:row.querySelector('[data-preparation]').value,grams:row.querySelector('[data-grams]').value,instructions:row.querySelector('[data-instructions]').value}));
    const body=new FormData(cform);body.set('payload',JSON.stringify({revision:draft.recipe.revision,rows,work_minutes:document.getElementById('composition-work').value}));
    submit(composition,root.dataset.baseUrl+'/'+draft.recipe.id+'/composition',body);
  });
});
