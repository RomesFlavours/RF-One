import unittest, tempfile, pathlib, json, threading, urllib.request, urllib.error
import server

class Flow(unittest.TestCase):
    def test_full_flow_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            server.DB=pathlib.Path(tmp)/'test.sqlite3'
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            base='http://127.0.0.1:'+str(http.server_port)
            def state(): return json.load(urllib.request.urlopen(base+'/api/state'))
            def act(role,action,key,**kw):
                body=json.dumps(dict(role=role,action=action,requestId=key,**kw)).encode()
                return json.load(urllib.request.urlopen(urllib.request.Request(base+'/api/action',body,{'Content-Type':'application/json'})))
            try:
                with self.assertRaises(urllib.error.HTTPError): act('staff','request','bad')
                for q in [0,-2,1.2,81]:
                    with self.assertRaises(urllib.error.HTTPError): act('staff','break',str(q),qty=q)
                act('staff','break','break1',qty=22)
                act('staff','break','break1',qty=22)
                self.assertEqual(state()['state']['stock']['wp']['available'],58)
                self.assertEqual(state()['proposal'],62)
                act('foh','request','request1')
                c=state()['state']['cases'][0]
                self.assertEqual(c['version'],'0.3')
                self.assertEqual(state()['state']['stock']['md']['available'],400)
                with self.assertRaises(urllib.error.HTTPError): act('foh','receive','early',caseId=c['id'])
                for action in ['accept','ship','receive']:
                    role='foh' if action=='receive' else 'md'
                    act(role,action,action,caseId=c['id'])
                    act(role,action,action+'repeat',caseId=c['id'])
                    s=state()['state']
                    self.assertEqual(s['stock']['md']['available'],338)
                    self.assertEqual(s['stock']['md']['reserved'],62 if action=='accept' else 0)
                    self.assertEqual(s['transit'],62 if action=='ship' else 0)
                s=state()['state']
                self.assertEqual(s['stock']['wp']['available'],120)
                self.assertEqual(s['cases'][0]['status'],'received')
                self.assertEqual(len(s['intercompany']),1)
                self.assertEqual(s['intercompany'][0]['value'],248)
                act('control','review','review',caseId=c['id'])
                act('control','review','review2',caseId=c['id'])
                self.assertEqual(state()['state']['cases'][0]['status'],'closed')
                self.assertEqual(len(state()['state']['movements']),5)
                # Close/reopen database: durable state, not process memory.
                with server.connect() as db:
                    stored=json.loads(db.execute('SELECT data FROM state').fetchone()[0])
                    self.assertEqual(stored['stock']['wp']['available'],120)
                    self.assertEqual(len(stored['intercompany']),1)
                req=urllib.request.Request(base+'/api/reset',b'{}',{'Content-Type':'application/json'})
                urllib.request.urlopen(req).close()
                self.assertEqual(state()['state']['stock']['wp']['available'],80)
                self.assertEqual(len(state()['state']['cases']),0)
            finally: http.shutdown();http.server_close()
if __name__=='__main__': unittest.main()
