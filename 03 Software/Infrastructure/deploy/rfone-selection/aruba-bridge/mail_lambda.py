"""Wake the authenticated RMAED transport. No candidate data is logged here.

The relay key is read once per container from Secrets Manager
(RFONE_RELAY_SECRET_ID), never from a plaintext environment value.
"""
import hashlib
import hmac
import json
import os
import time
from urllib.request import Request, urlopen

import boto3

_key = None


def relay_key():
    global _key
    if _key is None:
        _key = boto3.client('secretsmanager').get_secret_value(SecretId=os.environ['RFONE_RELAY_SECRET_ID'])['SecretString']
    return _key


def handler(event, context):
    body = b'{"action":"drain"}'
    stamp = str(int(time.time()))
    signature = hmac.new(relay_key().encode(), stamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
    request = Request('https://www.rmaed.it/mail-worker.php', data=body, method='POST', headers={
        'Content-Type': 'application/json', 'X-RFOne-Time': stamp, 'X-RFOne-Signature': signature})
    with urlopen(request, timeout=80) as response:
        result = json.loads(response.read(4096))
    if not result.get('ok'):
        raise RuntimeError('Selection email transport is unavailable.')
    return {'processed': int(result.get('processed', 0)), 'result': result.get('result', 'idle')}
