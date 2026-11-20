"""Visual Menu roles come from Training or MyRF, never Kitchen grants."""
from flask import abort
from sqlalchemy import select
from rfone_data_store import models as m


def role_for(db, account, entry):
    if account is None or account.status != 'ACTIVE':
        abort(403)
    from local_operator_session import local_admin_preview
    if local_admin_preview(account):
        return 'server' if entry == 'myrf' else 'trainer'
    if entry == 'myrf':
        grant = db.scalar(select(m.RFOneAccountDomainAccess.enabled).where(
            m.RFOneAccountDomainAccess.account_id == account.id,
            m.RFOneAccountDomainAccess.domain_code == 'MYRF',
            m.RFOneAccountDomainAccess.enabled.is_(True)))
        if grant:
            return 'server'
        abort(403)
    import training_integration
    result = training_integration.check_training_authorization(db, account)
    training = result.training_account
    if training is None:
        abort(403)
    if training.role == 'trainer':
        return 'trainer'
    if training.role == 'student':
        assigned = db.scalar(select(m.TrainingAssignment.id)
            .join(m.TrainingNeed,m.TrainingNeed.id==m.TrainingAssignment.need_id)
            .join(m.TrainingPill,m.TrainingPill.id==m.TrainingAssignment.pill_id)
            .where(m.TrainingNeed.student_account_id==training.id,m.TrainingPill.slug=='visual-menu').limit(1))
        if assigned:
            return 'student'
    abort(403)
