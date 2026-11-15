"""Ensure migration review gates reject wrong identities and incomplete choices."""
import csv,hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path


class MigrationChoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='selection-choice-test-');self.root=Path(self.temp.name)
        self.root.joinpath('local-baseline.sqlite').write_bytes(b'isolated-review-baseline')
        self.json('summary.json',{'local_snapshot_sha256':hashlib.sha256(b'isolated-review-baseline').hexdigest()})
        self.json('schema-rehearsal.json',{'local_app_schema_compatibility_verified':True})
        self.json('positions.json',{'aws_operational':[{'id':3,'role_code':'SERVER'}]})
        self.json('document-inventory.json',{'aws_operational':[{'id':9,'sha256':'original-A'}]})
        self.json('candidates.json',{'aws_operational':[{'id':15}]})
        self.json('account-identifiers.json',{'aws_operational':[{'id':4,'status':'ACTIVE'}]})
        self.json('restaurant-identifiers.json',{'aws_operational':[{'id':1}]})
        self.json('prototype-decision.json',{'decision':'ARCHIVE_ONLY','reviewed':True})
        self.csv('role-decisions.csv',{'local_role_name':'Server','decision':'MAP_EXISTING_ROLE','approved_target_code':'SERVER'})
        self.csv('local-position-decisions.csv',{'local_position_id':'2','decision':'MERGE_EXISTING','approved_target_position':'3','approved_manager_account_id':'4'})
        self.csv('position-organization-decisions.csv',{'local_position_id':'2','approved_aws_restaurant_id':'1'})
        self.csv('account-decisions.csv',{'source_account_id':'1','decision':'MAP_EXISTING_ACCOUNT','approved_aws_account_id':'4'})
        self.csv('document-decisions.csv',{'local_raw_resume_id':'1','approved_action':'IMPORT_NEW_DOCUMENT','approved_target_id':'','sha256':'local-B'})
        self.csv('candidate-decisions.csv',{'local_candidate_id':'1','approved_action':'IMPORT_NEW_CANDIDATE','approved_target_id':''})

    def tearDown(self):self.temp.cleanup()
    def json(self,name,data):self.root.joinpath(name).write_text(json.dumps(data),encoding='utf-8')
    def csv(self,name,row):
        with self.root.joinpath(name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(row));writer.writeheader();writer.writerow(row)
    def validate(self):
        return subprocess.run([sys.executable,str(Path(__file__).with_name('validate_choices.py')),'--review',str(self.root)],capture_output=True,text=True)

    def test_complete_choices_pass_without_import(self):
        self.assertEqual(self.validate().returncode,0)
        self.assertFalse(json.loads(self.root.joinpath('choices-validation.json').read_text())['data_import_performed'])

    def test_same_numeric_document_id_with_different_bytes_is_rejected(self):
        self.csv('document-decisions.csv',{'local_raw_resume_id':'1','approved_action':'REUSE_DOCUMENT','approved_target_id':'9','sha256':'local-B'})
        self.assertEqual(self.validate().returncode,2)

    def test_unknown_manager_is_rejected(self):
        self.csv('local-position-decisions.csv',{'local_position_id':'2','decision':'MERGE_EXISTING','approved_target_position':'3','approved_manager_account_id':'999'})
        self.assertEqual(self.validate().returncode,2)

    def test_changed_local_baseline_is_rejected(self):
        self.root.joinpath('local-baseline.sqlite').write_bytes(b'changed')
        self.assertEqual(self.validate().returncode,2)


if __name__=='__main__':unittest.main()
