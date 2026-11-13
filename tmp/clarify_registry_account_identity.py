from pathlib import Path
base=Path('tmp/git-anagrafica-release/03 Software')
p=base/'RF-One Web/role_profile_routes.py';s=p.read_text(encoding='utf-8');needle="            access_url=url_for('admin_account_access',account_id=account_ids[0],from_person=key) if len(account_ids)==1 else None";assert needle in s;s=s.replace(needle,needle+"\n            linked_account=db.get(m.RFOneAccount,account_ids[0]) if len(account_ids)==1 else None\n            account_label=f'{linked_account.username} · {linked_account.status}' if linked_account else 'No unique RF1 account linked'");s=s.replace("people_rows.append({'key':key,'email'","people_rows.append({'key':key,'account_label':account_label,'email'");p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/static/js/role-profiles.js';s=p.read_text(encoding='utf-8');needle="help.textContent=person?'Opens Domain Access for this person in a separate window. Your unsaved changes here are retained.'";assert needle in s;s=s.replace(needle,"help.textContent=person?'RF1 account: '+person.account_label+'. Opens Domain Access for this account in a separate window. Your unsaved changes here are retained.'");p.write_text(s,encoding='utf-8',newline='\n')
report='''

## Anthony local identity clarification — 2026-11-10

The user configured KITCHEN-only on Anthony Watler, employee 45, linked explicitly
to inactive account 16. The active login `anthony`, account 15, was a distinct,
unlinked external account with nine direct legacy grants and no KITCHEN grant.
No authentication failure or stale permission cache caused that discrepancy.
At the user's instruction that Anthony should see only Kitchen, the existing
Registry Domain Access POST was used to set account 15 to KITCHEN-only locally.
The two identities were not merged, linked, reactivated or renamed. Existing
record 45/account 16 was untouched. Actual HTTP checks as account 15 verified
Kitchen on MyRF, four working Kitchen entries, seven other components returning
403 and no Switch user for this nonadministrator. AWS was not modified.
The person modal now identifies the exact linked RF1 username and account status
beside the authorization controls to make similar-name discrepancies visible.
'''
for p in (Path('07 Tasks/Reports/REGISTRY_AUTHORIZATION_LOCAL_FIX_20261110_REPORT.md'),Path('tmp/git-anagrafica-release/07 Tasks/Reports/REGISTRY_AUTHORIZATION_LOCAL_FIX_20261110_REPORT.md')):
 p.write_text(p.read_text(encoding='utf-8')+report,encoding='utf-8',newline='\n')
