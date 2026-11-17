"""Build/deploy only Email Control presentation over the current running image.

No schema migrations, worker changes, SMTP access or production queue writes.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import boto3

ROOT = Path(__file__).resolve().parents[4]
STATE = Path(tempfile.gettempdir()) / 'rfone-email-ui-release-state.json'
SERVICE = 'arn:aws:apprunner:us-east-1:418674484214:service/rfone-web/07524815436944e3a05c600c5486f951'
BUCKET = 'rfone-tips-deploy-418674484214'
REPO = '418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web'
RELEASE = '03 Software/Infrastructure/deploy/rfone-email/'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'status', 'deploy', 'rollback'])
    args = parser.parse_args()
    aws = boto3.Session(profile_name='rfone-dev-login', region_name='us-east-1')
    assert aws.client('sts').get_caller_identity()['Account'] == '418674484214'
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    app = aws.client('apprunner')
    live = app.describe_service(ServiceArn=SERVICE)['Service']
    if args.action == 'build':
        assert live['Status'] == 'RUNNING'
        state['original_source'] = live['SourceConfiguration']
        current = state['original_source']['ImageRepository']['ImageIdentifier']
        assert current.startswith(REPO + ':'), 'Unexpected base repository'
        image = aws.client('ecr').describe_images(repositoryName='rfone-web',
            imageIds=[{'imageTag': current.split(':')[-1]}])['imageDetails'][0]
        state['base_digest'] = image['imageDigest']
        state['commit'] = git('rev-parse', 'HEAD').decode().strip()
        state['tag'] = 'email-ui-' + state['commit'][:12]
        state['image'] = REPO + ':' + state['tag']
        state['source_key'] = 'email/ui/releases/' + state['commit'] + '/source.zip'
        archive = Path(tempfile.gettempdir()) / (state['tag'] + '.zip')
        payload = ['email_routes.py', 'templates/_email_layout.html', 'templates/email_control.html',
                   'templates/email_detail.html', 'static/css/email-control.css']
        dockerfile = f'''FROM {REPO}@{state['base_digest']}
COPY ["payload/", "/app/RF-One Web/"]
COPY ["tests/test_email_service.py", "/app/RF-One Web/tests/test_email_service.py"]
COPY ["patch_timezone.py", "/opt/rfone-email-ui/patch_timezone.py"]
RUN python /opt/rfone-email-ui/patch_timezone.py
'''
        buildspec = '''version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
  build:
    commands:
      - docker build -t $ECR_URI:$EMAIL_UI_TAG .
      - docker run --rm -e PYTHONDONTWRITEBYTECODE=1 $ECR_URI:$EMAIL_UI_TAG python "/app/RF-One Web/tests/test_email_service.py"
  post_build:
    commands:
      - test "$CODEBUILD_BUILD_SUCCEEDING" = "1"
      - docker push $ECR_URI:$EMAIL_UI_TAG
'''
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for path in payload:
                z.writestr('payload/' + path, git('show', state['commit'] + ':03 Software/RF-One Web/' + path))
            z.writestr('tests/test_email_service.py', git('show', state['commit'] + ':03 Software/RF-One Web/tests/test_email_service.py'))
            z.writestr('patch_timezone.py', git('show', state['commit'] + ':' + RELEASE + 'patch_timezone.py'))
            z.writestr('Dockerfile', dockerfile)
            z.writestr('buildspec.yml', buildspec)
        aws.client('s3').upload_file(str(archive), BUCKET, state['source_key'])
        state['build'] = aws.client('codebuild').start_build(projectName='rfone-web-build',
            sourceLocationOverride=BUCKET + '/' + state['source_key'], buildspecOverride=buildspec,
            environmentVariablesOverride=[dict(name='EMAIL_UI_TAG', value=state['tag'], type='PLAINTEXT')])['build']['id']
        print('UI_BUILD_STARTED', state['build'], state['commit'])
    elif args.action == 'status':
        build = aws.client('codebuild').batch_get_builds(ids=[state['build']])['builds'][0]
        state['build_status'] = build['buildStatus']
        print('UI_BUILD', build['buildStatus'], build.get('currentPhase'))
        print('WEB', live['Status'], live['SourceConfiguration']['ImageRepository']['ImageIdentifier'])
        if state.get('operation'):
            for operation in app.list_operations(ServiceArn=SERVICE)['OperationSummaryList']:
                if operation['Id'] == state['operation']:
                    state['operation_status'] = operation['Status']
                    print('UI_DEPLOY', operation['Status'])
        if build['buildStatus'] == 'FAILED':
            for event in aws.client('logs').get_log_events(logGroupName=build['logs']['groupName'],
                logStreamName=build['logs']['streamName'], limit=40)['events']:
                print(event['message'].rstrip())
    elif args.action == 'deploy':
        assert state.get('build_status') == 'SUCCEEDED'
        assert live['Status'] == 'RUNNING'
        assert live['SourceConfiguration'] == state['original_source'], 'Concurrent Web release detected'
        source = json.loads(json.dumps(state['original_source']))
        source['ImageRepository']['ImageIdentifier'] = state['image']
        source['ImageRepository']['ImageConfiguration'].setdefault('RuntimeEnvironmentVariables', {})['RFONE_EMAIL_UI_RELEASE'] = state['commit']
        state['operation'] = app.update_service(ServiceArn=SERVICE, SourceConfiguration=source)['OperationId']
        print('UI_DEPLOY_STARTED', state['operation'])
    else:
        assert live['SourceConfiguration']['ImageRepository']['ImageIdentifier'] == state['image']
        print('UI_ROLLBACK_STARTED', app.update_service(ServiceArn=SERVICE, SourceConfiguration=state['original_source'])['OperationId'])
    STATE.write_text(json.dumps(state, indent=2, default=str), encoding='utf-8')


if __name__ == '__main__':
    import zipfile
    main()
