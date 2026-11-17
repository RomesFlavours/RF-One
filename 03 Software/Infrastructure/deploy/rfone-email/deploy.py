"""RF-One email release using existing ECR/CodeBuild, ECS cluster and NAT.

Each action is explicit. State contains AWS references, never secret values.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile

import boto3

ROOT = Path(__file__).resolve().parents[4]
PREFIX = '03 Software/Infrastructure/deploy/rfone-email/'
STATE = Path(tempfile.gettempdir()) / 'rfone-email-aws-release-state.json'
SERVICE = 'arn:aws:apprunner:us-east-1:418674484214:service/rfone-web/07524815436944e3a05c600c5486f951'
BASE = '418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:home-no-selection-old-e0cb4ea'
BUCKET = 'rfone-tips-deploy-418674484214'
DB_SECRET = 'arn:aws:secretsmanager:us-east-1:418674484214:secret:rfone-tips/database-url-chNZo8'
SMTP_SECRET = 'arn:aws:secretsmanager:us-east-1:418674484214:secret:rfone-selection/smtp-password'
EXECUTION_ROLE = 'arn:aws:iam::418674484214:role/rfone-clover-acquisition-job-execution-role'
WORKER_ROLE = 'rfone-email-worker-task-role'
SNAPSHOT = 'rfone-dev-pre-email-20261117t204618z'
NETWORK = {'awsvpcConfiguration': dict(
    subnets=['subnet-093b696170e73a5a1', 'subnet-0fa916c6b35d78a97', 'subnet-0ff9dd5e924d7e7f0'],
    securityGroups=['sg-0a4d4d094ea0d0fc3', 'sg-0eb82e56890163eb5'], assignPublicIp='DISABLED')}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def save(state):
    STATE.write_text(json.dumps(state, indent=2, default=str), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['build', 'status', 'preflight', 'migrate', 'api', 'worker', 'verify', 'rollback'])
    args = p.parse_args()
    aws = boto3.Session(profile_name='rfone-dev-login', region_name='us-east-1')
    assert aws.client('sts').get_caller_identity()['Account'] == '418674484214'
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    app = aws.client('apprunner')
    ecs = aws.client('ecs')

    if args.action == 'build':
        live = app.describe_service(ServiceArn=SERVICE)['Service']
        assert live['Status'] == 'RUNNING'
        assert live['SourceConfiguration']['ImageRepository']['ImageIdentifier'] == BASE, 'Live base changed'
        state['original_source'] = live['SourceConfiguration']
        state['release'] = git('rev-parse', 'HEAD').decode().strip()
        state['tag'] = 'email-' + state['release'][:12]
        state['image'] = '418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:' + state['tag']
        state['snapshot'] = SNAPSHOT
        key = 'email/releases/' + state['release'] + '/source.zip'
        payload = [
            'RF-One Data Store/rfone_data_store/email_service.py',
            'RF-One Data Store/rfone_data_store/email_worker.py',
            'RF-One Data Store/rfone_data_store/technical/aruba_smtp.py',
            'RF-One Data Store/migrations/versions/k9g120261112_kitchen_aws_release.py',
            'RF-One Data Store/migrations/versions/t9e120261113_training_enrollment_aws.py',
            'RF-One Data Store/migrations/versions/e9a120261117_shared_email_service_aws.py',
            'RF-One Web/email_routes.py', 'RF-One Web/templates/email_control.html',
            'RF-One Web/templates/email_detail.html']
        archive = Path(tempfile.gettempdir()) / ('rfone-email-' + state['release'][:12] + '.zip')
        buildspec = '''version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
  build:
    commands:
      - docker build -t $ECR_URI:$EMAIL_RELEASE_TAG .
      - docker run --rm $ECR_URI:$EMAIL_RELEASE_TAG python /opt/rfone-email-release/check_image.py
  post_build:
    commands:
      - test "$CODEBUILD_BUILD_SUCCEEDING" = "1"
      - docker push $ECR_URI:$EMAIL_RELEASE_TAG
'''
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for name in payload:
                z.writestr('payload/' + name, git('show', state['release'] + ':03 Software/' + name))
            for name in ['patch_existing.py', 'release_check.py', 'check_image.py']:
                z.writestr('release/' + name, git('show', state['release'] + ':' + PREFIX + name))
            z.writestr('Dockerfile', git('show', state['release'] + ':' + PREFIX + 'Dockerfile'))
            z.writestr('buildspec.yml', buildspec)
        aws.client('s3').upload_file(str(archive), BUCKET, key)
        state['source_key'] = key
        r = aws.client('codebuild').start_build(projectName='rfone-web-build',
            sourceLocationOverride=BUCKET + '/' + key, buildspecOverride=buildspec,
            environmentVariablesOverride=[dict(name='EMAIL_RELEASE_TAG', value=state['tag'], type='PLAINTEXT')])
        state['build'] = r['build']['id']
        save(state)
        print('EMAIL_BUILD_STARTED', state['build'], state['release'])
        return

    if args.action == 'status':
        if state.get('build'):
            b = aws.client('codebuild').batch_get_builds(ids=[state['build']])['builds'][0]
            print('BUILD', b['buildStatus'], b.get('currentPhase'))
            if b['buildStatus'] == 'FAILED':
                for phase in b.get('phases', []):
                    for ctx in phase.get('contexts', []):
                        print('BUILD_FAILURE', ctx.get('statusCode'), ctx.get('message'))
            state['build_status'] = b['buildStatus']
        d = aws.client('rds').describe_db_snapshots(DBSnapshotIdentifier=SNAPSHOT)['DBSnapshots'][0]
        print('SNAPSHOT', d['Status'])
        for mode in ['preflight', 'migrate', 'verify']:
            if state.get(mode + '_task'):
                task = ecs.describe_tasks(cluster='rfone-jobs', tasks=[state[mode + '_task']])['tasks'][0]
                print('TASK', mode, task['lastStatus'], task.get('stoppedReason', ''))
                if task['containers'][0].get('lastStatus') == 'STOPPED':
                    state[mode + '_exit'] = task['containers'][0].get('exitCode', -1)
                    print('EXIT', mode, state[mode + '_exit'])
                stream = f"release/email/{task['taskArn'].split('/')[-1]}"
                try:
                    for event in aws.client('logs').get_log_events(logGroupName='/ecs/rfone-email-service', logStreamName=stream)['events']:
                        print(event['message'])
                except aws.client('logs').exceptions.ResourceNotFoundException:
                    pass
        print('API', app.describe_service(ServiceArn=SERVICE)['Service']['Status'])
        services = ecs.describe_services(cluster='rfone-jobs', services=['rfone-email-service'])['services']
        if services:
            service = services[0]
            print('WORKER', json.dumps({k: service.get(k) for k in ['status','desiredCount','runningCount','pendingCount']}))
            for d in service.get('deployments', []):
                print('WORKER_DEPLOYMENT', d.get('rolloutState'), d.get('rolloutStateReason'))
        save(state)
        return

    assert state.get('build_status') == 'SUCCEEDED', 'Build must succeed first; run status'
    if args.action in ['preflight', 'migrate', 'verify', 'worker']:
        iam = aws.client('iam')
        try:
            role = iam.get_role(RoleName=WORKER_ROLE)['Role']
        except iam.exceptions.NoSuchEntityException:
            role = iam.create_role(RoleName=WORKER_ROLE, AssumeRolePolicyDocument=json.dumps({
                'Version':'2012-10-17', 'Statement':[dict(Effect='Allow', Principal={'Service':'ecs-tasks.amazonaws.com'}, Action='sts:AssumeRole')]}))['Role']
        smtp_arn = aws.client('secretsmanager').describe_secret(SecretId=SMTP_SECRET)['ARN']
        iam.put_role_policy(RoleName=WORKER_ROLE, PolicyName='ReadOnlyArubaSmtpSecret', PolicyDocument=json.dumps({
            'Version':'2012-10-17','Statement':[dict(Effect='Allow',Action='secretsmanager:GetSecretValue',Resource=smtp_arn)]}))
        config = state['original_source']['ImageRepository']['ImageConfiguration']['RuntimeEnvironmentVariables']
        env = {k: config[k] for k in ['RFONE_SMTP_HOST','RFONE_SMTP_PORT','RFONE_SMTP_USERNAME','RFONE_EMAIL_FROM_ADDRESS']}
        env.update(AWS_REGION='us-east-1', PYTHONUNBUFFERED='1', PYTHONPATH='/app/RF-One Data Store', RFONE_EMAIL_SMTP_SECRET_ID=smtp_arn)
        container = dict(name='email', image=state['image'], essential=True, workingDirectory='/app/RF-One Data Store',
            environment=[dict(name=k,value=v) for k,v in env.items()], secrets=[dict(name='RFONE_DATABASE_URL',valueFrom=DB_SECRET)],
            logConfiguration=dict(logDriver='awslogs',options={'awslogs-group':'/ecs/rfone-email-service','awslogs-region':'us-east-1','awslogs-stream-prefix':'release'}))
        if args.action == 'worker':
            assert state.get('migrate_exit') == 0, 'Migration must succeed first'
            container['command'] = ['python','-m','rfone_data_store.email_worker','--send','--interval','10']
        else:
            if args.action == 'migrate':
                assert state.get('preflight_exit') == 0, 'PostgreSQL and Aruba preflight must succeed'
                assert aws.client('rds').describe_db_snapshots(DBSnapshotIdentifier=SNAPSHOT)['DBSnapshots'][0]['Status'] == 'available'
            container['command'] = ['python','/opt/rfone-email-release/release_check.py',args.action]
        definition = ecs.register_task_definition(family='rfone-email-service' if args.action == 'worker' else 'rfone-email-release',
            requiresCompatibilities=['FARGATE'], networkMode='awsvpc', cpu='256', memory='512',
            executionRoleArn=EXECUTION_ROLE, taskRoleArn=role['Arn'], containerDefinitions=[container])['taskDefinition']['taskDefinitionArn']
        if args.action == 'worker':
            assert not ecs.describe_services(cluster='rfone-jobs',services=['rfone-email-service'])['services'], 'Worker service already exists'
            ecs.create_service(cluster='rfone-jobs', serviceName='rfone-email-service', taskDefinition=definition,
                desiredCount=1, launchType='FARGATE', networkConfiguration=NETWORK,
                deploymentConfiguration={'deploymentCircuitBreaker':{'enable':True,'rollback':True}})
            state['worker_definition'] = definition
            print('EMAIL_WORKER_CREATED', definition)
        else:
            for attempt in range(3):
                try:
                    r = ecs.run_task(cluster='rfone-jobs',taskDefinition=definition,launchType='FARGATE',networkConfiguration=NETWORK)
                    break
                except ecs.exceptions.ClientException as exc:
                    if 'unable to assume the role' not in str(exc) or attempt == 2:
                        raise
                    time.sleep(10)  # newly created IAM task role propagation
            assert not r['failures'], r['failures']
            state[args.action + '_task'] = r['tasks'][0]['taskArn']
            state.pop(args.action + '_exit', None)
            print('EMAIL_TASK_STARTED', args.action, state[args.action + '_task'])
    elif args.action == 'api':
        assert state.get('migrate_exit') == 0
        current = app.describe_service(ServiceArn=SERVICE)['Service']
        assert current['Status'] == 'RUNNING'
        assert current['SourceConfiguration'] == state['original_source'], 'Live configuration changed; refusing overwrite'
        source = json.loads(json.dumps(state['original_source']))
        source['ImageRepository']['ImageIdentifier'] = state['image']
        source['ImageRepository']['ImageConfiguration'].setdefault('RuntimeEnvironmentVariables', {})['RFONE_EMAIL_SERVICE_RELEASE'] = state['release']
        source['AutoDeploymentsEnabled'] = False
        state['api_operation'] = app.update_service(ServiceArn=SERVICE,SourceConfiguration=source)['OperationId']
        print('EMAIL_API_DEPLOY_STARTED', state['api_operation'])
    elif args.action == 'rollback':
        current = app.describe_service(ServiceArn=SERVICE)['Service']
        assert current['SourceConfiguration']['ImageRepository']['ImageIdentifier'] == state['image']
        print('ROLLBACK_API', app.update_service(ServiceArn=SERVICE, SourceConfiguration=state['original_source'])['OperationId'])
        if ecs.describe_services(cluster='rfone-jobs', services=['rfone-email-service'])['services']:
            ecs.update_service(cluster='rfone-jobs', service='rfone-email-service', desiredCount=0)
        print('Queue, audit and schema retained for reconciliation.')
    save(state)


if __name__ == '__main__':
    main()
