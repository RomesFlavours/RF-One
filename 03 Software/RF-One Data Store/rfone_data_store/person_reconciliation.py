"""Read-only identity graph and explicit, atomic reconciliation. No grant writes."""
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
import json
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, inspect, select
from . import models as m, people_registry as people, student_registry as students


class PersonReconciliationEvent(m.Base):
    __tablename__ = 'person_reconciliation_events'
    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('candidate_persons.id'), nullable=False)
    actor_id = Column(Integer, ForeignKey('rfone_accounts.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    action = Column(String(32), nullable=False)
    details = Column(JSON, nullable=False)


TABLES = (people.PersonAccountLink, people.PersonEmployeeLink, students.TrainingPersonLink,
          students.PersonQualification, PersonReconciliationEvent)


def ready(db):
    names=set(inspect(db.connection()).get_table_names())
    return all(t.__tablename__ in names for t in TABLES)


def _normal(value):
    return ' '.join((value or '').casefold().split())


class IdentityGraph:
    """Bounded-query snapshot of explicit links; names never create graph edges."""
    def __init__(self, db):
        tables=set(inspect(db.connection()).get_table_names())
        self.records={};self.edges=defaultdict(set);self.rows={};self.provenance=[];self.broken=[]
        def load(kind, model):
            rows=list(db.scalars(select(model).order_by(model.id)))
            self.rows[kind]={r.id:r for r in rows}
            for row in rows:
                label=(getattr(row,'full_name',None) or getattr(row,'display_name',None)
                       or getattr(row,'username',None) or f'{kind} {row.id}')
                email=getattr(row,'primary_email',None) or getattr(row,'email',None) or ''
                self.records[(kind,row.id)]={'kind':kind,'id':row.id,'name':label,'email':email,
                    'status':getattr(row,'status',None),'active':getattr(row,'active',None)}
        for kind,model in [('person',m.CandidatePerson),('employee',m.Employee),('account',m.RFOneAccount),('training',m.TrainingAccount),('acting',m.ActingIdentity)]:load(kind,model)
        def edge(left,right,origin):
            if left not in self.records or right not in self.records:
                self.broken.append({'left':left,'right':right,'origin':origin});return
            self.edges[left].add(right);self.edges[right].add(left)
            self.provenance.append((left,right,origin))
        links=[(people.PersonAccountLink,'account','account_id'),(people.PersonEmployeeLink,'employee','employee_id'),(students.TrainingPersonLink,'training','training_account_id')]
        for model,kind,key in links:
            if model.__tablename__ in tables:
                for row in db.scalars(select(model)):edge(('person',row.person_id),(kind,getattr(row,key)),model.__tablename__)
        for row in db.scalars(select(m.RFOneTrainingIdentityLink)):
            edge(('account',row.rfone_account_id),('training',row.training_account_id),'rfone_training_identity_links')
        for row in self.rows['training'].values():
            edge(('training',row.id),('acting',row.acting_identity_id),'training_accounts')
            actor=self.rows['acting'].get(row.acting_identity_id)
            if actor:self.records[('training',row.id)]['name']=actor.display_name
        for row in db.scalars(select(m.EmployeeContextLink)):
            for kind,key in [('account','rfone_account_id'),('training','training_account_id'),('acting','acting_identity_id')]:
                value=getattr(row,key,None)
                if value is not None:edge(('employee',row.employee_id),(kind,value),'employee_context_links')
        from .training.workspace import TrainingStudentProfile
        if TrainingStudentProfile.__tablename__ in tables:
            for row in db.scalars(select(TrainingStudentProfile).where(TrainingStudentProfile.employee_id.is_not(None))):
                edge(('training',row.training_account_id),('employee',row.employee_id),'training_student_profiles')
        for row in db.scalars(select(m.EmployeeIdentityAlias)):
            edge(('employee',row.employee_id),('employee',row.canonical_employee_id),'employee_identity_aliases')
        self.groups={};self.by_node={};visited=set()
        for node in sorted(self.records):
            if node in visited:continue
            stack=[node];component=set()
            while stack:
                value=stack.pop()
                if value in component:continue
                component.add(value);stack.extend(self.edges[value]-component)
            visited.update(component)
            # Unrelated actors (AI, system operators) are not person candidates.
            if not any(k in ('person','employee','account','training') for k,_ in component):continue
            key='|'.join(f'{k}:{i}' for k,i in sorted(component));fingerprint=sha256(json.dumps(
                {'records':[self.records[n] for n in sorted(component)],
                 'links':sorted((a,b,o) for a,b,o in self.provenance if a in component)},sort_keys=True,default=str).encode()).hexdigest()
            group={'key':key,'fingerprint':fingerprint,'nodes':component,
                   'records':[self.records[n] for n in sorted(component)],'conflicts':[]}
            if any(b['left'] in component or b['right'] in component for b in self.broken):
                group['conflicts'].append('An explicit link refers to a missing record; review required.')
            for kind in ('person','account','training'):
                count=sum(k==kind for k,_ in component)
                if count>1:group['conflicts'].append(f'Multiple {kind} identities ({count}); explicit conflict review required.')
            if any(self.rows['acting'][i].kind!='HUMAN_USER' for k,i in component if k=='acting'):
                group['conflicts'].append('Non-human acting identity; cannot reconcile as a person.')
            group['person_ids']=[i for k,i in sorted(component) if k=='person']
            group['name']=next((self.records[n]['name'] for kind in ('person','employee','account','training') for n in sorted(component) if n[0]==kind),'Person')
            group['state']=('conflict' if group['conflicts'] else 'person-only' if all(k=='person' for k,_ in component)
                            else 'confirmed' if group['person_ids'] else 'unlinked')
            self.groups[key]=group
            for n in component:self.by_node[n]=group

    def person_id(self, kind, identity):
        group=self.by_node.get((kind,identity))
        if not group:return None
        if group['conflicts']:raise ValueError('Conflicting confirmed identity links. Review reconciliation first.')
        return next(iter(group['person_ids']),None)

    def suggestions(self, group):
        names={_normal(r['name']) for r in group['records'] if r['kind']!='acting'}
        emails={_normal(r['email']) for r in group['records'] if r['email']}
        result=[]
        for person in self.rows['person'].values():
            if ('person',person.id) in group['nodes']:continue
            name=_normal(person.full_name);email=_normal(person.primary_email)
            score=max((max(SequenceMatcher(None,name,n).ratio(),SequenceMatcher(None,' '.join(sorted(name.split())),' '.join(sorted(n.split()))).ratio()) for n in names if n),default=0)
            if (email and email in emails) or score>=.8:
                result.append({'id':person.id,'name':person.full_name,'reason':'Email' if email and email in emails else 'Name similarity','score':score})
        return sorted(result,key=lambda r:(r['reason']!='Email',-r['score'],r['id']))


def audit(db):
    graph=IdentityGraph(db);rows=[]
    for group in graph.groups.values():
        row={key:value for key,value in group.items() if key!='nodes'}
        row['suggestions']=graph.suggestions(group) if group['state']=='unlinked' else []
        rows.append(row)
    return {'ready':ready(db),'broken_links':graph.broken,'counts':{state:sum(r['state']==state for r in rows) for state in ('confirmed','unlinked','conflict','person-only')},
            'groups':sorted(rows,key=lambda r:(r['state']!='conflict',r['name'].casefold(),r['key']))}


def validate_link(db, person_id, kind, source_id):
    """Guard every shared link writer against conflicting confirmed bridges."""
    graph=IdentityGraph(db)
    source=graph.by_node.get((kind,source_id));destination=graph.by_node.get(('person',person_id))
    if not source or not destination:raise ValueError('Person or source record not found.')
    if source['conflicts'] or destination['conflicts']:raise ValueError('Conflicting identity links require reconciliation.')
    combined=source['nodes'] | destination['nodes']
    for identity_kind in ('person','account','training'):
        if sum(k==identity_kind for k,_ in combined)>1:
            raise ValueError(f'This link conflicts with another confirmed {identity_kind} identity.')


def person_for_source(db, kind, source_id):
    """Shared read API. An unresolved identity stays unresolved, never guessed."""
    graph=IdentityGraph(db);identity=graph.person_id(kind,source_id)
    return graph.rows['person'].get(identity) if identity is not None else None


def reconcile(db, actor, *, key, fingerprint, person_id=None, new_name=None):
    """One explicit approval; savepoint prevents partial links on any failure."""
    people.require_admin(actor)
    if not ready(db):raise ValueError('Local identity schema is not installed.')
    # Serialize the identity-linking operation, not credential or grant operations.
    # Every competing source row is locked in deterministic order below.
    graph=IdentityGraph(db);group=graph.groups.get(key)
    if not group or group['fingerprint']!=fingerprint:raise ValueError('Identity data changed. Reload and review the links again.')
    if group['conflicts']:raise ValueError('Conflicting identities must be reviewed; no links were changed.')
    if bool(person_id)==bool(new_name):raise ValueError('Select an existing person or explicitly create one.')
    nodes=set(group['nodes'])
    if person_id:
        destination=graph.by_node.get(('person',int(person_id)))
        if not destination:raise ValueError('Person not found.')
        if destination['conflicts']:raise ValueError('The selected person has conflicting links.')
        nodes.update(destination['nodes'])
    for kind in ('person','account','training'):
        if sum(k==kind for k,_ in nodes)>1:raise ValueError(f'The chosen person has another {kind} identity. Nothing was linked.')
    if new_name and group['person_ids']:raise ValueError('This component already has a confirmed person.')
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy import text
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':720261112})
        # Rebuild after waiting: a concurrent reviewer must never reuse stale data.
        fresh=IdentityGraph(db);current=fresh.groups.get(key)
        if not current or current['fingerprint']!=fingerprint:raise ValueError('Identity data changed. Reload and review again.')
        if person_id and fresh.by_node[('person',int(person_id))]['fingerprint']!=destination['fingerprint']:
            raise ValueError('The selected person changed. Reload and review again.')
    for kind in ('person','account','training','employee'):
        model={'person':m.CandidatePerson,'account':m.RFOneAccount,'training':m.TrainingAccount,'employee':m.Employee}[kind]
        ids=sorted(i for k,i in nodes if k==kind)
        if ids:list(db.scalars(select(model).where(model.id.in_(ids)).order_by(model.id).with_for_update()))
    locked=IdentityGraph(db);current=locked.groups.get(key)
    if not current or current['fingerprint']!=fingerprint:raise ValueError('Identity data changed while locking. Reload and review.')
    if person_id and locked.by_node[('person',int(person_id))]['fingerprint']!=destination['fingerprint']:
        raise ValueError('The selected person changed while locking. Reload and review.')
    with db.begin_nested():
        person=(db.get(m.CandidatePerson,int(person_id)) if person_id else people.create_person(db,actor,new_name))
        for kind,identity in sorted(nodes):
            if kind in ('account','employee'):people.link_source(db,actor,person.id,kind,identity)
            elif kind=='training':
                link=db.get(students.TrainingPersonLink,identity)
                if link and link.person_id!=person.id:raise ValueError('Training identity is already linked to another person.')
                if not link:db.add(students.TrainingPersonLink(training_account_id=identity,person_id=person.id))
        db.add(PersonReconciliationEvent(person_id=person.id,actor_id=actor.id,created_at=datetime.now(timezone.utc),
            action='LINKS_CONFIRMED',details={'sources':[[k,i] for k,i in sorted(nodes)],'reviewed_fingerprint':fingerprint,'created_person':bool(new_name)}))
        db.flush()
    return person
