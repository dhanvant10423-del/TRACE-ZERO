"""SQLite storage for source uploads and the independent synthetic exercise branch."""
import hashlib
import json
import sqlite3
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

from sentinel import analyze, evaluate, event_records, record, settings_for, SCENARIOS
from vault import ADMITTED, extract, stamp

SCHEMA="""
CREATE TABLE IF NOT EXISTS original (
  id TEXT PRIMARY KEY, filename TEXT NOT NULL, file_type TEXT NOT NULL,
  uploaded_at TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
  duplicate_of TEXT REFERENCES original(id), error TEXT NOT NULL, raw BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS original_hash ON original(sha256);
CREATE TABLE IF NOT EXISTS extracted (
  source TEXT NOT NULL REFERENCES original(id), row_num INTEGER NOT NULL,
  data TEXT NOT NULL, PRIMARY KEY(source,row_num)
);
CREATE TABLE IF NOT EXISTS evidence_review (
  id INTEGER PRIMARY KEY, ref TEXT NOT NULL, time TEXT NOT NULL, note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exercise (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exercise_review (
  exercise_id TEXT PRIMARY KEY REFERENCES exercise(id), data TEXT NOT NULL
);
"""

def dump(obj):
    return json.dumps(obj,ensure_ascii=False,default=str,allow_nan=False)

def identifier(prefix):
    return prefix+uuid.uuid4().hex[:12].upper()

class Storage:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:db.executescript(SCHEMA)
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:yield db
        finally:db.close()

    def upload(self,filename,raw):
        filename=unquote(filename).replace("\\","/").split("/")[-1].strip()[:160]
        if not filename or any(ord(c)<32 for c in filename):raise ValueError("Invalid file name")
        digest=hashlib.sha256(raw).hexdigest()
        sid=identifier("U-")
        rows,error=extract(filename,raw)
        for row in rows:
            try:dump(row)
            except ValueError:row.update(raw={"value":str(row["raw"])},status="REJECTED",reason="Non-finite numeric value")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            duplicate=db.execute("SELECT id FROM original WHERE sha256=? AND duplicate_of IS NULL",(digest,)).fetchone()
            if duplicate:rows,error=[],""
            db.execute("INSERT INTO original VALUES(?,?,?,?,?,?,?,?,?)",(sid,filename,Path(filename).suffix.lower(),stamp(),
                       len(raw),digest,duplicate["id"] if duplicate else None,error,raw))
            db.executemany("INSERT INTO extracted VALUES(?,?,?)",((sid,i,dump(r)) for i,r in enumerate(rows)))
        return self.source(sid)

    def inventory(self):
        with self.db() as db:
            ids=[r["id"] for r in db.execute("SELECT id FROM original ORDER BY uploaded_at DESC,id")]
            return [self.source(s,db) for s in ids]

    def source(self,sid,connection=None):
        if connection is None:
            with self.db() as db:return self.source(sid,db)
        meta=connection.execute("SELECT id,filename,file_type,uploaded_at,size,sha256,duplicate_of,error FROM original WHERE id=?",(sid,)).fetchone()
        if not meta:raise KeyError("Upload unavailable")
        rows=self.rows(sid,connection)
        counts=dict(Counter(r["status"] for r in rows))
        state="DUPLICATE" if meta["duplicate_of"] else "PARTIAL" if meta["error"] and rows else "REJECTED" if meta["error"] else "INDEXED"
        return dict(meta)|dict(counts=counts,state=state,indexed=len(rows),origin="UPLOADED")

    def rows(self,sid,connection=None):
        if connection is None:
            with self.db() as db:return self.rows(sid,db)
        out=[]
        for row in connection.execute("SELECT data FROM extracted WHERE source=? ORDER BY row_num",(sid,)):
            value=json.loads(row["data"])
            out.append(value|{"ref":sid+"/"+value["locator"],"sid":sid,"origin":"UPLOADED"})
        return out

    def original(self,sid):
        with self.db() as db:r=db.execute("SELECT raw,sha256 FROM original WHERE id=?",(sid,)).fetchone()
        if not r:raise KeyError("Upload unavailable")
        return r["raw"],hashlib.sha256(r["raw"]).hexdigest()==r["sha256"]

    def review_upload(self,ref,note):
        sid,_,locator=ref.partition("/")
        if not any(r["locator"]==locator for r in self.rows(sid)):raise KeyError("Unknown upload record")
        note=clean_note(note)
        with self.db() as db:db.execute("INSERT INTO evidence_review(ref,time,note) VALUES(?,?,?)",(ref,stamp(),note))
        return self.upload_reviews(ref)

    def upload_reviews(self,ref):
        with self.db() as db:return [dict(r) for r in db.execute("SELECT time,note FROM evidence_review WHERE ref=? ORDER BY id",(ref,))]

    def run(self,body):
        scenario,settings=settings_for(body)
        rid=identifier("SIM-")
        entry=self.simulation_entry(rid,scenario,settings,stamp())
        with self.db() as db:db.execute("INSERT INTO exercise VALUES(?,?,?)",(rid,entry["created_at"],dump(entry)))
        return self.exercise(rid)

    @staticmethod
    def simulation_entry(rid,scenario,settings,now):
        result=evaluate(settings)
        return dict(id=rid,label=SCENARIOS[scenario][0],origin="SYNTHETIC",created_at=now,
                    edited=settings!=settings_for({"scenario":scenario})[1],settings=settings,
                    result=result,events=event_records(rid,now,settings,result))

    def load_demo(self):
        demos={"SIM-DEMO-DENIED":"denied_bank","SIM-DEMO-TRAVEL":"travel","SIM-DEMO-SCOPE":"excess_scope",
               "SIM-DEMO-VENDOR":"denied_vendor","SIM-DEMO-ADMIN":"admin_review"}
        with self.db() as db:
            for i,(rid,scenario) in enumerate(demos.items()):
                _,settings=settings_for({"scenario":scenario})
                now=f"2026-01-15T10:{i:02d}:00+00:00"
                entry=self.simulation_entry(rid,scenario,settings,now)
                db.execute("INSERT OR IGNORE INTO exercise VALUES(?,?,?)",(rid,now,dump(entry)))
        return self.exercise("SIM-DEMO-DENIED")

    def exercises(self):
        with self.db() as db:entries=[json.loads(r["data"]) for r in db.execute("SELECT data FROM exercise ORDER BY created_at DESC,rowid DESC")]
        return [dict(id=r["id"],label=r["label"],decision=r["result"]["decision"],created_at=r["created_at"]) for r in entries]

    def exercise(self,rid,excluded=()):
        with self.db() as db:
            row=db.execute("SELECT data FROM exercise WHERE id=?",(rid,)).fetchone()
            review=db.execute("SELECT data FROM exercise_review WHERE exercise_id=?",(rid,)).fetchone()
        if not row:raise KeyError("Unknown simulation run")
        entry=json.loads(row["data"])
        if review:
            entry["review"]=json.loads(review["data"])
            entry["events"].append(entry["review"]["event"])
        if set(excluded)-{r["ref"] for r in entry["events"]}:raise ValueError("Unknown simulation evidence reference")
        baseline=analyze(entry["events"],())
        result=analyze(entry["events"],excluded)
        original={r["id"]:r for r in baseline["relationships"]}
        current={r["id"]:r for r in result["relationships"]}
        return entry|dict(baseline=baseline,analysis=result,diff=dict(
            withdrawn=[v for k,v in original.items() if k not in current],
            retained=[v for k,v in current.items() if k in original]))

    def review_exercise(self,rid,body):
        entry=self.exercise(rid)
        if entry.get("review"):raise ValueError("This run has already been reviewed")
        if entry["result"]["decision"]=="ALLOW":raise ValueError("This run does not require a review")
        note=clean_note(body.get("note"))
        outcome=body.get("outcome")
        if outcome not in ("verified","held"):raise ValueError("Choose a review outcome")
        if outcome=="verified" and (entry["result"]["decision"]!="VERIFY" or not entry["result"]["authorized"]):
            raise ValueError("Restricted requests stay on hold. Renew authorization in a new simulation.")
        now=max(datetime.now(timezone.utc),datetime.fromisoformat(entry["events"][-1]["utc"])+timedelta(milliseconds=1))
        result="ALLOW AND MONITOR" if outcome=="verified" else "HOLD FOR AUTHORIZED REVIEW"
        review=record(rid,"05",now,"reviewer-demo","REVIEW","Record human review",
                      entry["events"][-1]["target"],{"outcome":result,"note":note})
        try:
            with self.db() as db:db.execute("INSERT INTO exercise_review VALUES(?,?)",(rid,dump({"event":review,"decision":result})))
        except sqlite3.IntegrityError:raise ValueError("This run has already been reviewed") from None
        return self.exercise(rid)

def clean_note(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=500:raise ValueError("Enter a review note of 1 to 500 characters")
    return value.strip()
