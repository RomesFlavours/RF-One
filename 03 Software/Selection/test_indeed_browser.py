"""Offline browser acceptance: synthetic Indeed pages served entirely by routing.

Requires Playwright and its Chromium (or RFONE_TEST_BROWSER_EXECUTABLE).
No real browser profile, Indeed account, AWS data or network requests are used.
"""
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright
from indeed_worker.runner import LoginRequired, collect, scan
from indeed_worker.store import Store

URL = 'https://employers.indeed.com/candidates?selectedJobs=synthetic'


class BrowserTests(unittest.TestCase):
    def test_paginated_downloads_missing_cv_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.getenv('RFONE_TEST_BROWSER_EXECUTABLE') or None)
            context = browser.new_context(accept_downloads=True)
            visited = []
            def fixture(route):
                p = urlsplit(route.request.url)
                query = parse_qs(p.query)
                if p.netloc != 'employers.indeed.com':
                    return route.abort()
                if p.path == '/candidates':
                    second = query.get('page') == ['2']
                    ids = ['ccc', 'ddd'] if second else ['aaa', 'bbb']
                    body = ''.join(f'<a href="/candidates/view?id={i}">{i}</a>' for i in ids)
                    body += '<p>Showing ' + ('3-4' if second else '1-2') + ' of 4</p>'
                    body += '<button disabled>Next</button>' if second else '<button onclick="location.href=\'/candidates?selectedJobs=synthetic&page=2\'">Next</button>'
                else:
                    ident = query['id'][0]
                    visited.append(ident)
                    body = '<button>Next candidate</button>'
                    if ident == 'bbb':
                        body += '<p>No resume available</p>'
                    else:
                        body += f'''<a id="download" download="{ident}.txt">Download resume</a>
                          <script>document.getElementById('download').href = URL.createObjectURL(
                            new Blob(['Synthetic resume {ident}'], {{type:'text/plain'}}));</script>'''
                route.fulfill(status=200, content_type='text/html', body=body)
            context.route('**/*', fixture)
            page = context.new_page()
            store = Store(Path(tmp) / 'ledger.sqlite')
            job = store.create(URL, 123, 456)
            store.update(job['id'], state='RUNNING')
            attempts = []
            fail_once = [True]
            def upload(job, ident, filename, data):
                self.assertEqual(job['position_id'], 123)
                self.assertEqual(filename, ident + '.txt')
                self.assertEqual(data, ('Synthetic resume ' + ident).encode())
                attempts.append(ident)
                if ident == 'ccc' and fail_once[0]:
                    fail_once[0] = False
                    raise RuntimeError('Synthetic callback outage')
                return {'status': 'OK', 'position_candidate_id': 100}
            self.assertEqual(collect(page, job, store, upload, tmp, lambda: None), 'PAUSED')
            self.assertEqual(visited, ['aaa', 'bbb', 'ccc', 'ddd'])
            self.assertEqual([i['status'] for i in store.get(job['id'])['items']], ['OK', 'NO_RESUME', 'FAILED', 'OK'])
            visited.clear()
            self.assertEqual(collect(page, job, store, upload, tmp, lambda: None), 'COMPLETED')
            self.assertEqual(visited, ['ccc'])
            self.assertEqual(attempts, ['aaa', 'ccc', 'ddd', 'ccc'])
            self.assertFalse(any((Path(tmp) / ident).exists() for ident in ('aaa', 'ccc', 'ddd')))
            browser.close()

    def test_login_pauses_without_scanning(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.getenv('RFONE_TEST_BROWSER_EXECUTABLE') or None)
            context = browser.new_context()
            context.route('**/*', lambda route: route.fulfill(body='<input type="password">', content_type='text/html'))
            page = context.new_page()
            with self.assertRaises(LoginRequired):
                scan(page, URL, lambda: None)
            browser.close()


if __name__ == '__main__':
    unittest.main()
