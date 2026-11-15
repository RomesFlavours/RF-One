"""Validate edited migration choices. This command never imports data or connects to AWS."""
import argparse,csv,json,hashlib
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);args=parser.parse_args();root=args.review.resolve()
    def read(name):
        with (root/name).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
    errors=[]
    with (root/'local-baseline.sqlite').open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    if actual!=summary['local_snapshot_sha256']:errors.append('Local baseline checksum changed.')
    rehearsal=root/'schema-rehearsal.json'
    if not rehearsal.exists() or not json.loads(rehearsal.read_text()).get('local_app_schema_compatibility_verified'):errors.append('Successful isolated schema rehearsal required.')
    positions=json.loads((root/'positions.json').read_text(encoding='utf-8'));aws_positions={str(p['id']) for p in positions['aws_operational']}
    cloud_roles={p['role_code'] for p in positions['aws_operational']}
    document_inventory=json.loads((root/'document-inventory.json').read_text(encoding='utf-8'))
    cloud_documents={str(d['id']):d for d in document_inventory['aws_operational']}
    cloud_candidates={str(c['id']) for c in json.loads((root/'candidates.json').read_text(encoding='utf-8'))['aws_operational']}
    accounts=json.loads((root/'account-identifiers.json').read_text(encoding='utf-8'));active_accounts={str(a['id']) for a in accounts['aws_operational'] if a['status']=='ACTIVE'}
    restaurants=json.loads((root/'restaurant-identifiers.json').read_text(encoding='utf-8'));organizations={str(r['id']) for r in restaurants['aws_operational']}
    for row in read('role-decisions.csv'):
        if row['decision'] not in ('KEEP_NEW_ROLE','MAP_EXISTING_ROLE') or not row['approved_target_code']:errors.append('Role requires approval: '+row['local_role_name'])
        elif row['decision']=='MAP_EXISTING_ROLE' and row['approved_target_code'] not in cloud_roles:errors.append('Unknown AWS role alias: '+row['local_role_name'])
    for row in read('local-position-decisions.csv'):
        if row['decision'] not in ('KEEP_SEPARATE','MERGE_EXISTING','EXCLUDE_LOCAL_TEST'):errors.append('Position requires approval: '+row['local_position_id'])
        elif row['decision']=='MERGE_EXISTING' and row['approved_target_position'] not in aws_positions:errors.append('Invalid AWS position: '+row['local_position_id'])
        if row['decision']!='EXCLUDE_LOCAL_TEST' and row['approved_manager_account_id'] not in active_accounts:errors.append('Existing active AWS manager required: '+row['local_position_id'])
    for row in read('position-organization-decisions.csv'):
        if row['approved_aws_restaurant_id'] not in organizations:errors.append('Organization approval required for local position '+row['local_position_id'])
    for row in read('account-decisions.csv'):
        if row['decision'] not in ('MAP_EXISTING_ACCOUNT','KEEP_ORIGINAL_ACTOR_TEXT'):
            errors.append('Actor/account review required: '+row['source_account_id'])
        elif row['decision']=='MAP_EXISTING_ACCOUNT' and row['approved_aws_account_id'] not in active_accounts:errors.append('Invalid active AWS account: '+row['source_account_id'])
    for row in read('document-decisions.csv'):
        if row['approved_action'] not in ('IMPORT_NEW_DOCUMENT','REUSE_DOCUMENT','EXCLUDE_AFTER_REVIEW'):errors.append('CV document review required: '+row['local_raw_resume_id'])
        elif row['approved_action']=='REUSE_DOCUMENT':
            target=cloud_documents.get(row['approved_target_id'])
            if not target or target['sha256']!=row['sha256']:errors.append('Reused document must exist and have identical bytes: '+row['local_raw_resume_id'])
    for row in read('candidate-decisions.csv'):
        if row['approved_action'] not in ('IMPORT_NEW_CANDIDATE','REUSE_EXISTING_CANDIDATE','EXCLUDE_AFTER_REVIEW'):errors.append('Candidate review required: '+row['local_candidate_id'])
        elif row['approved_action']=='REUSE_EXISTING_CANDIDATE' and row['approved_target_id'] not in cloud_candidates:errors.append('Existing candidate target required: '+row['local_candidate_id'])
    policy=json.loads((root/'prototype-decision.json').read_text(encoding='utf-8'))
    if policy.get('reviewed') is not True:errors.append('Prototype archive policy requires review.')
    if policy.get('decision')!='ARCHIVE_ONLY':errors.append('Prototype import requires a separate selproto-to-workspace data adapter.')
    result={'choices_complete':not errors,'errors':errors,'data_import_performed':False,'aws_access':False,
        'next_step':'Rehearse the data import on an isolated clone; approval is not authorization to deploy.' if not errors else 'Complete the listed choices before a data-import rehearsal.'}
    (root/'choices-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('CHOICES:', 'COMPLETE' if not errors else 'BLOCKED',len(errors),'unresolved items; no data imported.')
    raise SystemExit(0 if not errors else 2)


if __name__=='__main__':main()
