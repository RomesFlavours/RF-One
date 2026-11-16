"""Read-only HTTP verification of a published Selection release (fix A6, replaces the unversioned verify-http.py).

It never reads, prints or exports a secret and never builds or signs a session: authenticated pages are opened
by signing in through the normal RF-One login form with an authorized TEST account whose credentials the
operator supplies for this run only (RFONE_VERIFY_USERNAME / RFONE_VERIFY_PASSWORD, never stored).  Without
them, the authenticated checks are reported as NOT VERIFIED, never as passed.  Only GET requests are sent after
login: no rule is saved, no AI call, no candidate action or message.

    python verify_http_release.py --base https://rfone.romesflavours.com --pdl 7 --output http-verification.json
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests

PAGES = ['/selection/', '/selection/requisiti-priorita', '/selection/configurazioni',
         '/selection/posizioni/{pdl}', '/selection/posizioni/{pdl}/interviews', '/selection/posizioni/{pdl}/sp/upload?modal=1']
USER_AGENT = 'RFOne-Selection-Release-Verification/2.0'


def sign_in(session, base, username, password):
    """Normal RF-One login; returns True only when the shared session is really established."""
    page = session.get(base + '/login', timeout=60)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    if page.status_code != 200 or not token:
        return False
    response = session.post(base + '/login', data={'csrf_token': token.group(1), 'username': username,
                                                   'password': password, 'next': '/selection/'}, timeout=60)
    return response.status_code == 200 and urlsplit(response.url).path.startswith('/selection')


def verify(base, pdl, username=None, password=None, http=requests):
    report = {'base': base, 'secrets_read': False, 'session_signed_locally': False, 'writes_sent': False}
    anonymous = http.get(base + '/selection/', timeout=90, allow_redirects=False)
    report['anonymous_requires_login'] = anonymous.status_code == 302 and '/login' in anonymous.headers.get('Location', '')
    if not (username and password):
        report['authenticated'] = 'NOT VERIFIED: no authorized test account supplied'
        report['status'] = 'partial' if report['anonymous_requires_login'] else 'failed'
        return report
    session = http.Session()
    session.headers.update({'Cache-Control': 'no-cache', 'User-Agent': USER_AGENT})
    if not sign_in(session, base, username, password):
        report['authenticated'] = 'FAILED: the test account could not sign in or may not enter Selection'
        report['status'] = 'failed'
        return report
    checks = []
    for path in (p.format(pdl=pdl) for p in PAGES):
        response = session.get(base + path, timeout=120)
        checks.append({'path': path, 'status': response.status_code,
                       'authenticated': '/login' not in urlsplit(response.url).path, 'bytes': len(response.content)})
    report['checks'] = checks
    report['authenticated'] = 'passed' if all(c['status'] == 200 and c['authenticated'] for c in checks) else 'FAILED'
    report['status'] = 'passed' if report['anonymous_requires_login'] and report['authenticated'] == 'passed' else 'failed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', required=True)
    parser.add_argument('--pdl', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.base.rstrip('/'), args.pdl, os.environ.get('RFONE_VERIFY_USERNAME'),
                    os.environ.get('RFONE_VERIFY_PASSWORD'))
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}))
    sys.exit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
