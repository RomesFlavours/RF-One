"""Real loopback WebSocket/TCP transport, using synthetic VNC bytes only."""
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import websocket
from werkzeug.serving import make_server
from itsdangerous import URLSafeTimedSerializer
from indeed_worker.service import create_app
from indeed_worker.store import Store


class ViewerTests(unittest.TestCase):
    def test_socket_roundtrip_origin_revocation_and_ticket_expiry(self):
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as vnc:
            vnc.bind(('127.0.0.1', 0))
            vnc.listen(1)
            received = []
            def fake_vnc():
                peer, _ = vnc.accept()
                with peer:
                    peer.settimeout(5)
                    peer.sendall(b'RFB 003.008\n')
                    received.append(peer.recv(100))
                    peer.sendall(b'synthetic-frame')
                    while peer.recv(100):
                        pass
            transport = threading.Thread(target=fake_vnc, daemon=True)
            transport.start()
            # Reserve a loopback HTTP listener; set the public origin before
            # requests run, using Werkzeug's selected ephemeral port.
            key = 'synthetic-' + 'x' * 40
            with patch.dict(os.environ, RFONE_INDEED_KEY=key,
                            RFONE_INDEED_PUBLIC_URL='http://127.0.0.1',
                            RFONE_INDEED_SELECTION_URL='https://selection.example.test'):
                store = Store(Path(tmp) / 'jobs.sqlite')
                app = create_app(store=store, launch=False, vnc_address=vnc.getsockname())
                # Recreate after binding to know the exact Origin.
                server = make_server('127.0.0.1', 0, app, threaded=True)
                origin = f'http://127.0.0.1:{server.server_port}'
                os.environ['RFONE_INDEED_PUBLIC_URL'] = origin
                app = create_app(store=store, launch=False, vnc_address=vnc.getsockname())
                server.app = app
                serving = threading.Thread(target=server.serve_forever, daemon=True)
                serving.start()
                try:
                    job = store.create('https://employers.indeed.com/candidates?selectedJobs=synthetic', 1, 1)
                    store.update(job['id'], state='WAITING_LOGIN')
                    signer = URLSafeTimedSerializer(key, salt='indeed-remote-browser')
                    ticket = signer.dumps({'id': job['id'], 'generation': job['generation']})
                    cookie = 'indeed_viewer=' + ticket
                    with self.assertRaises(websocket.WebSocketBadStatusException):
                        websocket.create_connection(origin.replace('http:', 'ws:') + '/websockify', origin=origin, timeout=3)
                    wrong = websocket.create_connection(origin.replace('http:', 'ws:') + '/websockify',
                                                        origin='https://evil.example.test', cookie=cookie, timeout=3)
                    self.assertEqual(wrong.recv(), '')
                    wrong.close()
                    ws = websocket.create_connection(origin.replace('http:', 'ws:') + '/websockify', origin=origin, cookie=cookie, timeout=3)
                    self.assertEqual(ws.recv(), b'RFB 003.008\n')
                    ws.send_binary(b'synthetic-input')
                    self.assertEqual(ws.recv(), b'synthetic-frame')
                    self.assertEqual(received, [b'synthetic-input'])
                    store.update(job['id'], state='RUNNING')
                    self.assertEqual(ws.recv(), '')
                    ws.close()
                    store.update(job['id'], state='WAITING_LOGIN')
                    client = app.test_client()
                    future = time.time() + 1801
                    with patch('itsdangerous.timed.time.time', return_value=future):
                        self.assertEqual(client.get('/open?ticket=' + ticket).status_code, 403)
                finally:
                    server.shutdown()
                    server.server_close()
                    serving.join(timeout=3)
                    transport.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
