"""Versioned course repository extending TrainingPill; caller owns transactions."""
import hashlib
import json
import secrets
from urllib.parse import urlsplit, unquote
from sqlalchemy import select, func
from werkzeug.utils import secure_filename
from .. import models as m

MAX_FILE_BYTES=25*1024*1024
MAX_LESSONS=30


def document(title='',description='',objective='',lessons=None):
    return dict(title=title,description=description,objective=objective,lessons=lessons or [])


def active_revision(db,pill_id):
    course=db.get(m.TrainingCourse,pill_id)
    if not course or course.active_version is None:return None
    return db.scalar(select(m.TrainingCourseRevision).where(
        m.TrainingCourseRevision.pill_id==pill_id,m.TrainingCourseRevision.version==course.active_version))


def catalog(db):
    rows=db.execute(select(m.TrainingPill,m.TrainingCourse).outerjoin(m.TrainingCourse,m.TrainingCourse.pill_id==m.TrainingPill.id)
        .where(~select(m.TrainingRetiredPill.pill_id).where(m.TrainingRetiredPill.pill_id==m.TrainingPill.id).exists())
        .order_by(m.TrainingPill.title)).all()
    result=[]
    for pill,course in rows:
        revision=active_revision(db,pill.id)
        data=json.loads(course.draft_json) if course and course.draft_json else json.loads(revision.content_json) if revision else document(pill.title,'',pill.learning_objectives)
        result.append(dict(id=pill.id,slug=pill.slug,title=data['title'],objective=data['objective'],
            active_version=course.active_version if course else pill.content_version,
            has_draft=bool(course and course.draft_json),edit_revision=course.edit_revision if course else 0,
            data=data,lessons=len(data['lessons'])))
    return sorted(result,key=lambda row:row['title'].casefold())


def validate_url(value,internal=False):
    value=value.strip()
    decoded=unquote(value)
    if any(ord(c)<32 for c in decoded) or '\\' in decoded:
        raise ValueError('Il collegamento non è valido.')
    parts=urlsplit(value)
    if internal:
        if not decoded.startswith('/') or decoded.startswith('//') or parts.scheme or parts.netloc:
            raise ValueError('Per una pagina RF-One usa un percorso che inizia con una sola barra /.')
    elif parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('Per un collegamento esterno inserisci un indirizzo HTTPS valido.')
    return value


def uploaded_file(db,pill_id,upload):
    data=upload.read(MAX_FILE_BYTES+1)
    if not data or len(data)>MAX_FILE_BYTES:raise ValueError('Ogni file deve avere una dimensione compresa tra 1 byte e 25 MB.')
    filename=secure_filename(upload.filename or '')[:255]
    suffix=filename.rsplit('.',1)[-1].lower()
    if suffix=='pdf' and data.startswith(b'%PDF-'):media='application/pdf'
    elif suffix=='mp4' and len(data)>=12 and data[4:8]==b'ftyp':media='video/mp4'
    elif suffix=='webm' and data.startswith(b'\x1aE\xdf\xa3'):media='video/webm'
    else:raise ValueError('Carica un PDF oppure un video MP4 o WebM valido.')
    row=m.TrainingCourseFile(pill_id=pill_id,filename=filename,media_type=media,sha256=hashlib.sha256(data).hexdigest(),data=data)
    db.add(row);db.flush()
    return row


def save(db, *, pill_id, edit_revision, title, description, objective, lessons, uploads, publish=False):
    title,description,objective=title.strip(),description.strip(),objective.strip()
    if not title or len(title)>255:raise ValueError('Inserisci il titolo del corso (massimo 255 caratteri).')
    if len(description)>10000 or len(objective)>10000:raise ValueError('Descrizione e obiettivo possono contenere al massimo 10.000 caratteri.')
    if len(lessons)>MAX_LESSONS:raise ValueError('Un corso può contenere al massimo 30 lezioni.')
    if pill_id:
        course=db.scalar(select(m.TrainingCourse).where(m.TrainingCourse.pill_id==pill_id).with_for_update())
        if not course or db.get(m.TrainingRetiredPill,pill_id):raise ValueError('Corso non disponibile per la modifica.')
        if course.edit_revision!=edit_revision:raise ValueError('Il corso è stato modificato da un’altra sessione. Conserva i tuoi appunti e riapri la scheda aggiornata.')
        pill=db.get(m.TrainingPill,pill_id)
    else:
        pill=m.TrainingPill(slug='course-'+secrets.token_hex(12),title=title,learning_objectives=objective,content_version=1)
        db.add(pill);db.flush()
        course=m.TrainingCourse(pill_id=pill.id,edit_revision=0)
        db.add(course)
    cleaned=[]
    for index,item in enumerate(lessons):
        kind=item.get('kind','text')
        if kind not in ('text','internal','link','file'):raise ValueError('Tipo di materiale non valido.')
        lesson=dict(title=item.get('title','').strip(),kind=kind,url='',text='',file_id=None,filename='')
        if len(lesson['title'])>255:raise ValueError('Il titolo di una lezione può contenere al massimo 255 caratteri.')
        if kind=='file':
            upload=uploads[index] if index<len(uploads) else None
            if upload and upload.filename:
                file=uploaded_file(db,pill.id,upload)
            elif item.get('file_id'):
                try:file_id=int(item['file_id'])
                except (TypeError,ValueError):raise ValueError('Riferimento al file non valido.')
                file=db.get(m.TrainingCourseFile,file_id)
                if not file or file.pill_id!=pill.id:raise ValueError('Il file selezionato non appartiene a questo corso.')
            else:file=None
            if file:lesson.update(file_id=file.id,filename=file.filename)
        elif kind=='text':
            lesson['text']=item.get('text','').strip()
            if len(lesson['text'])>50000:raise ValueError('Ogni lezione può contenere al massimo 50.000 caratteri di testo.')
        else:
            raw=item.get('url','').strip()
            if len(raw)>2048:raise ValueError('Il collegamento è troppo lungo.')
            if raw:lesson['url']=validate_url(raw,kind=='internal')
        if publish:
            filled=lesson['text'] if kind=='text' else lesson['file_id'] if kind=='file' else lesson['url']
            if not lesson['title'] or not filled:raise ValueError(f'Completa il titolo e il materiale della lezione {index+1} prima di rendere disponibile il corso.')
        cleaned.append(lesson)
    data=document(title,description,objective,cleaned)
    if publish:
        if not description or not objective or not cleaned:raise ValueError('Per rendere disponibile il corso servono descrizione, obiettivo e almeno una lezione completa.')
        version=(course.active_version or 0)+1
        db.add(m.TrainingCourseRevision(pill_id=pill.id,version=version,content_json=json.dumps(data,ensure_ascii=False)))
        course.active_version=version;course.draft_json=None
        pill.title=title;pill.learning_objectives=objective;pill.content_version=version
    else:
        course.draft_json=json.dumps(data,ensure_ascii=False)
        if course.active_version is None:pill.title=title;pill.learning_objectives=objective
    course.edit_revision+=1
    db.flush()
    return pill


def pin_assignment(db,assignment):
    revision=active_revision(db,assignment.pill_id)
    if revision:
        db.add(m.TrainingCourseAssignmentRevision(assignment_id=assignment.id,revision_id=revision.id))
        db.flush()


def initialize_visual_menu(db):
    pill=db.scalar(select(m.TrainingPill).where(m.TrainingPill.slug=='visual-menu'))
    if not pill:raise ValueError('Visual Menu non è presente nel catalogo locale.')
    if db.get(m.TrainingCourse,pill.id):return
    data=document(pill.title,'Il menu visuale RF-One con i piatti e i relativi contenuti.',pill.learning_objectives,
        [dict(title='Visual Menu',kind='internal',url='/training/visual-menu',text='',file_id=None,filename='')])
    db.add(m.TrainingCourse(pill_id=pill.id,active_version=1,edit_revision=0))
    revision=m.TrainingCourseRevision(pill_id=pill.id,version=1,content_json=json.dumps(data,ensure_ascii=False))
    db.add(revision);db.flush()
    for assignment in db.scalars(select(m.TrainingAssignment).where(m.TrainingAssignment.pill_id==pill.id)):
        if not db.get(m.TrainingCourseAssignmentRevision,assignment.id):
            db.add(m.TrainingCourseAssignmentRevision(assignment_id=assignment.id,revision_id=revision.id))
    db.flush()
