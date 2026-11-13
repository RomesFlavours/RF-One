from pathlib import Path
root=Path('tmp/git-anagrafica-release/03 Software/RF-One Web')
p=root/'templates/role_profiles.html';s=p.read_text(encoding='utf-8').replace('<form id="person-password-form" method="post">','<form id="person-password-form" method="post" target="_blank" rel="noopener">').replace('<form id="person-access-form" method="post">','<form id="person-access-form" method="post" target="_blank" rel="noopener">');p.write_text(s,encoding='utf-8',newline='\n')
p=root/'static/js/role-profiles.js';s=p.read_text(encoding='utf-8').replace('. Opens Domain Access for this account. Save changes to the person before leaving this editor.','. Opens Domain Access for this account in a separate window. Your unsaved changes here are retained.');p.write_text(s,encoding='utf-8',newline='\n')
