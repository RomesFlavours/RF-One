from pathlib import Path
base=Path('tmp/git-anagrafica-release/03 Software')
p=base/'Tips/app.py';s=p.read_text(encoding='utf-8');marker='# RF-One UI Rules (`03 Software/Shared UI/UI Rules.md`): local times,';assert marker in s;s=s.replace(marker,'''@app.before_request
def _central_training_entry():
    # The public dish guide is a separate endpoint, not this blueprint.
    # Operational Training has one RF1 entry; legacy Training cookies and
    # its old student-provisioning/login routes must not bypass Registry.
    if request.blueprint != "training":
        return None
    with SessionFactory() as db:
        from rfone_data_store.web_access import training_account_for_rf1
        if training_account_for_rf1(db, rfone_identity.current_account(db)) is None:
            abort(403)
    base = rfone_web_link.base_url()
    if base is None:
        abort(503, description="RF-One Web navigation is not configured.")
    target = request.path
    if target in ("/training/login", "/training/logout"):
        target = "/training"
    return redirect(base + target, code=303 if request.method == "POST" else 302)


'''+marker);p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/tests/test_training_integration_http.py';s=p.read_text(encoding='utf-8');a=s.index('            "import re\\n"',s.index('tips_check_code ='));b=s.index('            "print(\'TIPS_HOME_STATUS',a);s=s[:a]+'''            "r3 = c.post('/training/login', data={'username': 'legacy', 'password': 'whatever'})\\n"
'''+s[b:];s=s.replace("Training's OWN login under Tips is untouched (still rejects a wrong password)","Tips cannot use a legacy Training login to bypass Registry").replace('"TIPS_TRAINING_LOGIN_STATUS 401"','"TIPS_TRAINING_LOGIN_STATUS 403"');p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/tests/test_registry_standalone_access.py';s=p.read_text(encoding='utf-8');needle='print(json.dumps({"service":service';start=s.index(needle);s=s[:start]+'''if service == "tips":
    with factory() as db:
        db.get(m.RFOneAccount,uid).status="ACTIVE"
        from rfone_data_store.training import service as training
        identity=training.create_account(db,display_name="Fixture",username="training-fixture",password="Unused123!",role="trainer")
        db.add(m.RFOneTrainingIdentityLink(rfone_account_id=uid,training_account_id=identity.id))
        grant=p.RolePermission(role_id=rid,domain_code="TRAINING",scope="ALL",role_code="student",items=[])
        db.add(grant);db.commit();training_id=identity.id
    os.environ["RFONE_WEB_BASE_URL"]="http://localhost:5000"
    response=c.get('/training')
    assert response.status_code==302 and response.location=='http://localhost:5000/training'
    checks.append('Operational Training uses canonical RF1 entry')
    with factory() as db:
        db.delete(db.query(p.RolePermission).filter_by(role_id=rid,domain_code='TRAINING').one());db.commit()
    with c.session_transaction() as browser:browser['training_account_id']=training_id
    assert c.get('/training/trainer').status_code==403
    assert c.post('/training/login',data={'username':'training-fixture','password':'Unused123!'}).status_code==403
    checks.extend(['Revoked Training denies legacy session','Legacy Training password cannot bypass Registry'])
'''+s[start:];p.write_text(s,encoding='utf-8',newline='\n')
