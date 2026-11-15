"""Loopback-only, in-memory S3 HTTP fixture. No AWS client or credentials."""
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

OBJECTS = {}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_PUT(self):
        data = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        with LOCK:
            OBJECTS[urlsplit(self.path).path] = data
        self.send_response(200)
        self.send_header('ETag', '"' + hashlib.md5(data).hexdigest() + '"')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_HEAD(self):
        with LOCK:
            data = OBJECTS.get(urlsplit(self.path).path)
        self.send_response(200 if data is not None else 404)
        self.send_header('Content-Length', str(len(data) if data is not None else 0))
        self.end_headers()

    def do_GET(self):
        with LOCK:
            data = OBJECTS.get(urlsplit(self.path).path)
        if data is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 55123), Handler).serve_forever()
