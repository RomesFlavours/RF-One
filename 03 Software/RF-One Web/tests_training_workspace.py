"""Rollback-only local HTTP workflow tests; no test database or retained accounts."""
import secrets
from sqlalchemy import select,func
from sqlalchemy.orm import sessionmaker
from werkzeug.security import check_password_hash


def run(engine):
    import training_cloud as training_local
    from rfone_data_store import models as m,rfone_account_service as accounts
    from rfone_data_store.training import workspace as ws
    connection=engine.connect();transaction=connection.begin()
    factory=sessionmaker(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
    try:
        app=training_local.create_app(SessionFactory=factory)
        import training_cloud as shell, auth
        shell.SessionFactory=factory;auth.SessionFactory=factory
        app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
        client=app.test_client()
        with factory() as db:
            operator=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username=='rfone'))
            trainer_id=db.scalar(select(m.RFOneTrainingIdentityLink.training_account_id).where(m.RFOneTrainingIdentityLink.rfone_account_id==operator.id))
            employee=db.scalar(select(m.Employee).where(m.Employee.active.is_not(False)))
            from rfone_data_store.training import service as training_service
            pills=[p.id for p in training_service.list_all_pills(db)][:2]
            if len(pills)<2:
                fixture=m.TrainingPill(slug='test-content-'+secrets.token_hex(5),title='Temporary test content',learning_objectives='Rollback-only test fixture',content_version=1)
                db.add(fixture);db.flush();pills.append(fixture.id);db.commit()
            draft_course=m.TrainingPill(slug='draft-test-'+secrets.token_hex(5),title='Unpublished test course',learning_objectives='Draft only',content_version=1)
            db.add(draft_course);db.flush()
            from rfone_data_store.training import courses
            import json
            db.add(m.TrainingCourse(pill_id=draft_course.id,active_version=None,draft_json=json.dumps(courses.document(draft_course.title,'',draft_course.learning_objectives)),edit_revision=1));db.commit()
        def sign_in(c,account):
            with c.session_transaction() as s:
                s.clear();s[auth.SESSION_ACCOUNT_KEY]=account.id;s[auth.SESSION_VERSION_KEY]=account.session_version;s[auth.SESSION_CSRF_KEY]='test-csrf'
        sign_in(client,operator)
        assert client.get('/training/manage').status_code==302
        assert client.get('/training/manage').location.endswith('/training/manage/students')
        assert client.post('/training/manage').status_code==405
        for path in ('/training/manage/content','/training/manage/students'):
            response=client.get(path)
            assert response.status_code==200,(path,response.status_code)
            text=response.get_data(as_text=True)
            assert 'lang="en"' in text and 'data-how-works' in text and 'How this page works' in text
            tabs=text.split('class="tw-tabs"')[1].split('</nav>')[0]
            assert '>Assegnazioni<' not in tabs
            assert tabs.index('>Content<')<tabs.index('>Students<')
        assert client.post('/training/manage/students',data={'action':'save'}).status_code==400
        marker='training-test-'+secrets.token_hex(5)
        form=dict(action='save',name='Student Prova',username=marker,email=marker+'@example.invalid',phone='123456',password='Initial-test-123',password_confirm='Initial-test-123',csrf_token='test-csrf')
        response=client.post('/training/manage/students',data=form)
        assert response.status_code==302,response.get_data(as_text=True)
        with factory() as db:
            student=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username==marker))
            link=db.scalar(select(m.RFOneTrainingIdentityLink).where(m.RFOneTrainingIdentityLink.rfone_account_id==student.id))
            training_id=link.training_account_id
            assert db.get(ws.TrainingStudentProfile,training_id).must_change_password
            assert check_password_hash(student.password_hash,'Initial-test-123')
            assert student.password_hash!='Initial-test-123'
        from html.parser import HTMLParser
        class StudentMarkup(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.pills=[];self.inputs=[]
            def handle_starttag(self,tag,attrs):
                attributes=dict(attrs)
                if attributes.get('id'):self.ids.append(attributes['id'])
                if tag=='input':
                    self.inputs.append(attributes.get('name'))
                    if attributes.get('name')=='pills':
                        assert attributes.get('type')=='checkbox'
                        self.pills.append(int(attributes['value']))
        filtered=client.get('/training/manage/students?q='+marker).get_data(as_text=True)
        markup=StudentMarkup();markup.feed(filtered)
        assert len(markup.ids)==len(set(markup.ids))
        assert 'Assign content' in filtered and f'/students/{training_id}/assign' in filtered
        assert set(pills).issubset(set(markup.pills)) and draft_course.id not in markup.pills
        assert 'recipients' not in markup.inputs and 'purpose' not in markup.inputs
        # First access is a real login and must gate every other page.
        learner=app.test_client()
        learner.get('/training/access')
        with learner.session_transaction() as s:token=s[auth.SESSION_CSRF_KEY]
        response=learner.post('/training/access',data=dict(username=marker,password='Initial-test-123',csrf_token=token))
        assert response.status_code==302 and '/training/first-access' in response.location
        assert '/training/first-access' in learner.get('/').location
        assert '/training/first-access' in learner.get('/training/manage').location
        with learner.session_transaction() as s:token=s.setdefault(auth.SESSION_CSRF_KEY,'learner-csrf')
        assert learner.post('/training/first-access',data=dict(csrf_token=token,password='Initial-test-123',password_confirm='Initial-test-123')).status_code==400
        response=learner.post('/training/first-access',data=dict(csrf_token=token,username=marker+'-personal',password='Personal-test-456',password_confirm='Personal-test-456'))
        assert response.status_code==302
        assert learner.get('/training/manage').status_code==403
        with factory() as db:
            assert not db.get(ws.TrainingStudentProfile,training_id).must_change_password
            current=db.get(m.RFOneAccount,student.id)
            assert current.username==marker+'-personal'
            assert check_password_hash(current.password_hash,'Personal-test-456')
            assert not check_password_hash(current.password_hash,'Initial-test-123')
        # Edit without replacing credentials.
        form.update(id=str(training_id),name='Student Modificato',password='',password_confirm='')
        assert client.post('/training/manage/students',data=form).status_code==302
        client.get('/training/manage/students')
        with client.session_transaction() as s:submission=s['tw_submission']
        payload={'csrf_token':'test-csrf','submission':submission,'purpose':'Objective di verifica',
                 'recipients':[f'student:{training_id}',f'employee:{employee.id}'],'pills':list(map(str,pills))}
        with factory() as db:before=db.scalar(select(func.count()).select_from(m.TrainingAssignment))
        assert client.post(f'/training/manage/students/{training_id}/assign',data={'submission':submission}).status_code==400
        assert client.post(f'/training/manage/students/{training_id}/assign',data={'csrf_token':'test-csrf','submission':submission},headers={'Accept':'application/json'}).status_code==400
        response=client.post(f'/training/manage/students/{training_id}/assign',data=payload,headers={'Accept':'application/json'})
        assert response.status_code==200 and response.json['saved'],response.get_data(as_text=True)
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(m.TrainingAssignment))==before+2
            new_assignments=db.scalars(select(m.TrainingAssignment).where(m.TrainingAssignment.id>0).order_by(m.TrainingAssignment.id.desc()).limit(2)).all()
            assert all(a.need.student_account_id==training_id for a in new_assignments)
            retired=db.scalar(select(m.TrainingRetiredPill.pill_id))
            if retired:
                need=db.scalar(select(m.TrainingNeed.id).where(m.TrainingNeed.student_account_id==training_id))
                for operation in (
                    lambda:training_service.assign_pill(db,need_id=need,pill_id=retired,assigned_by_account_id=trainer_id),
                    lambda:training_service.assign_pills_bulk(db,need_id=need,pill_ids=[retired],assigned_by_account_id=trainer_id)):
                    try:operation()
                    except ValueError:pass
                    else:raise AssertionError('Retired content was accepted for assignment')
        assert client.post(f'/training/manage/students/{training_id}/assign',data=payload).status_code==400
        with factory() as db:
            sign_in(learner,db.get(m.RFOneAccount,student.id))
        assert learner.post(f'/training/manage/students/{training_id}/assign',data=payload).status_code==403
        assert client.post('/training/manage/students',data=dict(action='archive',id=training_id,csrf_token='test-csrf')).status_code==302
        assert learner.get('/training/manage').status_code==302
        archive=client.get('/training/manage/students?archived=1').get_data(as_text=True)
        assert 'Student Modificato' in archive
        client.get('/training/manage/students')
        with client.session_transaction() as s:submission=s['tw_submission']
        payload['submission']=submission
        assert client.post(f'/training/manage/students/{training_id}/assign',data=payload).status_code==400
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(m.TrainingAssignment))==before+2
            assert db.get(m.RFOneAccount,student.id).status=='INACTIVE'
        assert client.post('/training/manage/students',data=dict(action='restore',id=training_id,csrf_token='test-csrf')).status_code==302
        with factory() as db:assert db.get(m.RFOneAccount,student.id).status=='ACTIVE'
        # A trainer reset must force replacement and revoke the student's session.
        form.update(password='Reset-test-789',password_confirm='Reset-test-789')
        assert client.post('/training/manage/students',data=form).status_code==302
        assert learner.get('/training/first-access').status_code==302
        with factory() as db:
            assert db.get(ws.TrainingStudentProfile,training_id).must_change_password
            assert check_password_hash(db.get(m.RFOneAccount,student.id).password_hash,'Reset-test-789')
        # Never allow a trainer to edit an administrator or another Domain's account.
        assert client.post('/training/manage/students',data=dict(action='archive',id=trainer_id,csrf_token='test-csrf')).status_code==400
        for page in ('students','content','login','password'):
            assert (shell.app.root_path and __import__('pathlib').Path(shell.app.root_path,'templates','help','training_'+page+'.html').is_file())
        from pathlib import Path
        assert Path(shell.app.root_path,'templates/_how_works.html').read_bytes()==Path(shell.app.root_path).parent.joinpath('Shared UI/help/_how_works.html').read_bytes()
        print('PASS: 2 Italian tabs and help, legacy page redirects, per-student assignment modal, CSRF, student create/edit/archive/restore, first-access password replacement, permission checks, 1 fixed student x 2 contents, replay rejection and atomic rollback.')
    finally:
        transaction.rollback();connection.close()
    with engine.connect() as c:
        assert not c.scalar(select(m.RFOneAccount.id).where(m.RFOneAccount.username.in_([marker,marker+'-personal'])))
    print('PASS: test accounts and assignments rolled back; no retained test data.')
