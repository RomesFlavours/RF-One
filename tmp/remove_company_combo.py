from pathlib import Path
p=Path('03 Software/RF-One Web/static/js/role-profiles.js');t=p.read_text(encoding='utf-8')
t=t.replace("Array.from(roleRows.children).map(function(row){return {company_id:row.querySelector('[data-company]').value", "Array.from(roleRows.querySelectorAll('.person-role-row')).map(function(row){return {company_id:row.dataset.companyId")
a=t.index('  function roleRow(value)');t=t[:a]+'''  function companyGroups(){
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
''' +t[a:]
t=t.replace("    var company=select('Company','data-company'),role=select('Role','data-role'),area=select('Area','data-area');\n    company.add(new Option('Choose a company',''));\n    editor.querySelectorAll('[name=company_ids]:checked').forEach(function(cb){company.add(new Option(cb.parentElement.textContent.trim(),cb.value));});", "    row.dataset.companyId=String(value.company_id);\n    var role=select('Role','data-role'),area=select('Area','data-area');")
t=t.replace("    company.value=value.company_id||'';role.value=value.role_id||'';", "    role.value=value.role_id||'';")
t=t.replace('row.append(remove);roleRows.append(row);', "row.append(remove);var group=Array.from(roleRows.children).find(function(g){return g.dataset.companyId===String(value.company_id);});if(group)group.querySelector('.company-role-rows').append(row);")
t=t.replace('    p.assignments.forEach(roleRow);', '    companyGroups();p.assignments.forEach(roleRow);')
a=t.index("  document.getElementById('person-add-role').addEventListener");b=t.index('  var dismissalDate=',a)
t=t[:a]+"  editor.querySelectorAll('[name=company_ids]').forEach(function(cb){cb.addEventListener('change',companyGroups);});\n"+t[b:]
t=t.replace("roleRows.replaceChildren(); try { JSON.parse", "roleRows.replaceChildren();companyGroups(); try { JSON.parse")
p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/templates/role_profiles.html');t=p.read_text(encoding='utf-8').replace('<button type="button" class="link-button" id="person-add-role">Add role</button>', '<p class="muted">Select companies above, then add their roles here.</p>').replace('?v=5','?v=6');p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/static/css/role-profiles.css');p.write_text(p.read_text(encoding='utf-8')+'\n#person-editor .person-role-row{grid-template-columns:1fr 1fr auto}.person-company-group{margin-bottom:1.2rem}.person-company-group h4{margin:.3rem 0 .8rem;color:#55652f;font-size:1rem}\n',encoding='utf-8')
