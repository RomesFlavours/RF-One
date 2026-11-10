(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('profile-data').textContent);
  var roles = new Map(data.roles.map(function (r) { return [String(r.id), r]; }));
  var areas = new Map(data.areas.map(function (a) { return [String(a.id), a]; }));
  var dialogs = {};
  document.querySelectorAll('.profile-overlay').forEach(function (overlay) {
    dialogs[overlay.id] = window.RFOneModal.create({ overlay: overlay });
  });
  function form(id) { return document.getElementById(id).querySelector('form'); }
  function reset(id) { var f = form(id); f.reset(); f.querySelectorAll('.profile-form-error').forEach(function (e) { e.remove(); }); return f; }
  function field(f, name, value) { var element = f.elements.namedItem(name); if (element) element.value = value; }
  function roleDialog(id, button) {
    var f = reset('role-dialog'), role = roles.get(String(id));
    field(f, 'id', role ? role.id : 0); field(f, 'name', role ? role.name : '');
    field(f, 'return_to', role ? 'role-' + role.id : 'catalog');
    f.querySelectorAll('[name=area_ids]').forEach(function (cb) { cb.checked = !!role && role.areas.indexOf(Number(cb.value)) >= 0; });
    document.getElementById('role-dialog-title').textContent = role ? 'Edit role · ' + role.name : 'Create role';
    dialogs['role-dialog'].open(button);
  }
  function permissionDialog(id, button) {
    var f = reset('permission-dialog'), role = roles.get(String(id)); if (!role) return;
    field(f, 'id', role.id); field(f, 'return_to', 'role-' + role.id);
    document.getElementById('permission-dialog-title').textContent = 'Permissions · ' + role.name;
    f.querySelectorAll('[data-domain]').forEach(function (box) {
      var code = box.dataset.domain, grant = role.permissions[code] || { mode: 'none', role: '', items: [] };
      field(f, 'access_' + code, grant.mode); field(f, 'role_' + code, grant.role);
      box.querySelectorAll('[type=checkbox]').forEach(function (cb) { cb.checked = grant.items.indexOf(cb.value) >= 0; });
    });
    dialogs['permission-dialog'].open(button);
  }
  function assignmentAreas() {
    var f = form('assignment-dialog'), role = roles.get(f.elements.role_id.value), select = f.elements.area_id;
    select.innerHTML = ''; select.add(new Option('Choose an area', ''));
    (role ? role.areas : []).forEach(function (id) { var area = areas.get(String(id)); if (area && area.active) select.add(new Option(area.name, id)); });
  }
  document.addEventListener('click', function (event) {
    var button = event.target.closest('button'), row = event.target.closest('[data-permission-row]');
    if (button && button.hasAttribute('data-new-role')) roleDialog(null, button);
    else if (button && button.dataset.editRole) roleDialog(button.dataset.editRole, button);
    else if (button && (button.hasAttribute('data-new-area') || button.dataset.editArea)) {
      var area = areas.get(button.dataset.editArea), f = reset('area-dialog');
      field(f, 'id', area ? area.id : 0); field(f, 'area_name', area ? area.name : ''); field(f, 'return_to', area ? 'area-' + area.id : 'catalog');
      document.getElementById('area-dialog-title').textContent = area ? 'Edit area' : 'Create area'; dialogs['area-dialog'].open(button);
    } else if (button && button.dataset.permissions) permissionDialog(button.dataset.permissions, button);
    else if (button && button.dataset.openDialog) { reset(button.dataset.openDialog); dialogs[button.dataset.openDialog].open(button); }
    else if (button && button.dataset.addAssignment) {
      var f = reset('assignment-dialog'); field(f, 'membership_id', button.dataset.addAssignment); field(f, 'return_to', 'membership-' + button.dataset.addAssignment);
      assignmentAreas(); dialogs['assignment-dialog'].open(button);
    } else if (row && !event.target.closest('a,button,input,form')) permissionDialog(row.dataset.permissionRow, row.querySelector('[data-permissions]'));
  });
  form('assignment-dialog').elements.role_id.addEventListener('change', assignmentAreas);
  form('permission-dialog').querySelectorAll('[type=checkbox]').forEach(function (checkbox) {
    checkbox.addEventListener('change', function () { if (checkbox.checked) {
      var box = checkbox.closest('[data-domain]'); var radio = box.querySelector('[type=radio][value=selected]'); if (radio) radio.checked = true;
    } });
  });

  var people = new Map(data.people.map(function(p){return [p.key,p];}));
  var editor = form('person-dialog'), roleRows = document.getElementById('person-role-rows');
  function selectedCompanies(){return Array.from(editor.querySelectorAll('[name=company_ids]:checked')).map(function(c){return c.value;});}
  function syncPersonRoles(){editor.elements.person_roles.value=JSON.stringify(Array.from(roleRows.querySelectorAll('.person-role-row')).map(function(row){return {company_id:row.dataset.companyId,role_id:row.querySelector('[data-role]').value,area_id:row.querySelector('[data-area]').value};}));}
  function systemAuthorizations(person){
    var link=document.getElementById('person-system-authorizations'),help=document.getElementById('person-authorizations-help');
    link.hidden=!person;document.getElementById('person-reset-password').hidden=!person;field(document.getElementById('person-password-form'),'person',person?person.key:'');
    var accessForm=document.getElementById('person-access-form');field(accessForm,'person',person?person.key:'');
    help.textContent=person?'RF1 account: '+person.account_label+'. Opens Domain Access for this account in a separate window. Your unsaved changes here are retained.':'Save the person first to manage their system authorizations.';
  }
  function companyGroups(){
    var selected=selectedCompanies();
    Array.from(roleRows.children).forEach(function(group){if(selected.indexOf(group.dataset.companyId)<0)group.remove();});
    editor.querySelectorAll('[name=company_ids]:checked').forEach(function(cb){
      var id=cb.value;
      if(Array.from(roleRows.children).some(function(g){return g.dataset.companyId===id;}))return;
      var group=document.createElement('section');group.className='person-company-group';group.dataset.companyId=id;
      var title=document.createElement('h4');title.textContent=cb.parentElement.textContent.trim();group.append(title);
      var rows=document.createElement('div');rows.className='company-role-rows';group.append(rows);
      var add=document.createElement('button');add.type='button';add.className='link-button';add.textContent='Add role';add.addEventListener('click',function(){roleRow({company_id:id});});group.append(add);roleRows.append(group);
    });
  }
  function roleRow(value){
    value=value||{};
    var row=document.createElement('div');row.className='person-role-row';
    function select(label,attribute){var wrap=document.createElement('label');wrap.textContent=label;var el=document.createElement('select');el.required=true;el.setAttribute(attribute,'');wrap.append(el);row.append(wrap);return el;}
    row.dataset.companyId=String(value.company_id);
    var role=select('Role','data-role'),area=select('Area','data-area');
    role.add(new Option('Choose a role',''));
    data.roles.forEach(function(r){if(r.active || Number(value.role_id)===r.id)role.add(new Option(r.name,r.id));});
    role.value=value.role_id||'';
    function fillAreas(){area.replaceChildren(new Option('Choose an area',''));var r=roles.get(role.value);(r?r.areas:[]).forEach(function(id){var a=areas.get(String(id));if(a&&(a.active||Number(value.area_id)===a.id))area.add(new Option(a.name,id));});}
    fillAreas();area.value=value.area_id||'';role.addEventListener('change',fillAreas);
    var remove=document.createElement('button');remove.type='button';remove.className='link-button';remove.textContent='Remove';remove.addEventListener('click',function(){row.remove();});row.append(remove);var group=Array.from(roleRows.children).find(function(g){return g.dataset.companyId===String(value.company_id);});if(group)group.querySelector('.company-role-rows').append(row);
  }
  document.addEventListener('click',function(e){var b=e.target.closest('[data-edit-person]');if(!b)return;var p=people.get(b.dataset.editPerson);if(!p)return;
    reset('person-dialog');field(editor,'person',p.key);field(editor,'name',p.name);field(editor,'email',p.email||'');field(editor,'phone',p.phone||'');field(editor,'tab','people');roleRows.replaceChildren();
    editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.checked=p.companies.indexOf(Number(cb.value))>=0;cb.disabled=cb.dataset.companyActive==='false'&&!cb.checked;});
    field(editor,'action','person_save');document.getElementById('person-dialog-title').textContent='Edit person';document.getElementById('person-dismissal').hidden=p.key.indexOf('employee:')!==0;document.getElementById('person-dismiss-button').disabled=true;
    systemAuthorizations(p);companyGroups();p.assignments.forEach(roleRow);dialogs['person-dialog'].open(b);
  });
  editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.addEventListener('change',companyGroups);});
  var dismissalDate=document.getElementById('person-dismissal-date'),dismissButton=document.getElementById('person-dismiss-button');
  dismissalDate.max=new Date().toISOString().slice(0,10);
  dismissalDate.addEventListener('input',function(){dismissButton.disabled=!dismissalDate.value||!dismissalDate.validity.valid;});
  document.querySelector('[data-new-person]')?.addEventListener('click',function(e){reset('person-dialog');field(editor,'person','');field(editor,'action','person_create');systemAuthorizations(null);field(editor,'tab','people');roleRows.replaceChildren();document.getElementById('person-dialog-title').textContent='Add person';document.getElementById('person-dismissal').hidden=true;editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.checked=false;cb.disabled=cb.dataset.companyActive==='false';});dialogs['person-dialog'].open(e.currentTarget);});
  editor.addEventListener('submit',function(e){
    if(e.submitter===dismissButton){if(!dismissalDate.value||!dismissalDate.validity.valid){e.preventDefault();return;}field(editor,'action','person_dismiss');}
    syncPersonRoles();
  });
  document.querySelectorAll('[data-person-filter]').forEach(function(select){select.addEventListener('change',function(){
    var name=document.getElementById('filter-name').value,company=document.getElementById('filter-company').value,role=document.getElementById('filter-role').value,count=0;
    document.querySelectorAll('[data-person-row]').forEach(function(row){var p=people.get(row.dataset.personRow);var matches=(!name||p.key===name)&&(!company||p.companies.indexOf(Number(company))>=0)&&(!role||p.assignments.some(function(a){return a.role_id===Number(role)&&(!company||a.company_id===Number(company));}));row.hidden=!matches;if(matches)count++;});document.getElementById('people-empty').hidden=count>0;
  });});
  if (data.reopen) {
    var action = (data.reopen.action || [''])[0], id = { role_save: 'role-dialog', area_save: 'area-dialog', permissions: 'permission-dialog', membership: 'membership-dialog', assignment: 'assignment-dialog', person_save: 'person-dialog', person_create: 'person-dialog', person_dismiss: 'person-dialog' }[action];
    if (id) {
      var f = reset(id);
      Object.keys(data.reopen).forEach(function (name) {
        var values = data.reopen[name];
        f.querySelectorAll('[name="' + name + '"]').forEach(function (el) {
          if (el.type === 'checkbox' || el.type === 'radio') el.checked = values.indexOf(el.value) >= 0;
          else el.value = values[0];
        });
      });
      if (id === 'assignment-dialog') { assignmentAreas(); field(f, 'area_id', (data.reopen.area_id || [''])[0]); }
      if (id === 'person-dialog') { systemAuthorizations(people.get(editor.elements.person.value)); document.getElementById('person-dialog-title').textContent=action==='person_create'?'Add person':'Edit person'; document.getElementById('person-dismissal').hidden=action==='person_create'||editor.elements.person.value.indexOf('employee:')!==0;dismissButton.disabled=!dismissalDate.value||!dismissalDate.validity.valid; roleRows.replaceChildren();companyGroups(); try { JSON.parse((data.reopen.person_roles || ['[]'])[0]).forEach(roleRow); } catch (e) {} }
      if (data.error) { var error = document.createElement('p'); error.className = 'profile-form-error'; error.setAttribute('role', 'alert'); error.textContent = data.error; f.prepend(error); }
      dialogs[id].open();
    }
  }
}());
