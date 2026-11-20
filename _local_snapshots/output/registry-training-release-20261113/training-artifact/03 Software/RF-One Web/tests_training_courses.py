"""Course authoring and delivery HTTP tests; all created data is rolled back."""
import io
import json
import secrets
from sqlalchemy import select,func
from sqlalchemy.orm import sessionmaker


def run(engine):
    import training_cloud as training_local
    from rfone_data_store import models as m
    from rfone_data_store.training import courses,service,workspace
    connection=engine.connect();transaction=connection.begin()
    factory=sessionmaker(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
    marker='course-test-'+secrets.token_hex(6)
    try:
        app=training_local.create_app(SessionFactory=factory)
        import training_cloud as shell,auth,training_integration as integration
        shell.SessionFactory=factory;auth.SessionFactory=factory;app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
        trainer=app.test_client()
        def sign_in(client,account):
            with client.session_transaction() as s:
                s.clear();s[auth.SESSION_ACCOUNT_KEY]=account.id;s[auth.SESSION_VERSION_KEY]=account.session_version;s[auth.SESSION_CSRF_KEY]='course-csrf'
        with factory() as db:
            operator=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username=='rfone'))
            trainer_id=integration.get_link_for_rfone_account(db,operator.id).training_account_id
            initial_count=db.scalar(select(func.count()).select_from(m.TrainingPill))
        sign_in(trainer,operator)
        from html.parser import HTMLParser
        class Markup(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.forms=[]
            def handle_starttag(self,tag,attrs):
                attributes=dict(attrs)
                if 'id' in attributes:self.ids.append(attributes['id'])
                if tag=='form':self.forms.append(attributes.get('id'))
        markup=Markup();markup.feed(trainer.get('/training/manage/content').get_data(as_text=True))
        assert len(markup.ids)==len(set(markup.ids)), 'Duplicate IDs prevent the editor from addressing the correct form.'
        assert 'course-editor-form' in markup.forms
        def save(data):
            return trainer.post('/training/manage/content/save',data={'csrf_token':'course-csrf',**data},headers={'Accept':'application/json'})
        data=dict(action='draft',title=marker,description='Description di prova',objective='Objective di prova')
        assert save(data).status_code==200
        with factory() as db:
            pill=db.scalar(select(m.TrainingPill).where(m.TrainingPill.title==marker));pill_id=pill.id
            assert db.get(m.TrainingCourse,pill_id).active_version is None
            assert pill_id not in [p.id for p in service.list_all_pills(db)]
        assert marker not in trainer.get('/training/manage/students').get_data(as_text=True)
        assert marker in trainer.get('/training/manage/content').get_data(as_text=True)
        data.update(id=str(pill_id),edit_revision='1',action='publish')
        response=save(data);assert response.status_code==400 and 'at least one complete lesson' in response.json['error']
        pdf=b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n'
        data.update(lesson_title=['Text introduttivo','Manuale PDF'],lesson_kind=['text','file'],
            lesson_url=['',''],lesson_text=['<script>alert(1)</script>',''],lesson_file_id=['',''],
            lesson_file=[(io.BytesIO(b''),''),(io.BytesIO(pdf),'manuale.pdf')])
        response=save(data);assert response.status_code==200,response.json
        with factory() as db:
            first=courses.active_revision(db,pill_id);first_id=first.id
            snapshot=json.loads(first.content_json);file_id=snapshot['lessons'][1]['file_id']
            assert first.version==1 and pill_id in [p.id for p in service.list_all_pills(db)]
            learner,student=integration.create_student_via_rf_one(db,username=marker,display_name='Student Test Corsi',password=secrets.token_urlsafe(20),email=marker+'@example.invalid')
            learner2,_=integration.create_student_via_rf_one(db,username=marker+'-other',display_name='Altro Student Test',password=secrets.token_urlsafe(20),email=marker+'-other@example.invalid')
            need=service.create_need(db,student_account_id=student.id,text='Studio del corso',origin='other',created_by_account_id=trainer_id)
            assignment=service.assign_pill(db,need_id=need.id,pill_id=pill_id,assigned_by_account_id=trainer_id)
            assignment_id=assignment.id
            assert db.get(m.TrainingCourseAssignmentRevision,assignment.id).revision_id==first_id
            db.commit()
        student_client=app.test_client();sign_in(student_client,learner)
        other=app.test_client();sign_in(other,learner2)
        assert other.get(f'/training/course-assignment/{assignment_id}').status_code==404
        assert other.get(f'/training/course-file/{file_id}?assignment={assignment_id}').status_code==404
        assert app.test_client().get(f'/training/course-file/{file_id}').status_code==404
        assert student_client.get(f'/training/course-file/{file_id}').status_code==404
        response=student_client.get(f'/training/course-file/{file_id}?assignment={assignment_id}')
        assert response.status_code==200 and response.data==pdf and response.headers['X-Content-Type-Options']=='nosniff'
        page=student_client.get(f'/training/course-assignment/{assignment_id}')
        assert page.status_code==200 and b'&lt;script&gt;alert(1)&lt;/script&gt;' in page.data
        assert b'How this page works' in page.data
        assert student_client.post('/training/manage/content/save',data=dict(csrf_token='course-csrf',title='Forbidden')).status_code==403
        # Draft edits must not replace active content or assignment snapshots.
        change=dict(id=str(pill_id),edit_revision='2',action='draft',title=marker+' aggiornato',description='Nuova descrizione',objective='Nuovo obiettivo',
            lesson_title=['Nuovo testo'],lesson_kind=['text'],lesson_url=[''],lesson_text=['Materiale della nuova versione'],lesson_file_id=[''])
        assert save(change).status_code==200
        with factory() as db:
            assert courses.active_revision(db,pill_id).id==first_id
            assert db.get(m.TrainingPill,pill_id).title==marker
        assert save(change).status_code==400 # stale edit revision
        change.update(edit_revision='3',action='publish')
        assert save(change).status_code==200
        with factory() as db:
            second=courses.active_revision(db,pill_id)
            assert second.version==2 and second.id!=first_id
            assert db.get(m.TrainingCourseAssignmentRevision,assignment_id).revision_id==first_id
            assert json.loads(db.get(m.TrainingCourseRevision,first_id).content_json)==snapshot
        assert 'Version 1' in student_client.get(f'/training/course-assignment/{assignment_id}').get_data(as_text=True)
        assert student_client.get(f'/training/course-file/{file_id}?assignment={assignment_id}').data==pdf
        preview=trainer.get(f'/training/manage/content/{pill_id}/preview')
        assert preview.status_code==200 and 'Version 2' in preview.get_data(as_text=True)
        # Reject unsafe/invalid material and roll back partially created courses/files.
        invalid=dict(action='publish',title=marker+' invalid',description='Description',objective='Objective',
            lesson_title=['Documento'],lesson_kind=['file'],lesson_url=[''],lesson_text=[''],lesson_file_id=[''],
            lesson_file=[(io.BytesIO(b'<html>unsafe</html>'),'wrong.pdf')])
        assert save(invalid).status_code==400
        invalid.pop('lesson_file');invalid.update(lesson_kind=['link'],lesson_url=['javascript:alert(1)'])
        assert save(invalid).status_code==400
        invalid['lesson_kind']=['internal'];invalid['lesson_url']=['//outside.example/path']
        assert save(invalid).status_code==400
        assert save(dict(title=marker+' malformed',lesson_title=['One'])).status_code==400
        assert trainer.post('/training/manage/content/save',data={'title':'No CSRF'}).status_code==400
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(m.TrainingPill))==initial_count+1
            visual=db.scalar(select(m.TrainingPill).where(m.TrainingPill.slug=='visual-menu'))
            assert json.loads(courses.active_revision(db,visual.id).content_json)['lessons'][0]['url']=='/training/visual-menu'
        print('PASS: draft creation, incomplete activation rejected, PDF upload, ordered lessons, activation, draft isolation, conflicting save rejected, immutable versions and assignment pinning.')
        print('PASS: protected file delivery, cross-student denial, escaped text, malformed material/links rejected, CSRF, English course view/help and Visual Menu preservation.')
    finally:
        transaction.rollback();connection.close()
    with engine.connect() as c:
        assert not c.scalar(select(m.TrainingPill.id).where(m.TrainingPill.title.like(marker+'%')))
        assert not c.scalar(select(m.RFOneAccount.id).where(m.RFOneAccount.username.like(marker+'%')))
    print('PASS: all test courses, uploads, accounts, versions and assignments rolled back.')
