"""Release rfone-selection from one pushed Git commit (SELECTION_DEPLOY_GUARD_001).

    python release_selection.py <label> [--commit <sha>] [--no-snapshot]

The only supported way to publish Selection. It refuses a commit that is not
on origin or lacks the Selection workspace, installs this commit's
buildspec.yml as the CodeBuild project's own buildspec (so any other ZIP
uploaded to the project is refused too), snapshots RDS, backs up the current
source ZIP and image, builds `rfone-selection:sel-<commit12>`, deploys only
that image and verifies the public /candidate/bridge/health. A failed check
restores the previous image. Other App Runner services are never touched.
Runtime settings and secrets are kept from the live service; the RMAED relay
key is read from Secrets Manager, never from a file or an environment value.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import boto3

REGION = 'us-east-1'
ACCOUNT = '418674484214'
SERVICE_ARN = f'arn:aws:apprunner:{REGION}:{ACCOUNT}:service/rfone-selection/f3c0d46758b44c38b3200947ca8c3a15'
REPOSITORY = 'rfone-selection'
ECR_URI = f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{REPOSITORY}'
PROJECT = 'rfone-selection-build'
BUCKET = f'rfone-tips-deploy-{ACCOUNT}'
SOURCE_KEY = 'rfone-selection-source.zip'
DB_INSTANCE = 'rfone-dev'
RELAY_SECRET = f'arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:rfone-selection/rmaed-relay-key-PJxbvJ'
HEALTH_URL = 'https://rfone.romesflavours.com/selection/candidate/bridge/health'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # repository root: paths below are relative to it
DEPLOY_DIR = '03 Software/Infrastructure/deploy/rfone-selection'
REQUIRED = ['03 Software/Selection/workspace/aruba_bridge.py', '03 Software/Selection/workspace/routes.py',
            '03 Software/Selection/workspace/careers.py', '03 Software/Selection/workspace/schema.py',
            '03 Software/RF-One Data Store/rfone_data_store/selection/workspace_models.py']


def git(*args: str, binary: bool = False):
    out = subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True).stdout
    return out if binary else out.decode().strip()


def log(message: str) -> None:
    print(time.strftime('%H:%M:%S'), message, flush=True)


def source_zip(commit: str) -> bytes:
    """`RF-One Data Store/` and `Selection/` exactly as committed, plus the Dockerfile and RELEASE_COMMIT."""
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as out:
        for folder in ('RF-One Data Store', 'Selection'):
            archive = git('archive', '--format=tar', commit, f'03 Software/{folder}', binary=True)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        out.writestr(member.name.removeprefix('03 Software/'), tar.extractfile(member).read())
        out.writestr('Dockerfile', git('show', f'{commit}:{DEPLOY_DIR}/Dockerfile', binary=True))
        out.writestr('RELEASE_COMMIT', commit + '\n')
    return data.getvalue()


def wait_operation(apprunner, operation_id: str) -> str:
    while True:
        for op in apprunner.list_operations(ServiceArn=SERVICE_ARN, MaxResults=20)['OperationSummaryList']:
            if op['Id'] == operation_id and op['Status'] not in ('PENDING', 'IN_PROGRESS', 'ROLLBACK_IN_PROGRESS'):
                return op['Status']
        time.sleep(15)


def deploy_image(apprunner, image: str, settings: dict) -> str:
    repo = settings['ImageRepository']
    secrets = dict(repo['ImageConfiguration'].get('RuntimeEnvironmentSecrets', {}))
    variables = dict(repo['ImageConfiguration'].get('RuntimeEnvironmentVariables', {}))
    variables.pop('RFONE_SELECTION_ARUBA_KEY', None)  # a plaintext key is never redeployed
    secrets['RFONE_SELECTION_ARUBA_KEY'] = RELAY_SECRET
    source = {'ImageRepository': {'ImageIdentifier': image, 'ImageRepositoryType': 'ECR', 'ImageConfiguration': {
        'Port': repo['ImageConfiguration']['Port'], 'RuntimeEnvironmentVariables': variables,
        'RuntimeEnvironmentSecrets': secrets}},
        'AutoDeploymentsEnabled': False, 'AuthenticationConfiguration': settings['AuthenticationConfiguration']}
    operation = apprunner.update_service(ServiceArn=SERVICE_ARN, SourceConfiguration=source)['OperationId']
    log(f'App Runner operation {operation} for {image}')
    return wait_operation(apprunner, operation)


def bridge_health() -> dict | None:
    for _ in range(12):
        try:
            with urlopen(HEALTH_URL, timeout=20) as response:
                body = json.loads(response.read())
            if body.get('version', '').startswith('rmaed-selection-bridge') and body.get('enabled') is True:
                return body
        except Exception as exc:  # noqa: BLE001 — retried, then reported
            log(f'health not ready: {type(exc).__name__}')
        time.sleep(10)
    return None


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        sys.exit(__doc__)
    label = args[0]
    commit = git('rev-parse', args[args.index('--commit') + 1] if '--commit' in args else 'HEAD')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz')
    git('fetch', '--quiet', 'origin')
    if not git('branch', '-r', '--contains', commit):
        sys.exit(f'REFUSED: {commit} is not pushed to origin.')
    tree = set(git('ls-tree', '-r', '--name-only', commit, '--', '03 Software').splitlines())
    missing = [f for f in REQUIRED if f not in tree]
    if missing:
        sys.exit(f'REFUSED: {commit} lacks the Selection workspace: {missing}')
    session = boto3.Session(region_name=REGION)
    assert session.client('sts').get_caller_identity()['Account'] == ACCOUNT
    s3, codebuild, apprunner, ecr, rds = (session.client(n) for n in ('s3', 'codebuild', 'apprunner', 'ecr', 'rds'))
    record = {'label': label, 'commit': commit, 'started_utc': stamp}

    settings = apprunner.describe_service(ServiceArn=SERVICE_ARN)['Service']['SourceConfiguration']
    previous = settings['ImageRepository']['ImageIdentifier']
    record['previous_image'] = previous
    digest = ecr.batch_get_image(repositoryName=REPOSITORY, imageIds=[{'imageTag': previous.rsplit(':', 1)[1]}])['images'][0]
    rollback_tag = f'pre-{label}-{stamp}'
    ecr.put_image(repositoryName=REPOSITORY, imageManifest=digest['imageManifest'], imageTag=rollback_tag)
    record['rollback_image'] = f'{ECR_URI}:{rollback_tag}'
    backup_key = f'backups/rfone-selection-source-pre-{label}-{stamp}.zip'
    s3.copy_object(Bucket=BUCKET, Key=backup_key, CopySource={'Bucket': BUCKET, 'Key': SOURCE_KEY})
    record['source_backup'] = f's3://{BUCKET}/{backup_key}'
    log(f'rollback image {rollback_tag}, source backup {backup_key}')

    if '--no-snapshot' not in args:
        snapshot = f'{DB_INSTANCE}-pre-selection-{label}-{stamp}'.replace('_', '-')
        rds.create_db_snapshot(DBInstanceIdentifier=DB_INSTANCE, DBSnapshotIdentifier=snapshot)
        log(f'RDS snapshot {snapshot} ...')
        rds.get_waiter('db_snapshot_available').wait(DBSnapshotIdentifier=snapshot,
                                                     WaiterConfig={'Delay': 30, 'MaxAttempts': 80})
        record['rds_snapshot'] = snapshot

    buildspec = git('show', f'{commit}:{DEPLOY_DIR}/buildspec.yml')
    project = codebuild.batch_get_projects(names=[PROJECT])['projects'][0]
    if project['source'].get('buildspec') != buildspec:
        codebuild.update_project(name=PROJECT, source={**project['source'], 'buildspec': buildspec})
        log('CodeBuild project buildspec installed from the release commit')
    s3.put_object(Bucket=BUCKET, Key=SOURCE_KEY, Body=source_zip(commit))
    build_id = codebuild.start_build(projectName=PROJECT)['build']['id']
    log(f'build {build_id}')
    while (build := codebuild.batch_get_builds(ids=[build_id])['builds'][0])['buildStatus'] == 'IN_PROGRESS':
        time.sleep(20)
    record['build'] = build_id
    if build['buildStatus'] != 'SUCCEEDED':
        s3.copy_object(Bucket=BUCKET, Key=SOURCE_KEY, CopySource={'Bucket': BUCKET, 'Key': backup_key})
        sys.exit(f'BUILD {build["buildStatus"]}: nothing deployed. Logs: /aws/codebuild/{PROJECT}')

    image = f'{ECR_URI}:sel-{commit[:12]}'
    status = deploy_image(apprunner, image, settings)
    health = bridge_health() if status == 'SUCCEEDED' else None
    record.update(image=image, deployment=status, health=health)
    if health is None:
        log('VERIFICATION FAILED: restoring the previous image')
        record['rollback'] = deploy_image(apprunner, record['rollback_image'], settings)
        print(json.dumps(record, indent=2))
        sys.exit(1)
    record['finished_utc'] = datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
