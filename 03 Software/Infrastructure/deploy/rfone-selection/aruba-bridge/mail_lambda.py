"""Wake the authenticated RMAED transport. No candidate data is logged here."""
import hashlib
import hmac
import json
import os
import time
from urllib.request import Request, urlopen


def handler(event, context):
    body = b'{"action":"drain"}'
    stamp = str(int(time.time()))
    signature = hmac.new(os.environ['RFONE_RELAY_KEY'].encode(), stamp.encode() + b'\n' + body,
                         hashlib.sha256).hexdigest()
    request = Request('https://www.rmaed.it/mail-worker.php', data=body, method='POST', headers={
        'Content-Type': 'application/json', 'X-RFOne-Time': stamp, 'X-RFOne-Signature': signature})
    with urlopen(request, timeout=80) as response:
        result = json.loads(response.read(4096))
    if not result.get('ok'):
        raise RuntimeError('Selection email transport is unavailable.')
    return {'processed': int(result.get('processed', 0)), 'result': result.get('result', 'idle')}
