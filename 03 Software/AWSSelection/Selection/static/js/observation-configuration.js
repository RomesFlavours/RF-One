(() => {
  const script=document.querySelector('script[data-observation-url]'),url=script.dataset.observationUrl,editable=script.dataset.observationEdit==='1';
  const el=id=>document.getElementById('observation-'+id),dialog=el('editor'),form=el('form');
  let scope=null,version=0,dirty=false,busy=false,rows=[];
  function error(message){el('error').textContent=message||'';el('error').hidden=!message;}
  function lock(value){busy=value;['ai','add','save','close','cancel'].forEach(id=>{if(el(id))el(id).disabled=value;});form.querySelectorAll('input,textarea').forEach(n=>n.disabled=value||!editable);}
  function values(){return [...el('items').children].map((node,i)=>({id:rows[i].id,active:node.querySelector('[data-field="active"]').checked,...Object.fromEntries(['title','description','question'].map(k=>[k,node.querySelector('[data-field="'+k+'"]').value]))}));}
  function render(items){rows=items;el('items').replaceChildren();items.forEach(item=>{
    const node=document.createElement('section');node.className='iv-item';node.style.cssText='border-top:1px solid var(--line);padding:1rem 0';
    const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.dataset.field='active';check.checked=item.active!==false;label.append(check,document.createTextNode(' Usa questa osservazione'));node.append(label);
    for(const [key,title,max] of [['title','Osservazione',200],['description','Cosa osservare',2000],['question','Domanda o prova da proporre',2000]]){
      const label=document.createElement('label'),field=document.createElement(key==='title'?'input':'textarea');label.textContent=title;field.dataset.field=key;field.value=item[key]||'';field.required=true;field.maxLength=max;field.disabled=!editable;label.append(field);node.append(label);
    }
    check.disabled=!editable;el('items').append(node);
  });if(!items.length)el('status').textContent='Nessun modello salvato. Premi AI per una proposta oppure aggiungi le osservazioni.';}
  async function post(operation){const body=new FormData();body.set('csrf_token',document.querySelector('meta[name="csrf-token"]').content);body.set('payload',JSON.stringify({...scope,operation,version,items:values()}));const response=await fetch(url,{method:'POST',body});const data=await response.json();if(!response.ok)throw Error(data.error||'Operazione non riuscita.');return data;}
  async function open(withAI){if(busy)return;const role=el('role'),location=el('location');if(!role.value||!location.value){el('notice').textContent='Scegli figura professionale e sede.';return;}
    scope={role_code:role.value,location:location.value};el('notice').textContent='';error('');el('status').textContent='Caricamento modello…';el('scope').textContent=role.selectedOptions[0].textContent+' · '+location.value;dialog.showModal();lock(true);el('editor-help').hidden=true;
    try{const response=await fetch(url+'?'+new URLSearchParams(scope));const data=await response.json();if(!response.ok)throw Error(data.error||'Modello non disponibile.');version=data.version;el('status').textContent=data.items.length?'Modello salvato: puoi modificarlo.':'';render(data.items);dirty=false;}
    catch(e){error(e.message);render([]);scope=null;}finally{lock(false);}
    if(withAI&&scope)await propose();
  }
  async function propose(){if(busy||!scope)return;error('');lock(true);el('status').textContent='L’AI sta preparando osservazioni e domande…';try{const data=await post('propose');render(data.items);dirty=true;el('status').textContent='Proposta AI da controllare e modificare. Non è ancora salvata.';}catch(e){error(e.message);el('status').textContent='Proposta non riuscita. Le modifiche precedenti sono conservate.';}finally{lock(false);}}
  function close(){if(busy)return;if(dirty&&!confirm('Chiudere senza salvare le modifiche?'))return;dialog.close();el('open').focus();}
  el('open').onclick=()=>open(false);if(el('ai-open'))el('ai-open').onclick=()=>open(true);if(el('ai'))el('ai').onclick=propose;
  el('close').onclick=close;if(el('cancel'))el('cancel').onclick=close;dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
  el('help-open').onclick=e=>{e.preventDefault();el('editor-help').hidden=!el('editor-help').hidden;};
  form.addEventListener('input',()=>{dirty=true;});form.addEventListener('change',()=>{dirty=true;});
  if(el('add'))el('add').onclick=()=>{const items=values();items.push({id:'obs_'+crypto.randomUUID().replaceAll('-',''),active:true,title:'',description:'',question:''});render(items);dirty=true;};
  form.onsubmit=async event=>{event.preventDefault();if(busy||!scope||!editable)return;error('');lock(true);try{const data=await post('save');version=data.version;render(data.items);dirty=false;el('status').textContent='Modello salvato per '+el('scope').textContent+'.';el('notice').textContent=el('status').textContent;}catch(e){error(e.message);}finally{lock(false);}};
})();
