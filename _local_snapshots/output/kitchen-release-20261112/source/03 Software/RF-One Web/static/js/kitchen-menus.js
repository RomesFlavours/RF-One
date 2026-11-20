document.addEventListener('DOMContentLoaded',()=>{
  const root=document.getElementById('menu-workspace');if(!root)return;
  const data=JSON.parse(document.getElementById('menu-data').textContent),list=document.getElementById('menu-list');
  const dialog=document.getElementById('menu-dialog'),form=document.getElementById('menu-form'),rows=document.getElementById('menu-entry-rows');
  const location=document.getElementById('menu-location'),name=document.getElementById('menu-name');
  let draft=null,saving=false,returnTo=null;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const option=(text,value)=>{const n=el('option',text);n.value=value??'';return n;};
  const error=(id,message)=>{const n=document.getElementById(id);n.textContent=message||'';n.hidden=!message;};
  const button=(text,action)=>{const b=el('button',text,'btn-secondary');b.type='button';b.addEventListener('click',action);return b;};
  const remember=trigger=>{returnTo={trigger,x:scrollX,y:scrollY};};
  const post=async(url,payload)=>{
    const body=new FormData();body.set('csrf_token',form.elements.namedItem('csrf_token').value);body.set('payload',JSON.stringify(payload));
    const response=await fetch(url,{method:'POST',body,credentials:'same-origin'});let result;
    try{result=await response.json();}catch{throw new Error('Could not confirm the save. Close and reopen the menu before retrying.');}
    if(!response.ok)throw new Error(result.error||'Unable to save this menu.');
    if(result.menus)data.menus=result.menus;
    return result.menu;
  };
  const applyMenu=menu=>{const i=data.menus.findIndex(m=>m.id===menu.id);if(i<0)data.menus.push(menu);else data.menus[i]=menu;render();list.querySelector('[data-menu-id="'+menu.id+'"]').open=true;};
  const render=()=>{
    const openIds=new Set([...list.querySelectorAll('details[open]')].map(n=>n.dataset.menuId));list.replaceChildren();
    if(!data.menus.length)list.append(el('p','No menus yet.','config-empty'));
    for(const menu of data.menus){
      const section=el('details',null,'kitchen-config-section');section.dataset.menuId=menu.id;section.dataset.rrKey='menu-'+menu.id;section.open=openIds.has(String(menu.id));
      const head=el('summary');head.append(el('span',null,'config-arrow'),el('span',menu.name,'config-heading'));
      if(data.locations.length>1)head.append(el('span',menu.location_name,'config-count'));
      head.append(el('span',menu.archived?'Archived':menu.active?'Active':'Draft','config-count'));section.append(head);
      const body=el('div',null,'config-body'),actions=el('div',null,'recipe-action-buttons');
      actions.append(button(menu.archived?'View':'Edit',event=>openMenu(menu,event.currentTarget)));
      const changeState=async(action,event)=>{
        if(saving)return;const trigger=event.currentTarget;trigger.disabled=true;saving=true;const x=scrollX,y=scrollY;
        error('menu-page-error','');
        try{applyMenu(await post(root.dataset.saveUrl.replace(/\/save$/,'/'+menu.id+'/'+action),{revision:menu.revision}));
          list.querySelector('[data-menu-id="'+menu.id+'"] button')?.focus({preventScroll:true});scrollTo(x,y);
        }catch(exc){error('menu-page-error',exc.message);}finally{saving=false;trigger.disabled=false;}
      };
      if(!menu.archived&&!menu.active)actions.append(button('Activate',event=>changeState('activate',event)));
      if(!menu.archived)actions.append(button('Archive',event=>changeState('archive',event)));
      body.append(actions);
      const groups=new Map();for(const entry of menu.entries){if(!groups.has(entry.area_id))groups.set(entry.area_id,{name:entry.area_name,entries:[]});groups.get(entry.area_id).entries.push(entry);}
      if(!groups.size)body.append(el('p','No entries yet.','config-empty'));
      for(const group of groups.values()){
        body.append(el('h3',group.name));const ul=el('ul');
        for(const entry of group.entries){const li=el('li');li.append(el('span',entry.label),el('span',entry.recipe_id?'Recipe: '+entry.recipe_name:'Label','menu-entry-kind'));ul.append(li);}body.append(ul);
      }
      section.append(body);list.append(section);
    }
  };
  const fillArea=(select,entry={})=>{
    const current=select.value||String(entry.area_id||'');select.replaceChildren(option('Choose an Area',''));
    data.areas.filter(a=>!a.archived||(entry.id&&a.id===entry.area_id)).forEach(a=>select.append(option(a.name+(a.archived?' (archived)':''),a.id)));
    select.value=current;if(!select.value)select.value='';
  };
  const addEntry=(entry={})=>{
    const tr=el('tr');tr.dataset.id=entry.id||'';tr.savedEntry=entry;
    const area=el('select');area.dataset.area='';area.required=true;area.setAttribute('aria-label','Menu Area');fillArea(area,entry);
    const label=el('input');label.dataset.label='';label.maxLength=255;label.value=entry.label||'';label.setAttribute('aria-label','Menu entry label');
    const recipe=el('select');recipe.dataset.recipe='';recipe.setAttribute('aria-label','Recipe');recipe.append(option('Label only — no recipe',''));
    const categoryKey=value=>(value||'').normalize('NFKC').trim().replace(/\s+/g,' ').toLowerCase();
    const fillRecipes=(current,preserveMismatch=false)=>{
      const selectedArea=data.areas.find(a=>String(a.id)===area.value);
      recipe.replaceChildren(option('Label only — no recipe',''));recipe.setCustomValidity('');
      const eligible=selectedArea?data.recipes.filter(r=>r.category&&categoryKey(r.category)===categoryKey(selectedArea.name)):[];
      eligible.forEach(r=>recipe.append(option(r.name,r.id)));
      if(current&&eligible.some(r=>String(r.id)===String(current)))recipe.value=current;
      else if(current&&preserveMismatch){
        const missing=option('Previous recipe Category differs — choose recipe or Label only','__mismatch');missing.disabled=true;recipe.append(missing);recipe.value='__mismatch';
        recipe.setCustomValidity('Choose a recipe matching this Area, or explicitly select Label only.');
      }
    };
    fillRecipes(entry.recipe_id,true);
    let previousRecipe=data.recipes.find(r=>r.id===entry.recipe_id);
    let autoLabel=!label.value.trim()||label.value===previousRecipe?.name;
    label.addEventListener('input',()=>{autoLabel=!label.value.trim()||label.value===previousRecipe?.name;});
    area.addEventListener('change',()=>{fillRecipes(recipe.value);previousRecipe=data.recipes.find(r=>String(r.id)===recipe.value);});
    recipe.addEventListener('change',()=>{
      recipe.setCustomValidity('');
      const next=data.recipes.find(r=>String(r.id)===recipe.value);
      if(next&&(autoLabel||!label.value.trim()))label.value=next.name;
      previousRecipe=next;
      if(next)autoLabel=label.value===next.name;
    });
    for(const control of [area,label,recipe]){const td=el('td');td.append(control);tr.append(td);}
    const actions=el('td',null,'menu-entry-actions');
    actions.append(button('Up',()=>{if(tr.previousElementSibling)rows.insertBefore(tr,tr.previousElementSibling);}),button('Down',()=>{if(tr.nextElementSibling)rows.insertBefore(tr.nextElementSibling,tr);}),button('Remove',()=>tr.remove()));
    tr.append(actions);rows.append(tr);
  };
  const openMenu=(menu,trigger)=>{
    if(saving)return;remember(trigger);draft=menu?structuredClone(menu):{draft_key:crypto.randomUUID(),entries:[]};form.reset();rows.replaceChildren();error('menu-form-error','');
    name.value=draft.name||'';location.replaceChildren(option('Choose a restaurant location',''));
    data.locations.forEach(l=>location.append(option(l.name,l.id)));location.value=draft.location_id||(data.locations.length===1?data.locations[0].id:'');
    for(const entry of draft.entries)addEntry(entry);
    document.getElementById('menu-dialog-title').textContent=menu?(menu.archived?'View menu':'Edit menu'):'New menu';
    form.querySelectorAll('input:not([type="hidden"]),select,button[type="submit"],#menu-add,#menu-entry-rows button').forEach(n=>n.disabled=Boolean(menu?.archived));
    dialog.showModal();name.focus({preventScroll:true});
  };
  root.addEventListener('click',event=>{const close=event.target.closest('[data-menu-close]');if(close&&!saving)close.closest('dialog').close();});
  dialog.addEventListener('cancel',event=>{if(saving)event.preventDefault();});
  dialog.addEventListener('close',()=>{
    const saved=returnTo;if(!saved)return;
    const trigger=draft.id?list.querySelector('[data-menu-id="'+draft.id+'"] button'):saved.trigger;
    trigger?.focus({preventScroll:true});scrollTo(saved.x,saved.y);
  });
  document.getElementById('menu-help-button').addEventListener('click',()=>{
    const body=document.getElementById('menu-help-body'),copy=document.querySelector('#rf-help #kitchen-menus').cloneNode(true);copy.removeAttribute('id');body.replaceChildren(copy);document.getElementById('menu-help-dialog').showModal();
  });
  document.getElementById('menu-new').addEventListener('click',event=>openMenu(null,event.currentTarget));
  document.getElementById('menu-add').addEventListener('click',()=>addEntry());
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(saving||draft.archived)return;
    const payload={id:draft.id,revision:draft.revision,draft_key:draft.draft_key,name:name.value,location_id:location.value,
      entries:[...rows.children].map(row=>({id:row.dataset.id||null,area_id:row.querySelector('[data-area]').value,label:row.querySelector('[data-label]').value,recipe_id:row.querySelector('[data-recipe]').value}))};
    saving=true;error('menu-form-error','');const controls=[...form.querySelectorAll('button,input,select')].map(n=>[n,n.disabled]);controls.forEach(([n])=>n.disabled=true);
    try{const menu=await post(root.dataset.saveUrl,payload);draft.id=menu.id;applyMenu(menu);dialog.close();}
    catch(exc){error('menu-form-error',exc.message);}finally{saving=false;controls.forEach(([n,disabled])=>n.disabled=disabled);}
  });
  render();
});
