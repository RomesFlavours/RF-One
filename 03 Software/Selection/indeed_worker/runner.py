"""Only visible employer UI controls; no challenge solving or private Indeed API."""
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from indeed_protocol import MAX_CV_BYTES


class LoginRequired(Exception):
    pass


def candidate_id(url):
    p = urlsplit(url)
    value = parse_qs(p.query).get('id', [''])[0]
    if p.scheme == 'https' and p.netloc == 'employers.indeed.com' and p.path == '/candidates/view' and re.fullmatch(r'[A-Za-z0-9]{1,64}', value):
        return value
    raise ValueError('Unexpected candidate URL')


def check_access(page):
    if urlsplit(page.url).netloc != 'employers.indeed.com' or page.locator(
            'input[type=password], input[autocomplete=one-time-code], iframe[src*="captcha"]'
    ).count():
        raise LoginRequired()
    if page.get_by_text(re.compile(r'verify (you are|your identity)|verification code|security check', re.I)).count():
        raise LoginRequired()


def scan(page, url, keep_running):
    """Snapshot list pages before visiting profiles, preserving the selected job."""
    page.goto(url, wait_until='domcontentloaded')
    found, pages = {}, set()
    expected = None
    while True:
        keep_running()
        check_access(page)
        links = page.locator('a[href*="/candidates/view?"]')
        try:
            links.first.wait_for(state='attached', timeout=15000)
        except Exception:
            check_access(page)
            # An empty list must be positively shown, never inferred from timeout.
            if page.get_by_text(re.compile(r'No (applications|candidates)|Showing 0', re.I)).count():
                return found
            raise RuntimeError('Candidate list not recognized; check the browser and resume.')
        values = links.evaluate_all('(nodes) => nodes.map(n => n.href)')
        signature = tuple(values)
        if signature in pages:
            raise RuntimeError('Pagination did not advance; import paused rather than claiming completion.')
        pages.add(signature)
        for href in values:
            found[candidate_id(href)] = href
        count = re.search(r'Showing\s+[\d,]+\s*[-–]\s*[\d,]+\s+of\s+([\d,]+)', page.locator('body').inner_text())
        if count:
            expected = int(count[1].replace(',', ''))
        next_button = page.get_by_role('button', name='Next', exact=True)
        if not next_button.count():
            raise RuntimeError('Pagination control not recognized; check the browser and resume.')
        if next_button.is_disabled() or next_button.get_attribute('aria-disabled') == 'true':
            if expected is not None and len(found) != expected:
                raise RuntimeError('The list changed or some candidates were omitted; check and resume.')
            return found
        next_button.click()
        page.wait_for_function(
            '(old) => JSON.stringify(Array.from(document.querySelectorAll(\'a[href*="/candidates/view?"]\')).map(a=>a.href)) !== old',
            arg=json.dumps(values, separators=(',', ':')), timeout=20000)


def collect(page, job, store, upload, directory, keep_running):
    candidates = scan(page, job['url'], keep_running)
    store.update(job['id'], total=len(candidates), message='')
    completed = {r['candidate_id'] for r in store.get(job['id'])['items'] if r['status'] in ('OK', 'DUPLICATE', 'NO_RESUME')}
    for ident, href in candidates.items():
        keep_running()
        if ident in completed:
            continue
        try:
            page.goto(href, wait_until='domcontentloaded')
            check_access(page)
            # Wait for the actual profile; do not treat a slow page as missing CV.
            page.get_by_role('button', name='Next candidate', exact=True).wait_for(state='attached', timeout=20000)
            download_link = page.get_by_role('link', name='Download resume', exact=True)
            if not download_link.count() and page.get_by_text(re.compile(r'No resume|No résumé|Resume not (provided|available)', re.I)).count():
                store.checkpoint(job['id'], ident, 'NO_RESUME', 'Indeed explicitly reports no résumé.')
                continue
            try:
                download_link.wait_for(state='attached', timeout=15000)
            except Exception:
                check_access(page)
                if page.get_by_text(re.compile(r'No resume|No résumé|Resume not (provided|available)', re.I)).count():
                    store.checkpoint(job['id'], ident, 'NO_RESUME', 'Indeed explicitly reports no résumé.')
                    continue
                raise RuntimeError('Download control unavailable; manual verification required.')
            with page.expect_download(timeout=45000) as event:
                download_link.click(timeout=15000)
            download = event.value
            path = Path(directory) / ident
            try:
                download.save_as(path)
                if path.stat().st_size > MAX_CV_BYTES:
                    raise ValueError('Résumé exceeds the 20 MiB limit.')
                keep_running()
                result = upload(job, ident, download.suggested_filename, path.read_bytes())
                if result['status'] not in ('OK', 'DUPLICATE'):
                    raise RuntimeError('Selection could not import this résumé.')
                store.checkpoint(job['id'], ident, result['status'], str(result.get('position_candidate_id', '')))
            finally:
                path.unlink(missing_ok=True)
                download.delete()
        except LoginRequired:
            raise
        except InterruptedError:
            raise
        except Exception:
            # Don't log browser URLs, file contents or authentication values.
            check_access(page)
            store.checkpoint(job['id'], ident, 'FAILED', 'Download/import failed; resume to retry this candidate.')
    failures = [i for i in store.get(job['id'])['items'] if i['status'] == 'FAILED']
    return 'PAUSED' if failures else 'COMPLETED'
