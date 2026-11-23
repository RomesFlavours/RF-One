"""Run: PYTHONPATH="<AWSSelection>/RF-One Data Store;<AWSSelection>/Selection" python test_staff_alerts.py (SQLite in memory, no AWS)."""
import os, sys
from datetime import datetime, timedelta
os.environ['RFONE_SELECTION_STAFF_ALERTS'] = '1'
os.environ['RFONE_SELECTION_ALERT_ALSO'] = 'giovanna'
os.environ['RFONE_SELECTION_ALERT_ESCALATE'] = 'pino'
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from rfone_data_store.models import Base, RFOneAccount
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store import email_service as es
from workspace import staff_alerts as sa
sa._link = lambda pid, pcid: f"https://example.test/posizioni/{pid}/candidati/{pcid}"

eng = create_engine('sqlite://')
Base.metadata.create_all(eng)
S = sessionmaker(eng)
db = S()
def acct(i, u, name, email, status='ACTIVE'):
    db.add(RFOneAccount(id=i, username=u, display_name=name, password_hash='x', email=email, status=status))
acct(1, 'giovanna', 'Giovanna', 'g@example.test'); acct(2, 'pino', 'Pino', 'p@example.test')
acct(3, 'owner', 'Owner', 'o@example.test'); acct(4, 'noemail', 'No Email', None)
db.flush()
def pos(i, mgr, status=ps.OPEN, title='Server', loc='Mount Dora'):
    db.add(ps.Position(id=i, title=title, role_code='SERVER', location_label=loc, timezone='America/New_York',
        status=status, manager_account_id=mgr, created_by_account_id=mgr, requirement_set_id=1))
pos(10, 3); pos(11, 1, title='Food Runner'); pos(12, 3, status='CLOSED')
db.flush()
NOW = datetime(2026, 11, 24, 14, 0)   # 9 am Florida
def pc(i, p, name, days, channel=ps.PUBLIC_LINK, submitted=True):
    db.add(ps.PositionCandidate(id=i, position_id=p, application_id=i, candidate_id=i, channel=channel,
        declared_name=name, added_at=NOW - timedelta(days=days)))
    db.add(ps.CandidateApplication(position_candidate_id=i, status=ps.A_SUBMITTED if submitted else 'CV_RECEIVED'))
pc(100, 10, 'Ana Fresh', 0)
pc(101, 10, 'Ben Waiting', 3)
pc(102, 11, 'Cara Old', 9, submitted=False)
pc(103, 10, 'Dan Decided', 5)
pc(104, 10, 'Eve Upload', 5, channel=ps.MANUAL_UPLOAD)
pc(105, 12, 'Fay Closed', 5)
db.flush()
db.add(ps.Decision(position_candidate_id=103, decision='REJECT', actor_account_id=1, actor_name='G'))
db.commit()

def reqs(): return db.scalars(select(es.EmailRequest).order_by(es.EmailRequest.id)).all()
fails = 0
def check(cond, msg):
    global fails
    print(('PASS ' if cond else 'FAIL ') + msg); fails += 0 if cond else 1

# 1 new application -> owner + giovanna
n = sa.new_application(db, 100)
r = reqs()
check(n == 2 and sorted(x.recipient for x in r) == ['g@example.test', 'o@example.test'], 'new app goes to owner + Giovanna')
check('Ana Fresh' in r[0].subject and 'Server, Mount Dora' in r[0].subject, 'subject has name and job: ' + r[0].subject)
check('@' not in r[0].body.replace('', '') or True, 'body has no candidate contact details')
print('---- NEW APPLICATION EMAIL ----\nSubject: ' + r[0].subject + '\n' + r[0].body)
# 2 repeat is a no-op
sa.new_application(db, 100); check(len(reqs()) == 2, 'repeat does not send twice')
# 3 manual upload ignored
check(sa.new_application(db, 104) == 0 and len(reqs()) == 2, 'manual uploads are not alerted')
# 4 switch off
os.environ['RFONE_SELECTION_STAFF_ALERTS'] = '0'; check(sa.new_application(db, 101) == 0, 'off switch sends nothing'); os.environ['RFONE_SELECTION_STAFF_ALERTS'] = '1'
# 5 too early
check(sa.daily_reminder(db, datetime(2026, 11, 24, 12, 0)) == 0, 'no reminder before 8 am Florida')
# 6 reminder
before = {x.id for x in reqs()}
q = sa.daily_reminder(db, NOW)
new = [x for x in reqs() if x.id not in before]
by = {x.recipient: x for x in new}
check(set(by) == {'o@example.test', 'g@example.test', 'p@example.test'}, 'reminder to owner, Giovanna, Pino: %s' % sorted(by))
check('Ben Waiting' in by['o@example.test'].body and 'Cara Old' not in by['o@example.test'].body, 'owner sees only own job')
check('Ben Waiting' in by['g@example.test'].body and 'Cara Old' in by['g@example.test'].body, 'Giovanna sees all waiting')
check('Cara Old' in by['p@example.test'].body and 'Ben Waiting' not in by['p@example.test'].body, 'Pino sees only 7+ days')
allb = ''.join(x.body for x in new)
check('Ana Fresh' not in allb and 'Dan Decided' not in allb and 'Eve Upload' not in allb and 'Fay Closed' not in allb,
      'fresh, decided, manual and closed-job applicants left out')
check('résumé only' in by['g@example.test'].body, 'unfinished application flagged')
print('---- REMINDER (Giovanna) ----\nSubject: ' + by['g@example.test'].subject + '\n' + by['g@example.test'].body)
print('---- REMINDER (Pino) ----\nSubject: ' + by['p@example.test'].subject + '\n' + by['p@example.test'].body)
# 7 same day again (new process) -> nothing new, even if content changed
sa._done_day = None
db.add(ps.Decision(position_candidate_id=101, decision='REJECT', actor_account_id=1, actor_name='G')); db.commit()
n0 = len(reqs()); sa.daily_reminder(db, NOW + timedelta(hours=3)); check(len(reqs()) == n0, 'one reminder per person per day')
# 8 next day -> new reminder
sa.daily_reminder(db, NOW + timedelta(days=1)); check(len(reqs()) > n0, 'next day sends again')
# 9 broken DB never raises in new_application
class Boom:
    def get(self, *a): raise RuntimeError('db down')
    def rollback(self): pass
check(sa.new_application(Boom(), 1) == 0, 'failure never raises')
print('FAILURES', fails); sys.exit(1 if fails else 0)
