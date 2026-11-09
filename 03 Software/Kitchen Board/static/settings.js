'use strict';
const settingsForm=document.querySelector('#display-settings-form');
if(settingsForm) {
  const frame=document.querySelector('#display-preview');
  const viewport=document.querySelector('#preview-viewport');
  const it=settingsForm.dataset.locale==='it';
  function values() {
    const form=new FormData(settingsForm);
    return {font_family:form.get('font_family'),font_size:Number(form.get('font_size')),
      visible_count:Number(form.get('visible_count')),row_count:Number(form.get('row_count')),layout:form.get('layout')};
  }
  function preview() {
    const selected=values();
    document.querySelector('#layout-explanation').textContent=selected.layout==='flow'
      ?(it?'Gli ordini lunghi proseguono nel riquadro successivo.':'Long orders continue in the next cell.')
      :(it?'Ogni ordine resta in un riquadro. Il carattere si adatta alla sua lunghezza.':'Each order stays in one cell. Its text adapts to fit.');
    if(settingsForm.checkValidity()) frame.contentWindow.postMessage({type:'kitchen-board-settings',settings:selected},location.protocol==='file:'?'*':location.origin);
  }
  new ResizeObserver(()=>{frame.style.transform=`scale(${viewport.clientWidth/1920})`;}).observe(viewport);
  settingsForm.addEventListener('input',preview); settingsForm.addEventListener('change',preview);
  frame.addEventListener('load',preview);
  if(settingsForm.dataset.localPreview==='1') {
    const key='rfone-kitchen-display-'+settingsForm.dataset.location;
    try {
      const stored=JSON.parse(localStorage.getItem(key)||'null');
      if(stored) Object.entries(stored).forEach(([name,value])=>{const field=settingsForm.elements.namedItem(name); if(field)field.value=value;});
    } catch(_) {}
    settingsForm.addEventListener('submit',event=>{
      event.preventDefault(); if(!settingsForm.reportValidity())return;
      const selected=values();
      try { localStorage.setItem(key,JSON.stringify(selected)); } catch(_) {}
      document.querySelector('#local-save-status').textContent=it?'Impostazioni salvate per questa anteprima locale.':'Settings saved for this local preview.';
      const target=new URL('preview.html',location.href);
      Object.entries(selected).forEach(([name,value])=>target.searchParams.set(name,value));
      document.querySelector('#open-display').href=target.href;
      preview();
    });
  }
  preview();
}
