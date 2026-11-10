"""Administration of shared role profiles and explicit company participation."""
import json
from collections import defaultdict
from flask import request, render_template, redirect, url_for, flash, abort, session as browser_session, g
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from rfone_data_store import models as m, employee_directory as directory
from rfone_data_store import access_profiles as profiles


def register_role_profile_routes(app,*,SessionFactory,require_admin,load_current_account,require_csrf,domains):
    @app.before_request
    def profile_company_context():
        with SessionFactory() as db:
            account=load_current_account(db)
            allowed=profiles.company_ids_for_account(db,account.id) if account else set()
            chosen=browser_session.get('rfone_company_context')
            if chosen not in allowed:chosen=min(allowed) if allowed else None
            g.access_profile_company_token=profiles.company_context.set(chosen)

    @app.teardown_request
    def release_profile_company_context(error):
        token=g.pop('access_profile_company_token',None)
        if token is not None:profiles.company_context.reset(token)

    @app.context_processor
    def role_profile_context():
        summaries=defaultdict(lambda:{'companies':set(),'roles':set()})
        with SessionFactory() as db:
            account=load_current_account(db)
            available=profiles.company_ids_for_account(db,account.id) if account else set()
            companies=list(db.scalars(select(profiles.CompanyContext).where(profiles.CompanyContext.id.in_(available)).order_by(profiles.CompanyContext.name)))
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
        return {'profile_companies':companies,'profile_company_id':profiles.company_context.get(),
                'can_manage_profiles':bool(account and (account.is_admin or account.is_owner)),
                'person_profile_summary':lambda kind,identity:summaries[(kind,identity)]}

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

    def target_choices(db):
        choices={f'employee:{p.id}':p.display_name or 'Name to complete' for p in directory.employee_options(db)}
        for account in db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.status=='ACTIVE').order_by(m.RFOneAccount.display_name)):
            if directory.context_person_id(db,'RFONE_ACCOUNT',account.id) is None:
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
                    if action in ('person_access','person_password'):
                        linked=profiles.ensure_profile_account(db,person,account.id)
                        db.commit()
                        return redirect(url_for('admin_account_edit',account_id=linked.id,_anchor='reset-password')) if action=='person_password' else redirect(url_for('admin_account_access',account_id=linked.id,from_person=person))
                    elif action=='person_create':
                        record=profiles.create_profile_person(db,name=request.form.get('name'),company_ids=request.form.getlist('company_ids'),assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id,**{key:request.form[key] for key in ('email','phone') if key in request.form})
                        person=f'employee:{record.id}';anchor='people-table'
                    elif action=='person_dismiss':
                        profiles.dismiss_profile_person(db,person,dismissal_date=request.form.get('dismissal_date'),actor=account.id)
                        anchor='dismissed-people'
                    elif action=='person_save':
                        profiles.save_person_profile(db,person,name=request.form.get('name'),company_ids=request.form.getlist('company_ids'),assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id,**{key:request.form[key] for key in ('email','phone') if key in request.form})
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
        choices=target_choices(db)
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
            condition=profiles.membership_target_condition(db,employee_id=identity if kind=='employee' else None,account_id=identity if kind=='account' else None)
            memberships=list(db.scalars(select(profiles.CompanyMembership).where(condition).order_by(profiles.CompanyMembership.id)))
            members=[v for v in memberships if v.valid_to is None];history=[v for v in memberships if v.valid_to is not None]
            assignments=list(db.scalars(select(profiles.RoleProfileAssignment).where(profiles.RoleProfileAssignment.membership_id.in_([v.id for v in memberships])).order_by(profiles.RoleProfileAssignment.id)))
            linked=identity if kind=='account' else None
            if kind=='employee':
                linked=db.scalar(select(m.EmployeeContextLink.rfone_account_id).where(m.EmployeeContextLink.employee_id==identity,m.EmployeeContextLink.rfone_account_id.is_not(None)))
                if linked is None:
                    linked=next((aid for aid in db.scalars(select(m.RFOneAccount.id)) if directory.context_person_id(db,'RFONE_ACCOUNT',aid)==identity),None)
            if linked:
                for member in members:effective[member.company_id]=profiles.effective_permissions(db,linked,company_id=member.company_id)
        people_rows=[]
        for key,label in choices.items():
            kind,identity=key.split(':');identity=int(identity)
            target=db.get(m.Employee if kind=='employee' else m.RFOneAccount,identity)
            condition=profiles.membership_target_condition(db,identity if kind=='employee' else None,identity if kind=='account' else None)
            current=list(db.scalars(select(profiles.CompanyMembership).where(condition,profiles.CompanyMembership.valid_to.is_(None))))
            current_roles=list(db.scalars(select(profiles.RoleProfileAssignment).where(profiles.RoleProfileAssignment.membership_id.in_([v.id for v in current]),profiles.RoleProfileAssignment.valid_to.is_(None))))
            company_map={v.id:v.company_id for v in current}
            account_ids=([identity] if kind=='account' else [aid for aid in db.scalars(select(m.RFOneAccount.id)) if directory.context_person_id(db,'RFONE_ACCOUNT',aid)==identity])
            access_url=url_for('admin_account_access',account_id=account_ids[0],from_person=key) if len(account_ids)==1 else None
            people_rows.append({'key':key,'email':target.email if kind=='employee' else target.contact_email,'phone':target.phone if kind=='employee' else target.contact_phone,'access_url':access_url,'name':target.display_name or 'Name to complete','companies':sorted({v.company_id for v in current}),
                'assignments':[{'company_id':company_map[a.membership_id],'role_id':a.role_id,'area_id':a.area_id} for a in current_roles]})
        dismissed_rows=[]
        dismissal_dates={}
        for ev in db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action=='PERSON_DISMISSED').order_by(profiles.ProfileEvent.id)):
            dismissal_dates[ev.details.get('employee_id')]=ev.details.get('dismissal_date')
        for option in directory.employee_options(db,include_inactive=True):
            target=db.get(m.Employee,option.id)
            if not directory.employee_is_active(target,[]):
                dismissed_rows.append({'name':target.display_name or 'Name to complete','date':dismissal_dates.get(target.id) or getattr(target,'dismissed_at',None)})
        events=list(db.scalars(select(profiles.ProfileEvent).order_by(profiles.ProfileEvent.id.desc()).limit(25)))
        return render_template('role_profiles.html',people_rows=people_rows,dismissed_rows=dismissed_rows,tab=tab,person=person,roles=roles,areas=areas,companies=companies,
            pairs=dict(pairs),grants=dict(grants),domains=domains,choices=choices,members=members,assignments=assignments,
            history=history,effective=effective,events=events,dialog=dialog,error=error,can_assign_target=can_assign_target,
            area_by_id={a.id:a for a in areas},role_by_id={r.id:r for r in roles},company_by_id={c.id:c for c in companies},
            domain_names={d.code:d.display_name for d in domains},
            role_payload=[{'id':r.id,'name':r.name,'active':r.active is not False,'areas':pairs[r.id],
                'permissions':{code:{'mode':'all' if p.scope=='ALL' else 'selected','role':p.role_code or '', 'items':p.items} for code,p in grants[r.id].items()}} for r in roles],
            area_payload=[{'id':a.id,'name':a.name,'active':a.active is not False} for a in areas])
