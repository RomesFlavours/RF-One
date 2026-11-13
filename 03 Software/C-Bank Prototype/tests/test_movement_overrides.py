"""Manual WHY and WHOM survive engine recalculation; pair defaults remain unchanged."""
import sys, unittest
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import _isolated
from cbank import config, engine as E, legacy, store
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import source_classification as sc

class MovementOverrideTests(unittest.TestCase):
    def test_manual_fields_are_isolated_and_survive_new_engine(self):
        sql=create_engine('sqlite:///'+config.BANK_DB.as_posix())
        with Session(sql) as db:
            groups=sc.movement_groups(db)
            key, rows=next((k,v) for k,v in groups.items() if len(v)>1)
            pair=db.scalar(select(m.BankWhoSourceClassification).where(
                m.BankWhoSourceClassification.occurrence_id==key[0],
                m.BankWhoSourceClassification.payment_instrument_id==key[1]))
            before_pairs=[(p.id,p.transaction_reason_id) for p in db.scalars(select(m.BankWhoSourceClassification))]
            target,other=rows[0]['id'],rows[1]['id']
            other_before=db.get(m.FinancialTransaction,other).explanation_id
            eng=E.Engine(db,store.connect(':memory:'))
            before=eng.evaluate(eng.by_id[target]);owner=before['payer_id']
            why=next(w for w,r in eng.c.whys.items() if r.accounting_classification_id and w not in eng.provisional and w!=before['why_id'])
            whom=next(e.id for e in eng.c.entities.values() if e.status=='ACTIVE' and e.id!=owner)
            sc.save_movement_override(db,classification_id=pair.id,transaction_id=target,
                why_id=why,whom_id=whom,account_id=None)
            for repeat in range(2):
                fresh=E.Engine(db,store.connect(':memory:'))
                result=fresh.evaluate(fresh.by_id[target])
                self.assertEqual(result['why_id'],why)
                self.assertEqual(result['category_id'],fresh.c.whys[why].accounting_classification_id)
                self.assertEqual(result['beneficiary_id'],whom)
                self.assertEqual(result['beneficiary_method'],E.HUMAN_BANK)
                self.assertEqual(result['payer_id'],owner)
                # Changing the pair default cannot replace the manual WHY.
                pair.transaction_reason_id=next(w for w,r in fresh.c.whys.items() if r.accounting_classification_id and w not in fresh.provisional and w!=why)
                db.flush()
            pair.transaction_reason_id=dict(before_pairs)[pair.id]
            self.assertEqual(before_pairs,[(p.id,p.transaction_reason_id) for p in db.scalars(select(m.BankWhoSourceClassification))])
            self.assertEqual(db.get(m.FinancialTransaction,other).explanation_id,other_before)
            with self.assertRaises(ValueError):
                sc.save_movement_override(db,classification_id=pair.id,transaction_id=-999,
                    why_id=why,whom_id=whom,account_id=None)
            db.rollback()

    def test_manual_whom_protected_without_human_who(self):
        eng=E.Engine(legacy.session(),store.connect(':memory:'))
        txn=next(t for t in eng.txns if eng.bank_decision(t)['source']!='HUMAN')
        old=eng.bank_decision
        owner=eng.owner(txn)
        whom=next(e.id for e in eng.c.entities.values() if e.status=='ACTIVE' and (not owner or e.id!=owner.id))
        eng.bank_decision=lambda t:dict(old(t),beneficiary_human=True,beneficiary_id=whom)
        result=eng.evaluate(txn)
        self.assertEqual(result['beneficiary_id'],whom)
        self.assertEqual(result['beneficiary_method'],E.HUMAN_BANK)
        eng.db.close()

if __name__=='__main__':unittest.main()
