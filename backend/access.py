"""Loopback authentication and role enforcement for the synthetic finance desk."""
import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ROLES = ("support", "finance", "investigator")
PAYEES = {"demo-north": "North Quay Logistics", "demo-south": "South Yard Freight"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_payment (
 id INTEGER PRIMARY KEY CHECK(id=1), payee TEXT NOT NULL);
INSERT OR IGNORE INTO demo_payment VALUES (1,'demo-north');
CREATE TABLE IF NOT EXISTS access_log (
 id INTEGER PRIMARY KEY, utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actor TEXT NOT NULL, operation TEXT NOT NULL, decision TEXT NOT NULL, detail TEXT NOT NULL);
"""

class Access:
    def __init__(self, storage, passwords):
        self.storage = storage
        self.keys = {u:hashlib.sha256(v.encode()).digest() for u,v in passwords.items()}
        self.sessions = {}
        self.failed = deque()
        self.lock = Lock()
        with storage.db() as db:
            db.executescript(SCHEMA)

    def audit(self, user, op, status, detail):
        with self.storage.db() as db:
            self.log(db,user,op,status,detail)

    @staticmethod
    def log(db,user,op,status,detail):
        db.execute("INSERT INTO access_log(actor,operation,decision,detail) VALUES (?,?,?,?)",
                   (user,op,status,detail))

    def login(self, name, password):
        with self.lock:
            now=time.monotonic()
            while self.failed and self.failed[0]<now-30:
                self.failed.popleft()
            if len(self.failed)>=8:
                return 429,None
            if not hmac.compare_digest(self.keys.get(name,bytes(32)), hashlib.sha256(password.encode()).digest()):
                self.failed.append(now)
                return 401,None
            self.sessions={k:v for k,v in self.sessions.items() if v[1]>now}
            token=secrets.token_urlsafe(32)
            self.sessions[token]=(name,now+1800)
            return 200,token

    def actor(self, token):
        with self.lock:
            name,expiry=self.sessions.get(token,(None,0))
            if expiry<=time.monotonic():
                self.sessions.pop(token,None)
                return None
            return name

def secured(base, access):
    class Desk(base):
        cookie_out=None
        def end_headers(self):
            if self.cookie_out:
                self.send_header("Set-Cookie",self.cookie_out)
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Referrer-Policy","no-referrer")
            super().end_headers()

        def token(self):
            jar=SimpleCookie()
            try:jar.load(self.headers.get("Cookie",""))
            except CookieError:return ""
            return jar["trace_session"].value if "trace_session" in jar else ""

        def cookie(self,value,age):
            self.cookie_out=f"trace_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}"

        def deny(self,user,op,status,reason):
            access.audit(user or "guest",op,"BLOCKED",reason)
            self.send_json({"decision":"BLOCKED","error":reason},status)

        def guard(self,post=False):
            host=self.headers.get("Host","")
            allowed={f"{name}:{self.server.server_port}" for name in ("localhost","127.0.0.1")}
            if host not in allowed or (post and (self.headers.get("X-Trace-Local")!="1" or
                    self.headers.get("Origin",f"http://{host}")!=f"http://{host}")):
                self.send_json({"error":"Local, same-origin request required."},403)
                return False
            return True

        def body(self):
            n=int(self.headers.get("Content-Length",0))
            if not 0<n<=4096:raise ValueError()
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict):raise ValueError()
            return data

        def do_GET(self):
            if not self.guard():return
            path=urlsplit(self.path).path
            if path in ("/","/desk.js","/desk.css"):
                name,mime={"/":("desk.html","text/html"),"/desk.js":("desk.js","text/javascript"),
                           "/desk.css":("desk.css","text/css")}[path]
                return self.respond((FRONTEND/name).read_bytes(),mime)
            user=access.actor(self.token())
            if path=="/access/session":return self.send_json({"user":user})
            if not user:return self.deny(user,"Protected access",401,"Sign in to open this resource.")
            if path=="/access/activity":
                with access.storage.db() as db:
                    query="SELECT * FROM access_log "
                    rows=db.execute(query+"ORDER BY id DESC LIMIT 25") if user=="investigator" else db.execute(
                        query+"WHERE actor=? ORDER BY id DESC LIMIT 25",(user,))
                    return self.send_json([dict(r) for r in rows])
            if path=="/access/statement":
                if user!="finance":return self.deny(user,"Read statement",403,"Finance permission is required. No statement was released.")
                with access.storage.db() as db:
                    payee=db.execute("SELECT payee FROM demo_payment WHERE id=1").fetchone()[0]
                    access.log(db,user,"Read statement","ALLOWED","Released demo statement DEMO-104.")
                return self.send_json({"decision":"ALLOWED","statement":"DEMO-104","amount":"INR 24,500","beneficiary":PAYEES[payee]})
            if user!="investigator":return self.deny(user,"Open case workspace",403,"Investigator permission is required. Case data was withheld.")
            if path=="/workspace":self.path="/"
            return super().do_GET()

        def do_POST(self):
            if not self.guard(post=True):return
            path=urlsplit(self.path).path
            token=self.token()
            user=access.actor(token)
            try:
                if path=="/access/login":
                    data=self.body()
                    name=data.get("username")
                    pw=data.get("password")
                    if not isinstance(name,str) or not isinstance(pw,str):raise ValueError()
                    status,new=access.login(name,pw)
                    if not new:return self.deny("guest","Sign in",status,"Try again in 30 seconds." if status==429 else "Sign-in denied. Check your username and password.")
                    with access.lock:access.sessions.pop(token,None)
                    self.cookie(new,1800)
                    access.audit(name,"Sign in","ALLOWED","Password accepted. Session valid for 30 minutes.")
                    return self.send_json({"user":name})
                if not user:return self.deny(None,"Protected action",401,"Sign in to request this operation.")
                if path=="/access/logout":
                    with access.lock:access.sessions.pop(token,None)
                    self.cookie("",0)
                    return self.send_json({"signed_out":True})
                if path=="/access/beneficiary":
                    if user!="finance":return self.deny(user,"Change beneficiary",403,"Finance permission is required. The beneficiary was preserved.")
                    payee=self.body().get("beneficiary")
                    if payee not in PAYEES:raise ValueError()
                    with access.storage.db() as db:
                        db.execute("UPDATE demo_payment SET payee=? WHERE id=1",(payee,))
                        access.log(db,user,"Change beneficiary","ALLOWED","Saved "+PAYEES[payee]+".")
                    return self.send_json({"decision":"ALLOWED","beneficiary":PAYEES[payee]})
                if user!="investigator":return self.deny(user,"Modify investigation",403,"Investigator permission is required.")
                return super().do_POST()
            except (ValueError,TypeError,UnicodeError):
                self.send_json({"error":"Invalid request fields."},400)
    return Desk
