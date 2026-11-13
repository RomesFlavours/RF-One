from pathlib import Path
root=Path('tmp/git-anagrafica-release/03 Software/RF-One Web');p=root/'app.py';s=p.read_text(encoding='utf-8');needle='    return redirect(profile_return) if saved else redirect(url_for("admin_account_edit", account_id=account_id, from_person=profile_person, _anchor="reset-password"))';replacement='''    if saved and account_id == current_account_id():
        # Resetting one's own password invalidates the session. Preserve the
        # canonical return through the existing login instead of losing it.
        log_out()
        flash("Password updated. Sign in again to continue.", "info")
        return redirect(url_for("login", next=profile_return))
'''+needle;assert needle in s;s=s.replace(needle,replacement);p.write_text(s,encoding='utf-8',newline='\n')
p=root/'tests/test_registry_navigation.py';s=p.read_text(encoding='utf-8');needle=' def test_nonadmin_cannot_use_navigation_to_gain_access(self):';s=s.replace(needle,''' def test_z_own_password_reset_preserves_person_through_login(self):
  r=self.post(f'/admin/accounts/{self.owner}/reset-password',password='Owner-fixture-pass-123',password_confirm='Owner-fixture-pass-123')
  self.assertEqual(r.status_code,302);u=urlsplit(r.location);self.assertEqual(u.path,'/login')
  destination=parse_qs(u.query)['next'][0];self.assertEqual(parse_qs(urlsplit(destination).query)['person'],[f'employee:{self.person}'])
  self.assertEqual(urlsplit(destination).path,'/admin/roles')
'''+needle);p.write_text(s,encoding='utf-8',newline='\n')
# Preserve this case in the immutable release transformer too.
p=Path('tmp/registry-navigation-release/artifact/navigation/apply.py');s=p.read_text(encoding='utf-8');s += '\n'+repr('')+'\n' if False else ''
s += '\np=root/"app.py"\ns=p.read_text(encoding="utf-8")\nneedle='+repr(needle if False else '    return redirect(profile_return) if saved else redirect(url_for("admin_account_edit", account_id=account_id, from_person=profile_person, _anchor="reset-password"))')+'\ns=s.replace(needle,'+repr(replacement)+')\np.write_text(s,encoding="utf-8",newline="\\n")\n'
p.write_text(s,encoding='utf-8',newline='\n')
import shutil
shutil.copyfile(root/'tests/test_registry_navigation.py','tmp/registry-navigation-release/artifact/navigation/test_registry_navigation.py')
