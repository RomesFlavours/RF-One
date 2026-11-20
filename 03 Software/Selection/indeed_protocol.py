"""Small wire contract shared by Selection and its isolated browser worker."""
import json
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

MAX_CV_BYTES = 20 * 1024 * 1024


def list_url(value):
    value = (value or '').strip()
    p = urlsplit(value)
    if (p.scheme != 'https' or p.netloc != 'employers.indeed.com'
            or p.path.rstrip('/') != '/candidates' or p.fragment
            or not (parse_qs(p.query).get('selectedJobs') or parse_qs(p.query).get('employerJobId'))):
        raise ValueError('Use the Indeed employer candidate-list URL for one job.')
    return value


def service_url(value):
    p = urlsplit(value or '')
    local = p.hostname in ('127.0.0.1', 'localhost')
    if (p.scheme != 'https' and not (local and p.scheme == 'http')) or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('Service URLs must use HTTPS (HTTP allowed only on loopback).')
    return value.rstrip('/')


def call(base, key, path, data=None, *, raw=None, headers=None, timeout=120):
    payload = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    req = Request(service_url(base) + path, data=payload,
                  headers={'Authorization': 'Bearer ' + key,
                           'Content-Type': 'application/json' if raw is None else 'application/octet-stream',
                           **(headers or {})})
    # No redirects: never forward worker credentials to another origin.
    from urllib.request import HTTPRedirectHandler, build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
        return json.load(response)
