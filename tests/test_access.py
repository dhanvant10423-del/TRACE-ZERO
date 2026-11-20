import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from access import Access,secured
from server import handler,ThreadingHTTPServer
from storage import Storage

class Work:
    def api(self,p,q):
        return {"protected":"case content"}

class GateTest(unittest.TestCase):
    def test_access_lifecycle(self):
        with tempfile.TemporaryDirectory() as root:
            store=Storage(Path(root)/"test.db")
            auth=Access(store,{u:"test-"+u for u in ("support","finance","investigator")})
            with ThreadingHTTPServer(("127.0.0.1",0),secured(handler(Work()),auth)) as server:
                th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
                def call(path,data=None,cookie=""):
                    c=http.client.HTTPConnection("127.0.0.1",server.server_port)
                    c.request("GET" if data is None else "POST",path,None if data is None else json.dumps(data),
                              {"Cookie":cookie,"X-Trace-Local":"1"})
                    r=c.getresponse();out=(r.status,r.read(),(r.getheader("Set-Cookie") or "").split(";")[0]);c.close()
                    return out
                def login(name):
                    status,_,token=call("/access/login",{"username":name,"password":"test-"+name})
                    self.assertEqual(status,200)
                    return token
                try:
                    for route in ["/api/overview","/api/exports/json","/access/statement","/workspace"]:
                        self.assertEqual(call(route)[0],401)
                    self.assertEqual(call("/access/login",{"username":"finance","password":"bad"})[0],401)
                    sup=login("support")
                    code,body,_=call("/access/statement",cookie=sup)
                    self.assertEqual(code,403);self.assertNotIn(b"24,500",body)
                    self.assertEqual(call("/access/beneficiary",{"beneficiary":"demo-south","role":"finance"},sup)[0],403)
                    self.assertEqual(call("/api/vault/upload",{},sup)[0],403)
                    fin=login("finance")
                    self.assertIn(b"North Quay",call("/access/statement",cookie=fin)[1])
                    self.assertEqual(call("/access/beneficiary",{"beneficiary":"demo-south"},fin)[0],200)
                    self.assertIn(b"South Yard",call("/access/statement",cookie=fin)[1])
                    self.assertEqual(call("/api/overview",cookie=fin)[0],403)
                    inv=login("investigator")
                    self.assertEqual(call("/api/overview",cookie=inv)[0],200)
                    self.assertEqual(call("/access/beneficiary",{"beneficiary":"demo-north"},inv)[0],403)
                    self.assertIn(b"BLOCKED",call("/access/activity",cookie=inv)[1])
                    call("/access/logout",{},fin)
                    self.assertEqual(call("/access/statement",cookie=fin)[0],401)
                finally:
                    server.shutdown();th.join()
