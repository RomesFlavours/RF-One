from pathlib import Path
p=Path('03 Software/RF-One Web/static/js/role-profiles.js');t=p.read_text(encoding='utf-8');idx=t.index('  if (data.reopen)')
t=t[:idx]+'''
  var people = new Map(data.people.map(function(p){return [p.key,p];}));
  var editor = form('person-dialog'), roleRows = document.getElementById('person-role-rows');
  function selectedCompanies(){return Array.from(editor.querySelectorAll('[name=company_ids]:checked')).map(function(c){return c.value;});}
  function syncPersonRoles(){editor.elements.person_roles.value=JSON.stringify(Array.from(roleRows.children).map(function(row){return {company_id:row.querySelector('[data-company]').value,role_id:row.querySelector('[data-role]').value,area_id:row.querySelector('[data-area]').value};}));}
  function roleRow(value){
    value=value||{};
    var row=document.createElement('div');row.className='person-role-row';
    function select(label,attribute){var wrap=document.createElement('label');wrap.textContent=label;var el=document.createElement('select');el.required=true;el.setAttribute(attribute,'');wrap.append(el);row.append(wrap);return el;}
    var company=select('Company','data-company'),role=select('Role','data-role'),area=select('Area','data-area');
    company.add(new Option('Choose a company',''));
    editor.querySelectorAll('[name=company_ids]:checked').forEach(function(cb){company.add(new Option(cb.parentElement.textContent.trim(),cb.value));});
    role.add(new Option('Choose a role',''));
    data.roles.forEach(function(r){if(r.active || Number(value.role_id)===r.id)role.add(new Option(r.name,r.id));});
    company.value=value.company_id||'';role.value=value.role_id||'';
    function fillAreas(){area.replaceChildren(new Option('Choose an area',''));var r=roles.get(role.value);(r?r.areas:[]).forEach(function(id){var a=areas.get(String(id));if(a&&(a.active||Number(value.area_id)===a.id))area.add(new Option(a.name,id));});}
    fillAreas();area.value=value.area_id||'';role.addEventListener('change',fillAreas);
    var remove=document.createElement('button');remove.type='button';remove.className='link-button';remove.textContent='Remove';remove.addEventListener('click',function(){row.remove();});row.append(remove);roleRows.append(row);
  }
  document.addEventListener('click',function(e){var b=e.target.closest('[data-edit-person]');if(!b)return;var p=people.get(b.dataset.editPerson);if(!p)return;
    reset('person-dialog');field(editor,'person',p.key);field(editor,'name',p.name);field(editor,'tab','people');roleRows.replaceChildren();
    editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.checked=p.companies.indexOf(Number(cb.value))>=0;cb.disabled=cb.dataset.companyActive==='false'&&!cb.checked;});
    p.assignments.forEach(roleRow);dialogs['person-dialog'].open(b);
  });
  document.getElementById('person-add-role').addEventListener('click',function(){roleRow();});
  editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.addEventListener('change',function(){
    var selected=selectedCompanies();Array.from(roleRows.children).forEach(function(row){var c=row.querySelector('[data-company]'),before=c.value;if(before&&selected.indexOf(before)<0){row.remove();return;}c.replaceChildren(new Option('Choose a company',''));editor.querySelectorAll('[name=company_ids]:checked').forEach(function(x){c.add(new Option(x.parentElement.textContent.trim(),x.value));});c.value=before;});
  });});
  editor.addEventListener('submit',syncPersonRoles);
  document.querySelectorAll('[data-person-filter]').forEach(function(select){select.addEventListener('change',function(){
    var name=document.getElementById('filter-name').value,company=document.getElementById('filter-company').value,role=document.getElementById('filter-role').value,count=0;
    document.querySelectorAll('[data-person-row]').forEach(function(row){var p=people.get(row.dataset.personRow);var matches=(!name||p.key===name)&&(!company||p.companies.indexOf(Number(company))>=0)&&(!role||p.assignments.some(function(a){return a.role_id===Number(role)&&(!company||a.company_id===Number(company));}));row.hidden=!matches;if(matches)count++;});document.getElementById('people-empty').hidden=count>0;
  });});
''' +t[idx:]
t=t.replace("assignment: 'assignment-dialog'", "assignment: 'assignment-dialog', person_save: 'person-dialog'")
t=t.replace("      if (data.error) {", "      if (id === 'person-dialog') { roleRows.replaceChildren(); try { JSON.parse((data.reopen.person_roles || ['[]'])[0]).forEach(roleRow); } catch (e) {} }\n      if (data.error) {")
p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/static/css/role-profiles.css');p.write_text(p.read_text(encoding='utf-8')+'''\n.profile-people-table summary {cursor:pointer;font-size:1.2rem;font-weight:600;padding:1rem 0}.profile-people-table th select {display:block;margin-top:.5rem;width:100%;min-width:150px}.person-role-row {display:flex;gap:.75rem;align-items:end;margin-bottom:1rem;flex-wrap:wrap}.person-role-row label {flex:1;min-width:130px}.person-role-row select {width:100%}.sr-only {position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}\n''',encoding='utf-8')
