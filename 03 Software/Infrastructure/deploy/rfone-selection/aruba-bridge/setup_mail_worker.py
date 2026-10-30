"""Manage only Selection's mail wake-up worker and its own logs/schedule."""
import hashlib
import hmac
import io
import json
import sys
import time
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from urllib.request import Request, urlopen
import boto3

HERE = Path(__file__).parent
session = boto3.Session(region_name='us-east-1')
ACCOUNT = '418674484214'
NAME = 'rfone-selection-mail-worker'
ROLE = NAME + '-role'
RULE = NAME + '-minute'
# The relay key lives only in Secrets Manager (and in config.php on Aruba).
RELAY_SECRET = f'arn:aws:secretsmanager:us-east-1:{ACCOUNT}:secret:rfone-selection/rmaed-relay-key-PJxbvJ'
LAMBDA_ENV = {'Variables': {'RFONE_RELAY_SECRET_ID': RELAY_SECRET}}
mode = sys.argv[1]
assert session.client('sts').get_caller_identity()['Account'] == ACCOUNT
iam, lam, events = (session.client(n) for n in ['iam', 'lambda', 'events'])
key = session.client('secretsmanager').get_secret_value(SecretId=RELAY_SECRET)['SecretString']

if mode == 'setup':
    trust = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'lambda.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]}
    try:
        role = iam.get_role(RoleName=ROLE)['Role']
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust),
            Description='Selection-only RMAED mail transport wake-up worker')['Role']
    logs = session.client('logs')
    group = '/aws/lambda/' + NAME
    try:
        logs.create_log_group(logGroupName=group)
    except logs.exceptions.ResourceAlreadyExistsException:
        pass
    logs.put_retention_policy(logGroupName=group, retentionInDays=14)
    iam.put_role_policy(RoleName=ROLE, PolicyName=NAME + '-logs', PolicyDocument=json.dumps({
        'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': ['logs:CreateLogStream', 'logs:PutLogEvents'],
            'Resource': f'arn:aws:logs:us-east-1:{ACCOUNT}:log-group:{group}:*'}]}))
    iam.put_role_policy(RoleName=ROLE, PolicyName=NAME + '-relay-key', PolicyDocument=json.dumps({
        'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': 'secretsmanager:GetSecretValue',
            'Resource': RELAY_SECRET}]}))
    data = io.BytesIO()
    with ZipFile(data, 'w', ZIP_DEFLATED) as z:
        z.write(HERE / 'mail_lambda.py', 'mail_lambda.py')
    try:
        lam.get_function(FunctionName=NAME)
        lam.update_function_code(FunctionName=NAME, ZipFile=data.getvalue())
        lam.get_waiter('function_updated_v2').wait(FunctionName=NAME, WaiterConfig={'Delay': 2, 'MaxAttempts': 20})
        lam.update_function_configuration(FunctionName=NAME, Role=role['Arn'], Runtime='python3.12',
            Handler='mail_lambda.handler', Timeout=90, MemorySize=128, Environment=LAMBDA_ENV)
    except lam.exceptions.ResourceNotFoundException:
        for attempt in range(10):
            try:
                lam.create_function(FunctionName=NAME, Runtime='python3.12', Role=role['Arn'],
                    Handler='mail_lambda.handler', Code={'ZipFile': data.getvalue()}, Timeout=90, MemorySize=128,
                    Environment=LAMBDA_ENV, Description='Selection email transport via RMAED.it')
                break
            except lam.exceptions.InvalidParameterValueException:
                if attempt == 9:
                    raise
                time.sleep(2)
    rule = events.put_rule(Name=RULE, ScheduleExpression='rate(1 minute)', State='DISABLED',
        Description='Process Selection-approved emails on RMAED.it once per minute')
    arn = f'arn:aws:lambda:us-east-1:{ACCOUNT}:function:{NAME}'
    try:
        lam.add_permission(FunctionName=NAME, StatementId='selection-mail-schedule', Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com', SourceArn=rule['RuleArn'], SourceAccount=ACCOUNT)
    except lam.exceptions.ResourceConflictException:
        pass
    target = events.put_targets(Rule=RULE, Targets=[{'Id': 'selection-mail', 'Arn': arn,
        'RetryPolicy': {'MaximumRetryAttempts': 0, 'MaximumEventAgeInSeconds': 60}}])
    assert not target['FailedEntryCount']
    lam.put_function_event_invoke_config(FunctionName=NAME, MaximumRetryAttempts=0, MaximumEventAgeInSeconds=60)
    print('Selection-only worker created. Schedule remains DISABLED until the uploaded PHP endpoint is verified.')

elif mode == 'activate':
    with urlopen('https://rfone.romesflavours.com/selection/candidate/bridge/health', timeout=20) as response:
        deployed = json.loads(response.read())
    assert deployed.get('version') == 'rmaed-selection-bridge-3', 'Deploy the Selection mail API first.'
    payload = b'{"action":"health"}'
    stamp = str(int(time.time()))
    signature = hmac.new(key.encode(), stamp.encode() + b'\n' + payload, hashlib.sha256).hexdigest()
    request = Request('https://www.rmaed.it/mail-worker.php', data=payload, headers={'Content-Type': 'application/json',
        'X-RFOne-Time': stamp, 'X-RFOne-Signature': signature})
    with urlopen(request, timeout=20) as response:
        result = json.loads(response.read())
    assert result == {'ok': True, 'version': 'selection-mail-worker-1'}, 'Upload the PHP worker first.'
    events.enable_rule(Name=RULE)
    print('RMAED worker verified; Selection mail schedule ENABLED (one check per minute).')

elif mode == 'status':
    print('Schedule:', events.describe_rule(Name=RULE)['State'])
    print('Lambda:', lam.get_function_configuration(FunctionName=NAME)['State'])
