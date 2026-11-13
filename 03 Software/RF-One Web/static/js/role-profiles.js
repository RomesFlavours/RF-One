(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('profile-data').textContent);
  var labels = {"How Registry works": "Come funziona Registry", "How this page works": "Come funziona questa pagina", "Close": "Chiudi", "Identity reconciliation": "Riconciliazione identità", "Assign people to one or more companies. Their role permissions add together within each company.": "Gestisci persone, rapporti aziendali e accessi. Le autorizzazioni dei ruoli si sommano nella stessa azienda.", "People & assignments": "Persone e incarichi", "People": "Persone", "Roles": "Ruoli", "Areas": "Aree", "Companies": "Aziende", "Company": "Azienda", "Switch": "Cambia", "Role management": "Gestione ruoli", "Add person": "Aggiungi persona", "Edit person": "Modifica persona", "Full name": "Nome e cognome", "Phone": "Telefono", "Company status": "Status Aziendale", "Account status": "Status dell’account", "Candidate": "Candidato", "External": "Esterno", "Employee": "Dipendente", "Multiple relationships allowed; independent of roles and permissions.": "Sono consentite più qualifiche, indipendenti da ruoli e permessi.", "Access also requires credentials and permissions.": "L’accesso richiede anche credenziali e autorizzazioni.", "Active": "Attivo", "Inactive": "Inattivo", "No linked account": "Nessun account collegato", "Companies and roles": "Aziende e ruoli", "Company · select one or more": "Aziende · selezione multipla", "Roles by company and area": "Ruoli per azienda e area", "Select companies above, then add their roles here.": "Seleziona le aziende, poi aggiungi i relativi ruoli.", "Credentials and permissions": "Credenziali e autorizzazioni", "Other system authorizations": "Altre autorizzazioni", "Reset password": "Reimposta password", "End employment": "Cessazione del rapporto", "Keep their history and remove them from active selections.": "Conserva lo storico ed escludi la persona dalle selezioni attive.", "Dismissal date": "Data cessazione", "Dismiss person": "Registra cessazione", "Save changes": "Salva", "Cancel": "Annulla", "Person editor help": "Aiuto gestione persona", "Name": "Nome", "Filter Name": "Filtra nome", "All names": "Tutti i nomi", "Filter Company": "Filtra azienda", "All companies": "Tutte le aziende", "Role": "Ruolo", "Filter Role": "Filtra ruolo", "All roles": "Tutti i ruoli", "Actions": "Azioni", "Edit": "Modifica", "No matching people.": "Nessuna persona corrispondente.", "Recent changes": "Modifiche recenti", "No changes yet.": "Nessuna modifica.", "No dismissed people.": "Nessuna persona cessata.", "Not recorded": "Non registrata", "Dismissis": "Persone cessate", "Active roles": "Ruoli attivi", "Create role": "Crea ruolo", "Permissions": "Autorizzazioni", "No roles.": "Nessun ruolo.", "Active areas": "Aree attive", "Create area": "Crea area", "Area": "Area", "No active areas.": "Nessuna area attiva.", "Archived areas": "Aree archiviate", "No archived areas.": "Nessuna area archiviata.", "Companies & group": "Aziende e gruppo", "Type": "Tipo", "Status": "Stato", "Group": "Gruppo", "Archived": "Archiviato", "Archive": "Archivia", "Restore": "Ripristina", "Save role": "Salva ruolo", "Save area": "Salva area", "Save permissions": "Salva autorizzazioni", "Role permissions": "Autorizzazioni del ruolo", "Manage permissions": "Gestisci autorizzazioni", "Not assigned": "Non assegnato", "No access": "Nessun accesso", "Whole domain": "Intero dominio", "Selected functions": "Funzioni selezionate", "Level": "Livello", "No Training role": "Nessun ruolo Training", "User": "Utente", "Student": "Studente", "Trainer": "Formatore", "Domain administrator": "Amministratore del dominio", "Add role": "Aggiungi ruolo", "Choose a role": "Scegli un ruolo", "Choose an area": "Scegli un’area", "Remove": "Rimuovi", "Edit area": "Modifica area", "RF1 account: ": "Account RF1: ", ". Opens Domain Access for this account in a separate window. Your unsaved changes here are retained.": ". Le autorizzazioni si aprono in un’altra finestra; la bozza resta conservata.", "Save the person first to manage their system authorizations.": "Salva prima la persona per gestirne credenziali e autorizzazioni.", "Enter a valid email address.": "Inserisci un indirizzo email valido.", "Invalid email.": "Email non valida.", "Invalid phone.": "Telefono non valido.", "Choose an active account.": "Scegli un account attivo.", "Choose a person or external account.": "Scegli una persona o un account esterno.", "Invalid person reference.": "Riferimento persona non valido.", "Dismissed people cannot receive new assignments.": "Le persone cessate non possono ricevere nuovi incarichi.", "Each role must belong to a selected company.": "Ogni ruolo deve appartenere a un’azienda selezionata.", "Invalid role assignments.": "Incarichi non validi.", "Invalid role assignment.": "Incarico non valido.", "Choose an active company.": "Scegli un’azienda attiva.", "A matching active record already exists. Nothing saved.": "Esiste già un record attivo corrispondente. Nessuna modifica salvata."};
  function tr(value){return data.localItalian ? (labels[value] || value) : value;}
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
  // The Level only matters when the domain grants access (Whole domain or
  // Selected functions); with No access it is disabled and shown empty, so
  // the dialog never suggests a level that would not be saved.
  function syncLevel(box) {
    var checked = box.querySelector('[type=radio]:checked'), select = box.querySelector('select[name^="role_"]');
    if (!select) return;
    var placeholder = select.querySelector('option[data-no-level]');
    if (!placeholder) {
      placeholder = new Option('—', '__none__'); placeholder.dataset.noLevel = '1'; placeholder.hidden = true;
      select.insertBefore(placeholder, select.firstChild);
    }
    var none = !checked || checked.value === 'none';
    if (none) { select.disabled = true; placeholder.selected = true; }
    else { select.disabled = false; if (placeholder.selected) select.value = ''; }
  }
  function syncLevels(f) { f.querySelectorAll('[data-domain]').forEach(syncLevel); }
  function permissionDialog(id, button) {
    var f = reset('permission-dialog'), role = roles.get(String(id)); if (!role) return;
    field(f, 'id', role.id); field(f, 'return_to', 'role-' + role.id);
    document.getElementById('permission-dialog-title').textContent = 'Permissions · ' + role.name;
    f.querySelectorAll('[data-domain]').forEach(function (box) {
      var code = box.dataset.domain, grant = role.permissions[code] || { mode: 'none', role: '', items: [] };
      field(f, 'access_' + code, grant.mode); field(f, 'role_' + code, grant.role);
      box.querySelectorAll('[type=checkbox]').forEach(function (cb) { cb.checked = grant.items.indexOf(cb.value) >= 0; });
    });
    syncLevels(f);
    dialogs['permission-dialog'].open(button);
  }
  function assignmentAreas() {
    var f = form('assignment-dialog'), role = roles.get(f.elements.role_id.value), select = f.elements.area_id;
    select.innerHTML = ''; select.add(new Option(tr("Choose an area"), ''));
    (role ? role.areas : []).forEach(function (id) { var area = areas.get(String(id)); if (area && area.active) select.add(new Option(area.name, id)); });
  }
  document.addEventListener('click', function (event) {
    var button = event.target.closest('button'), row = event.target.closest('[data-permission-row]');
    if (button && button.hasAttribute('data-new-role')) roleDialog(null, button);
    else if (button && button.dataset.editRole) roleDialog(button.dataset.editRole, button);
    else if (button && (button.hasAttribute('data-new-area') || button.dataset.editArea)) {
      var area = areas.get(button.dataset.editArea), f = reset('area-dialog');
      field(f, 'id', area ? area.id : 0); field(f, 'area_name', area ? area.name : ''); field(f, 'return_to', area ? 'area-' + area.id : 'catalog');
      document.getElementById('area-dialog-title').textContent = area ? tr("Edit area") : tr("Create area"); dialogs['area-dialog'].open(button);
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
      syncLevel(box);
    } });
  });
  form('permission-dialog').querySelectorAll('[data-domain] [type=radio]').forEach(function (radio) {
    radio.addEventListener('change', function () { syncLevel(radio.closest('[data-domain]')); });
  });

  var people = new Map(data.people.map(function(p){return [p.key,p];}));
  var editor = form('person-dialog'), roleRows = document.getElementById('person-role-rows');
  function selectedCompanies(){return Array.from(editor.querySelectorAll('[name=company_ids]:checked')).map(function(c){return c.value;});}
  function syncPersonRoles(){editor.elements.person_roles.value=JSON.stringify(Array.from(roleRows.querySelectorAll('.person-role-row')).map(function(row){return {company_id:row.dataset.companyId,role_id:row.querySelector('[data-role]').value,area_id:row.querySelector('[data-area]').value};}));}
  function systemAuthorizations(person){
    var link=document.getElementById('person-system-authorizations'),help=document.getElementById('person-authorizations-help');
    link.hidden=!person;document.getElementById('person-reset-password').hidden=!person;field(document.getElementById('person-password-form'),'person',person?person.key:'');
    var accessForm=document.getElementById('person-access-form');field(accessForm,'person',person?person.key:'');
    help.textContent=person?tr('RF1 account: ')+person.account_label+tr('. Opens Domain Access for this account in a separate window. Your unsaved changes here are retained.'):tr('Save the person first to manage their system authorizations.');
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
      var add=document.createElement('button');add.type='button';add.className='link-button';add.textContent=tr("Add role");add.addEventListener('click',function(){roleRow({company_id:id});});group.append(add);roleRows.append(group);
    });
  }
  function roleRow(value){
    value=value||{};
    var row=document.createElement('div');row.className='person-role-row';
    function select(label,attribute){var wrap=document.createElement('label');wrap.textContent=label;var el=document.createElement('select');el.required=true;el.setAttribute(attribute,'');wrap.append(el);row.append(wrap);return el;}
    row.dataset.companyId=String(value.company_id);
    var role=select(tr("Role"),'data-role'),area=select(tr("Area"),'data-area');
    role.add(new Option(tr("Choose a role"),''));
    data.roles.forEach(function(r){if(r.active || Number(value.role_id)===r.id)role.add(new Option(r.name,r.id));});
    role.value=value.role_id||'';
    function fillAreas(){area.replaceChildren(new Option(tr("Choose an area"),''));var r=roles.get(role.value);(r?r.areas:[]).forEach(function(id){var a=areas.get(String(id));if(a&&(a.active||Number(value.area_id)===a.id))area.add(new Option(a.name,id));});}
    fillAreas();area.value=value.area_id||'';role.addEventListener('change',fillAreas);
    var remove=document.createElement('button');remove.type='button';remove.className='link-button';remove.textContent=tr("Remove");remove.addEventListener('click',function(){row.remove();});row.append(remove);var group=Array.from(roleRows.children).find(function(g){return g.dataset.companyId===String(value.company_id);});if(group)group.querySelector('.company-role-rows').append(row);
  }
  function statusFields(person){
    field(editor,'account_status',person ? person.account_status : 'INACTIVE');
    var select=editor.elements.account_status;
    select.querySelector('[value=NONE]').disabled=!person || person.account_status!=='NONE';
    select.querySelector('[value=INACTIVE]').disabled=!!(person && person.account_status_locked);
    editor.querySelectorAll('[name=company_status]').forEach(function(cb){cb.checked=!!person && person.company_statuses.indexOf(cb.value)>=0;});
  }
  function editPerson(p,b){
    if(!p)return;
    reset('person-dialog');field(editor,'person',p.key);field(editor,'name',p.name);field(editor,'email',p.email||'');field(editor,'phone',p.phone||'');field(editor,'tab','people');roleRows.replaceChildren();
    editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.checked=p.companies.indexOf(Number(cb.value))>=0;cb.disabled=cb.dataset.companyActive==='false'&&!cb.checked;});
    field(editor,'action','person_save');document.getElementById('person-dialog-title').textContent=tr("Edit person");document.getElementById('person-dismissal').hidden=p.key.indexOf('employee:')!==0;document.getElementById('person-dismiss-button').disabled=true;
    statusFields(p);systemAuthorizations(p);companyGroups();p.assignments.forEach(roleRow);dialogs['person-dialog'].open(b);
  }
  document.addEventListener('click',function(e){var b=e.target.closest('[data-edit-person]');if(b)editPerson(people.get(b.dataset.editPerson),b);});
  editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.addEventListener('change',companyGroups);});
  var dismissalDate=document.getElementById('person-dismissal-date'),dismissButton=document.getElementById('person-dismiss-button');
  dismissalDate.max=new Date().toISOString().slice(0,10);
  dismissalDate.addEventListener('input',function(){dismissButton.disabled=!dismissalDate.value||!dismissalDate.validity.valid;});
  document.querySelector('[data-new-person]')?.addEventListener('click',function(e){reset('person-dialog');field(editor,'person','');field(editor,'action','person_create');statusFields(null);systemAuthorizations(null);field(editor,'tab','people');roleRows.replaceChildren();document.getElementById('person-dialog-title').textContent=tr("Add person");document.getElementById('person-dismissal').hidden=true;editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.checked=false;cb.disabled=cb.dataset.companyActive==='false';});dialogs['person-dialog'].open(e.currentTarget);});
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
      if (id === 'permission-dialog') syncLevels(f);
      if (id === 'assignment-dialog') { assignmentAreas(); field(f, 'area_id', (data.reopen.area_id || [''])[0]); }
      if (id === 'person-dialog') { systemAuthorizations(people.get(editor.elements.person.value)); document.getElementById('person-dialog-title').textContent=action==='person_create'?tr("Add person"):tr("Edit person"); document.getElementById('person-dismissal').hidden=action==='person_create'||editor.elements.person.value.indexOf('employee:')!==0;dismissButton.disabled=!dismissalDate.value||!dismissalDate.validity.valid; roleRows.replaceChildren();companyGroups(); try { JSON.parse((data.reopen.person_roles || ['[]'])[0]).forEach(roleRow); } catch (e) {} }
      if (data.error) { var error = document.createElement('p'); error.className = 'profile-form-error'; error.setAttribute('role', 'alert'); error.textContent = data.error; f.prepend(error); }
      dialogs[id].open();
    }
  }
  if (!data.reopen && data.returnPerson) {
    var returnPerson=people.get(data.returnPerson);
    if(returnPerson){
      var table=document.getElementById('people-table');if(table)table.open=true;
      var button=Array.from(document.querySelectorAll('[data-edit-person]')).find(function(b){return b.dataset.editPerson===data.returnPerson;});
      if(button){button.focus({preventScroll:true});if(!sessionStorage.getItem('rfone-row-return'))button.scrollIntoView({block:'nearest'});}
    }
  }
}());
