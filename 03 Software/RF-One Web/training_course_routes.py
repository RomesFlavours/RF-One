"""Local course editor, authorized previews and assignment-version delivery."""
import io
import json
import secrets
from flask import abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from rfone_data_store import models as m
from rfone_data_store.training import courses, service
import training_integration as integration


def register(app, *, SessionFactory, auth, trainer):
    def submitted_lessons():
        names=('lesson_title','lesson_kind','lesson_url','lesson_text','lesson_file_id')
        values={name:request.form.getlist(name) for name in names}
        count=len(values['lesson_title'])
        if count>courses.MAX_LESSONS or any(len(v)!=count for v in values.values()):
            raise ValueError('L’elenco delle lezioni non è valido. Riapri la scheda.')
        return [dict(title=values['lesson_title'][i],kind=values['lesson_kind'][i],url=values['lesson_url'][i],
                     text=values['lesson_text'][i],file_id=values['lesson_file_id'][i],filename='') for i in range(count)]

    @app.post('/training/manage/content/save')
    @trainer
    def tw_save_course():
        auth.require_csrf()
        wants_json=request.accept_mimetypes.best=='application/json'
        try:
            if request.form.get('id') and request.form.get('id',type=int) is None:
                raise ValueError('Identificativo del corso non valido.')
            action=request.form.get('action','draft')
            if action not in ('draft','publish'):abort(400)
            with SessionFactory() as db:
                pill=courses.save(db,pill_id=request.form.get('id',type=int),edit_revision=request.form.get('edit_revision',type=int,default=0),
                    title=request.form.get('title',''),description=request.form.get('description',''),objective=request.form.get('objective',''),
                    lessons=submitted_lessons(),uploads=request.files.getlist('lesson_file'),publish=action=='publish')
                pill_id=pill.id
                db.commit()
        except (ValueError,IntegrityError) as exc:
            error=str(exc) if isinstance(exc,ValueError) else 'Il corso è stato aggiornato da un’altra sessione. Riapri la scheda.'
            if wants_json:return jsonify(error=error),400
            with SessionFactory() as db:
                rows=courses.catalog(db)
            try:lessons=submitted_lessons()
            except ValueError:lessons=[]
            data=courses.document(request.form.get('title',''),request.form.get('description',''),request.form.get('objective',''),lessons)
            return render_template('training_workspace/content.html',active_tab='content',help_section='training_content',
                course_rows=rows,q='',error=error,course_draft=dict(id=request.form.get('id',''),edit_revision=request.form.get('edit_revision',0),data=data)),400
        flash('Corso disponibile per le assegnazioni.' if action=='publish' else 'Bozza del corso salvata.','info')
        target=url_for('tw_content',saved=pill_id)
        if wants_json:return jsonify(redirect=target)
        return redirect(target)

    @app.get('/training/manage/content/<int:pill_id>/preview')
    @trainer
    def tw_course_preview(pill_id):
        with SessionFactory() as db:
            course=db.get(m.TrainingCourse,pill_id)
            if not course or db.get(m.TrainingRetiredPill,pill_id):abort(404)
            revision=courses.active_revision(db,pill_id)
            is_draft=request.args.get('draft')=='1' and course.draft_json is not None
            raw=course.draft_json if is_draft else revision.content_json if revision else course.draft_json
            if not raw:abort(404)
            return render_template('training_workspace/course.html',active_tab='content',help_section='training_course',
                course_data=json.loads(raw),version=revision.version if revision and not is_draft else None,
                is_draft=is_draft or revision is None,assignment_id=None,preview=True,error=None)

    def assigned_revision(db,assignment_id):
        account=auth.load_current_account(db)
        if not account:abort(404)
        result=integration.check_training_authorization(db,account)
        if not result.training_account:abort(404)
        assignment=db.get(m.TrainingAssignment,assignment_id)
        if not assignment:abort(404)
        if result.training_account.role!='trainer' and assignment.need.student_account_id!=result.training_account.id:abort(404)
        pin=db.get(m.TrainingCourseAssignmentRevision,assignment_id)
        revision=db.get(m.TrainingCourseRevision,pin.revision_id) if pin else None
        if not revision or revision.pill_id!=assignment.pill_id:abort(404)
        return assignment,revision,result.training_account

    @app.get('/training/course-assignment/<int:assignment_id>')
    def tw_assigned_course(assignment_id):
        with SessionFactory() as db:
            assignment,revision,account=assigned_revision(db,assignment_id)
            data=json.loads(revision.content_json)
            if account.role=='student':
                service.mark_assignment_opened(db,assignment);db.commit()
            return render_template('training_workspace/course.html',active_tab='course',help_section='training_course',
                course_data=data,version=revision.version,is_draft=False,assignment_id=assignment_id,preview=False,error=None)

    @app.get('/training/course-file/<int:file_id>')
    def tw_course_file(file_id):
        with SessionFactory() as db:
            account=auth.load_current_account(db)
            if not account:abort(404)
            result=integration.check_training_authorization(db,account)
            if not result.training_account:abort(404)
            file=db.get(m.TrainingCourseFile,file_id)
            if not file:abort(404)
            if result.training_account.role!='trainer':
                assignment_id=request.args.get('assignment',type=int)
                if not assignment_id:abort(404)
                assignment,revision,_=assigned_revision(db,assignment_id)
                lessons=json.loads(revision.content_json)['lessons']
                if file.pill_id!=assignment.pill_id or not any(x.get('file_id')==file_id for x in lessons):abort(404)
            response=send_file(io.BytesIO(file.data),mimetype=file.media_type,download_name=file.filename,
                as_attachment=file.media_type=='application/pdf',conditional=True,etag=file.sha256)
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['Cache-Control']='private, no-store'
            return response
