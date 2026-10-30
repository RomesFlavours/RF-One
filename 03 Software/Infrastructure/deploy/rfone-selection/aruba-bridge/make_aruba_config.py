"""Write the Aruba upload ZIP holding only config.php (SELECTION_DEPLOY_GUARD_001).

    python make_aruba_config.py <output.zip>

The relay key comes from Secrets Manager (the same secret rfone-selection and
the mail Lambda read); the SMTP credential from the local DPAPI-protected
Selection configuration. Neither is printed or written anywhere else. Upload
the ZIP's config.php to the RMAED.it root, then delete the ZIP.
"""
import base64
import json
import smtplib
import ssl
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'Selection'))
import smtp_local_config  # noqa: E402

RELAY_SECRET = 'arn:aws:secretsmanager:us-east-1:418674484214:secret:rfone-selection/rmaed-relay-key-PJxbvJ'
MAILBOX = 'romesflavourscareers@rmaed.it'

output = Path(sys.argv[1])
data = json.loads(smtp_local_config.CONFIG_FILE.read_text(encoding='utf-8'))
if data['username'].lower() != MAILBOX:
    sys.exit('SMTP_MAILBOX_DOES_NOT_MATCH')
password = smtp_local_config._dpapi(base64.b64decode(data['password_dpapi']), protect=False).decode('utf-8')
with smtplib.SMTP_SSL('smtps.aruba.it', 465, timeout=20, context=ssl.create_default_context()) as smtp:
    smtp.login(data['username'], password)
    smtp.noop()
print('SMTP_AUTHENTICATION_OK (no email sent)')
key = boto3.client('secretsmanager', region_name='us-east-1').get_secret_value(SecretId=RELAY_SECRET)['SecretString']
config = {'aws_base': 'https://rfone.romesflavours.com/selection', 'relay_key': key,
          'smtp_user': data['username'], 'smtp_password': password}
php = ("<?php\ndeclare(strict_types=1);\nif (!defined('RFONE_ENTRY')) { http_response_code(404); exit; }\n"
       "return json_decode(base64_decode('" + base64.b64encode(json.dumps(config).encode()).decode()
       + "'), true, 512, JSON_THROW_ON_ERROR);\n")
with ZipFile(output, 'w', ZIP_DEFLATED) as z:
    z.writestr('config.php', php)
print('ZIP_READY:', output)
