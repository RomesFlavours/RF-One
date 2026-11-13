"""Administration of shared role profiles and explicit company participation."""
import json
import os
from registry_text import ui as registry_ui
from collections import defaultdict
from flask import request, render_template, redirect, url_for, flash, abort, session as browser_session, g
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from rfone_data_store import models as m, employee_directory as directory
from rfone_data_store import access_profiles as profiles


def register_role_profile_routes(app,*,SessionFactory,require_admin,load_current_account,require_csrf,domains):
    from rfone_data_store.web_access import install_access_context
    install_access_context(app, SessionFactory, load_current_account)
    from person_reconciliation_routes import register_person_reconciliation
    register_person_reconciliation(app, SessionFactory=SessionFactory, require_admin=require_admin,
        load_current_account=load_current_account, require_csrf=require_csrf)

    @app.context_processor
    def role_profile_context():
        summaries=defaultdict(lambda:{'companies':set(),'roles':set()})
        with SessionFactory() as db:
            account=load_current_account(db)
            available=profiles.company_ids_for_account(db,account.id) if account else set()
            companies=list(db.scalars(select(profiles.CompanyContext).where(profiles.CompanyContext.id.in_(available)).order_by(profiles.CompanyContext.name)))
        summaries_loaded = False
        def person_summary(kind, identity):
            nonlocal summaries_loaded
            if not summaries_loaded:
                with SessionFactory() as db:
                    for member,company in db.execute(select(profiles.CompanyMembership,profiles.CompanyContext.name).join(
                        profiles.CompanyContext,profiles.CompanyContext.id==profiles.CompanyMembership.company_id).where(profiles.CompanyMembership.valid_to.is_(None))):
                        target=('employee' if member.employee_id is not None else 'account',member.employee_id or member.account_id)
                        summaries[target]['companies'].add(company)
                    for member,role,area,company in db.execute(select(profiles.CompanyMembership,m.RestaurantRole.name,m.OperationalArea.name,profiles.CompanyContext.name).join(
                        profiles.RoleProfileAssignment,profiles.RoleProfileAssignment.membership_id==profiles.CompanyMembership.id).join(m.RestaurantRole,
                        m.RestaurantRole.id==profiles.RoleProfileAssignment.role_id).join(m.OperationalArea,
                        m.OperationalArea.id==profiles.RoleProfileAssignment.area_id).join(profiles.CompanyContext,profiles.CompanyContext.id==profiles.CompanyMembership.company_id).where(
                        profiles.CompanyMembership.valid_to.is_(None),profiles.RoleProfileAssignment.valid_to.is_(None))):
                        target=('employee' if member.employee_id is not None else 'account',member.employee_id or member.account_id)
                        summaries[target]['roles'].add(f'{role} · {area} · {company}')
                summaries_loaded = True
            return summaries[(kind, identity)]
        return {'registry_it':os.environ.get('RFONE_UI_LANGUAGE') == 'it',
                'registry_ui':registry_ui,
                'profile_companies':companies,'profile_company_id':profiles.company_context.get(),
                'can_manage_profiles':bool(account and (account.is_admin or account.is_owner)),
                'person_profile_summary':person_summary}

    @app.route('/admin/access-company',methods=['POST'])
    def switch_access_company():
        require_csrf()
        with SessionFactory() as db:
            account=load_current_account(db)
            try:identity=int(request.form.get('company_id',''))
            except ValueError:abort(400)
            if not account or identity not in profiles.company_ids_for_account(db,account.id):abort(403)
        browser_session['rfone_company_context']=identity
        return redirect(url_for('home'))

    def target_choices(db, account_people, accounts):
        choices={f'employee:{p.id}':p.display_name or 'Name to complete' for p in directory.employee_options(db)}
        for account in sorted((a for a in accounts if a.status in ('ACTIVE','INACTIVE')), key=lambda a:a.display_name):
            if account_people[account.id] is None:
                choices[f'account:{account.id}']=f'{account.display_name} · external account'
        return choices

    @app.route('/admin/roles',methods=['GET','POST'])
    @require_admin
    def role_profiles_home():
        with SessionFactory() as db:
            account=load_current_account(db)
            if not account.is_owner:
                employee_id=directory.context_person_id(db,'RFONE_ACCOUNT',account.id)
                if employee_id is not None and not directory.employee_is_active(db.get(m.Employee,employee_id),[]):abort(403)
            tab=request.values.get('tab','people')
            if tab not in ('roles','areas','companies','people'):tab='people'
            person=request.values.get('person','')
            if person:
                try:
                    target_kind,target_id=person.split(':');target_id=int(target_id)
                    if target_kind=='account':
                        canonical=directory.context_person_id(db,'RFONE_ACCOUNT',target_id)
                        if canonical is not None:person=f'employee:{canonical}'
                    elif target_kind=='employee':person=f'employee:{directory.resolve_employee_id(db,target_id)}'
                    else:abort(400)
                except ValueError:abort(400)
            if request.method=='POST':
                require_csrf()
                try:
                    action=request.form.get('action','')
                    identity=int(request.form.get('id','0') or 0)
                    anchor=request.form.get('return_to','catalog')
                    if action == 'clover_confirm':
                        directory.attach_link(db, link_id=int(request.form.get('link_id', '')),
                            employee_id=int(request.form['employee_id']) if request.form.get('employee_id') else None,
                            create_new=request.form.get('create_new') == 'yes', account_id=account.id)
                        anchor='clover-identities'
                        flash('Identità confermata e dati di lavoro attribuiti. Ricalcola le mance prima di finalizzarle.' if os.environ.get('RFONE_UI_LANGUAGE') == 'it' else 'Identity confirmed and held work attributed. Recalculate tips before finalizing.', 'info')
                    elif action in ('person_access','person_password'):
                        linked=profiles.ensure_profile_account(db,person,account.id)
                        db.commit()
                        return redirect(url_for('admin_account_edit',account_id=linked.id,from_person=person,_anchor='reset-password')) if action=='person_password' else redirect(url_for('admin_account_access',account_id=linked.id,from_person=person))
                    elif action=='person_create':
                        record=profiles.create_profile_person(db,name=request.form.get('name'),company_ids=request.form.getlist('company_ids'),assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id,**({'company_statuses':request.form.getlist('company_status')} if request.form.get('person_status_fields')=='1' or 'company_status' in request.form else {}),**{key:request.form[key] for key in ('email','phone','account_status') if key in request.form})
                        person=f'employee:{record.id}';anchor='people-table'
                    elif action=='person_dismiss':
                        profiles.dismiss_profile_person(db,person,dismissal_date=request.form.get('dismissal_date'),actor=account.id)
                        anchor='dismissed-people'
                    elif action=='person_save':
                        profiles.save_person_profile(db,person,name=request.form.get('name'),company_ids=request.form.getlist('company_ids'),assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id,**({'company_statuses':request.form.getlist('company_status')} if request.form.get('person_status_fields')=='1' or 'company_status' in request.form else {}),**{key:request.form[key] for key in ('email','phone','account_status') if key in request.form})
                        anchor='people-table'
                    elif action=='area_save':
                        record=profiles.save_area(db,name=request.form.get('area_name',request.form.get('name')),area_id=identity or None,actor=account.id);anchor=f'area-{record.id}'
                    elif action=='role_save':
                        record=profiles.save_role(db,name=request.form.get('name'),area_ids=request.form.getlist('area_ids'),role_id=identity or None,actor=account.id);anchor=f'role-{record.id}'
                    elif action in ('archive','restore'):profiles.set_archived(db,request.form.get('kind'),identity,action=='archive',account.id)
                    elif action=='permissions':
                        values={d.code:{'mode':request.form.get('access_'+d.code,'none'),'role':request.form.get('role_'+d.code,''),'items':request.form.getlist('items_'+d.code)} for d in domains}
                        profiles.save_permissions(db,identity,values,domains,account.id)
                    elif action=='membership':
                        record=profiles.membership(db,person,int(request.form.get('company_id','')),account.id);anchor=f'membership-{record.id}'
                    elif action=='assignment':profiles.assign_role(db,membership_id=int(request.form.get('membership_id','')),role_id=int(request.form.get('role_id','')),area_id=int(request.form.get('area_id','')),actor=account.id)
                    elif action in ('withdraw_membership','withdraw_assignment'):profiles.withdraw(db,action.removeprefix('withdraw_'),identity,account.id)
                    else:raise ValueError('Unknown action.')
                    db.commit()
                except (ValueError,IntegrityError,TypeError,KeyError) as exc:
                    db.rollback()
                    error=str(exc) if isinstance(exc,ValueError) else 'A matching active record already exists. Nothing saved.'
                    # Reopen the same modal with its input and error.
                    return render_page(db,tab,person,dialog=request.form.to_dict(flat=False),error=error),422
                return redirect(url_for('role_profiles_home',tab=tab,person=person,_anchor=anchor))
            return render_page(db,tab,person)

    def render_page(db,tab,person,dialog=None,error=None):
        actor_id=load_current_account(db).id
        if error:error=registry_ui(error)
        roles=list(db.scalars(select(m.RestaurantRole).order_by(m.RestaurantRole.name,m.RestaurantRole.id)))
        areas=list(db.scalars(select(m.OperationalArea).order_by(m.OperationalArea.name,m.OperationalArea.id)))
        companies=list(db.scalars(select(profiles.CompanyContext).order_by(profiles.CompanyContext.name)))
        pairs=defaultdict(list)
        for pair in db.scalars(select(m.OperationalAreaRole)):pairs[pair.restaurant_role_id].append(pair.operational_area_id)
        area_names={area.id:area.name.casefold() for area in areas}
        for ids in pairs.values():ids.sort(key=lambda identity:(area_names.get(identity,''),identity))
        roles.sort(key=lambda role:(not bool(pairs[role.id]),tuple(area_names.get(identity,'') for identity in pairs[role.id]),role.name.casefold(),role.id))
        grants=defaultdict(dict)
        for grant in db.scalars(select(profiles.RolePermission)):grants[grant.role_id][grant.domain_code]=grant
        # Presentation-only snapshot, scoped to this render. Authorization and
        # all POST operations continue to use the authoritative shared services.
        load_people = tab == 'people'
        accounts = list(db.scalars(select(m.RFOneAccount))) if load_people or person else []
        account_by_id = {a.id:a for a in accounts}
        account_people = {a.id:directory.context_person_id(db,'RFONE_ACCOUNT',a.id) for a in accounts}
        accounts_by_person = defaultdict(list)
        for aid, employee_id in account_people.items():
            if employee_id is not None:accounts_by_person[employee_id].append(aid)
        choices=target_choices(db, account_people, accounts) if load_people else {}
        def membership_condition(kind, identity):
            if kind == 'account':return profiles.CompanyMembership.account_id == identity
            return or_(profiles.CompanyMembership.employee_id == identity,
                       profiles.CompanyMembership.account_id.in_(accounts_by_person[identity]))
        members=[];assignments=[];history=[];effective={};can_assign_target=False
        if person:
            # Reading dismissed historical profiles is allowed. New writes use person_target.
            try:
                kind,identity=person.split(':');identity=int(identity)
            except (ValueError,AttributeError):abort(400)
            model=m.Employee if kind=='employee' else m.RFOneAccount if kind=='account' else None
            target=db.get(model,identity) if model else None
            if target is None:abort(404)
            can_assign_target=directory.employee_is_active(target,[]) if kind=='employee' else target.status=='ACTIVE'
            choices.setdefault(person,(target.display_name or 'Name to complete')+' · history')
            condition=membership_condition(kind, identity)
            memberships=list(db.scalars(select(profiles.CompanyMembership).where(condition).order_by(profiles.CompanyMembership.id)))
            members=[v for v in memberships if v.valid_to is None];history=[v for v in memberships if v.valid_to is not None]
            assignments=list(db.scalars(select(profiles.RoleProfileAssignment).where(profiles.RoleProfileAssignment.membership_id.in_([v.id for v in memberships])).order_by(profiles.RoleProfileAssignment.id)))
            linked=identity if kind=='account' else None
            if kind=='employee':
                linked=db.scalar(select(m.EmployeeContextLink.rfone_account_id).where(m.EmployeeContextLink.employee_id==identity,m.EmployeeContextLink.rfone_account_id.is_not(None)))
                if linked is None:
                    linked=next(iter(accounts_by_person[identity]),None)
            if linked:
                for member in members:effective[member.company_id]=profiles.effective_permissions(db,linked,company_id=member.company_id)
        from rfone_data_store import person_reconciliation as identities
        identity_graph = identities.IdentityGraph(db) if load_people and identities.ready(db) else None
        people_rows=[]
        current_by_employee=defaultdict(list);current_by_account=defaultdict(list)
        roles_by_membership=defaultdict(list)
        if load_people:
            for member in db.scalars(select(profiles.CompanyMembership).where(profiles.CompanyMembership.valid_to.is_(None))):
                if member.employee_id is not None:current_by_employee[member.employee_id].append(member)
                if member.account_id is not None:current_by_account[member.account_id].append(member)
            for assignment in db.scalars(select(profiles.RoleProfileAssignment).where(profiles.RoleProfileAssignment.valid_to.is_(None))):
                roles_by_membership[assignment.membership_id].append(assignment)
            # Keep Employee objects alive in the identity map throughout rendering.
            people_by_id={p.id:p for p in db.scalars(select(m.Employee))}
        status_codes=defaultdict(list)
        if load_people:
            for status in db.scalars(select(profiles.PersonCompanyStatus)):
                status_codes[('employee' if status.employee_id is not None else 'account',status.employee_id or status.account_id)].append(status.code)
        for key,label in choices.items() if load_people else []:
            kind,identity=key.split(':');identity=int(identity)
            target=people_by_id.get(identity) if kind=='employee' else account_by_id.get(identity)
            related=accounts_by_person[identity] if kind=='employee' else [identity]
            current=list(current_by_employee[identity]) if kind=='employee' else []
            for aid in related:current.extend(current_by_account[aid])
            current=list({v.id:v for v in current}.values())
            current_roles=sorted((a for v in current for a in roles_by_membership[v.id]),key=lambda a:a.id)
            company_map={v.id:v.company_id for v in current}
            account_ids=related
            access_url=url_for('admin_account_access',account_id=account_ids[0],from_person=key) if len(account_ids)==1 else None
            linked_account=account_by_id[account_ids[0]] if len(account_ids)==1 else None
            account_label=f'{linked_account.username} · {linked_account.status}' if linked_account else 'No unique RF1 account linked'
            central_person_id=None;identity_conflict=False
            if identity_graph:
                try:central_person_id=identity_graph.person_id('employee' if kind=='employee' else 'account',identity)
                except ValueError:identity_conflict=True
            people_rows.append({'company_statuses':status_codes[(kind,identity)],'account_status':linked_account.status if linked_account else 'NONE','account_status_locked':bool(linked_account and (linked_account.is_owner or linked_account.id==actor_id)),'central_person_id':central_person_id,'identity_conflict':identity_conflict,'key':key,'account_label':account_label,'email':target.email if kind=='employee' else target.contact_email,'phone':target.phone if kind=='employee' else target.contact_phone,'access_url':access_url,'name':target.display_name or 'Name to complete','companies':sorted({v.company_id for v in current}),
                'assignments':[{'company_id':company_map[a.membership_id],'role_id':a.role_id,'area_id':a.area_id} for a in current_roles]})
        dismissed_rows=[]
        dismissal_dates={}
        clover_people = directory.employee_options(db, include_inactive=True) if load_people else []
        if load_people:
            for ev in db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action=='PERSON_DISMISSED').order_by(profiles.ProfileEvent.id)):
                dismissal_dates[ev.details.get('employee_id')]=ev.details.get('dismissal_date')
            for option in clover_people:
                target=db.get(m.Employee,option.id)
                if not directory.employee_is_active(target,[]):
                    dismissed_rows.append({'name':target.display_name or 'Name to complete','date':dismissal_dates.get(target.id) or getattr(target,'dismissed_at',None)})
        events=list(db.scalars(select(profiles.ProfileEvent).order_by(profiles.ProfileEvent.id.desc()).limit(25)))
        from registry_clover import pending_identities
        clover_pending = pending_identities(db) if tab == 'people' else []
        return render_template('role_profiles.html',clover_pending=clover_pending,
            clover_people=clover_people,
            registry_it=os.environ.get('RFONE_UI_LANGUAGE') == 'it',people_rows=people_rows,dismissed_rows=dismissed_rows,tab=tab,person=person,roles=roles,areas=areas,companies=companies,
            pairs=dict(pairs),grants=dict(grants),domains=domains,choices=choices,members=members,assignments=assignments,
            history=history,effective=effective,events=events,dialog=dialog,error=error,can_assign_target=can_assign_target,
            area_by_id={a.id:a for a in areas},role_by_id={r.id:r for r in roles},company_by_id={c.id:c for c in companies},
            domain_names={d.code:d.display_name for d in domains},
            role_payload=[{'id':r.id,'name':r.name,'active':r.active is not False,'areas':pairs[r.id],
                'permissions':{code:{'mode':'all' if p.scope=='ALL' else 'selected','role':p.role_code or '', 'items':p.items} for code,p in grants[r.id].items()}} for r in roles],
            area_payload=[{'id':a.id,'name':a.name,'active':a.active is not False} for a in areas])
