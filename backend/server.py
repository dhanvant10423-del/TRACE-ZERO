"""Local investigator workbench. Run from any working directory."""
import argparse
import functools
import json
import os
import threading
import webbrowser
import secrets
from access import Access, ROLES, secured
from collections import Counter
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

from ingest import BASE, Case
from entities import EntityIndex
from reasoning import RULES,context_lookup,run,evaluate_status
from sentinel import ACTIONS, IDENTITIES, benchmark, catalog
from storage import Storage
from vault import MAX_BYTES, ADMITTED
from reporting import build_report, evidence_csv, pdf

ROOT=BASE.parent

def lineage(case,fact):
    nodes={}
    edges=[]
    def node(id,kind,label):
        nodes[id]={"id":id,"type":kind,"label":label}
        return id
    def edge(a,b,label,status,refs):
        status_names={"recorded":"VERIFIED","inference":"INFERRED","candidate":"CANDIDATE","unresolved":"UNRESOLVED"}
        edges.append({"id":f"{a}>{b}","from":a,"to":b,"label":label,"status":status_names.get(status,status),
                      "method":status,"rule":fact["rule"],"refs":refs,
                      "explanation":"This reference supplies the recorded field." if status=="recorded" else fact["summary"]})
    fid=node(fact["id"],"assessment",fact["rule"])
    for ref in fact["refs"]:
        r=case.by_id[ref]
        e=node(ref,"evidence",ref)
        obs=node("obs:"+ref,"observation",r.action or r.label)
        edge(e,obs,"records","recorded",[ref])
        edge(obs,fid,"input",fact["kind"],[ref])
    if fact["entity"]:
        ent=node("subject:"+fact["entity"],"entity",fact["entity"])
        edge(fid,ent,"concerns",fact["kind"],fact["refs"])
    for h,effect in fact["effects"].items():
        edge(fid,node(h,"hypothesis",h),effect,fact["kind"],fact["refs"])
    return {"nodes":list(nodes.values()),"edges":edges}

def scoped(result,scopes):
    if not scopes:return result
    facts=[f|{"effects":{h:tag for h,tag in f["effects"].items() if h not in scopes or f["rule"] in scopes[h]}}
           for f in result["facts"]]
    hypotheses={}
    for h,meta in result["hypotheses"].items():
        effects=[f["effects"][h] for f in facts if h in f["effects"]]
        enabled=scopes.get(h)
        hypotheses[h]=meta|{"status":evaluate_status(effects,enabled!=[] and meta["status"]!="NOT EVALUATED"),
                            "counts":{k:effects.count(k) for k in meta["counts"]},"enabled_rules":enabled}
    return result|dict(facts=facts,hypotheses=hypotheses)

class Workbench:
    def __init__(self,case,storage=None):
        self.case=case
        self.storage=storage
        self.entities=EntityIndex(case)
        self.baseline=run(case)
        self.scenario=functools.lru_cache(maxsize=16)(lambda ids:run(case,ids) if ids else self.baseline)
        self.context=functools.lru_cache(maxsize=512)(lambda ref,ids:context_lookup(case,ref,ids))

    def api(self,path,q):
        arg=lambda k,default="":q.get(k,[default])[0]
        ids=tuple(sorted(set(filter(None,arg("exclude").split(",")))))
        if any(k not in self.case.sources and k not in self.case.by_id for k in ids):raise ValueError("Unknown challenge target")
        case=self.case
        result=self.scenario(ids)
        restrictions=arg("hyp_rules")
        scopes=json.loads(restrictions) if restrictions else {}
        if not isinstance(scopes,dict) or any(
            h not in self.baseline["hypotheses"] or not isinstance(rules,list) or any(not isinstance(r,str) or r not in RULES for r in rules)
            for h,rules in scopes.items()
        ):raise ValueError("Invalid hypothesis rule scope")
        baseline=scoped(self.baseline,scopes)
        result=scoped(result,scopes)
        if path.startswith(("/api/sentinel/","/api/vault/","/api/exports/")):
            return self.extensions(path,arg,q)
        if path=="/api/overview":
            before={f["id"]:f for f in baseline["facts"]}
            after={f["id"]:f for f in result["facts"]}
            diff={"lost":[before[k] for k in before if k not in after],
                  "added":[after[k] for k in after if k not in before],
                  "changed":[after[k] for k in after if k in before and after[k]!=before[k]],
                  "surviving":sum(f==before.get(k) for k,f in after.items()),
                  "baseline":baseline["hypotheses"]}
            return {**result,"sources":case.sources,"diff":diff,"rules":RULES,"records":len(case.by_id)}
        if path=="/api/graph":
            fact=next((f for f in result["facts"] if f["id"]==arg("id")),None)
            if not fact:raise KeyError("Assessment unavailable in this scenario")
            return lineage(case,fact)
        if path=="/api/record":
            r=case.by_id[arg("ref")]
            return {**asdict(r),"excluded":r.ref in ids or r.sid in ids,"context":self.context(r.ref,ids),"entities":self.entities.neighbors(r,ids)}
        if path=="/api/records":
            timeline=arg("timeline")=="1"
            rows=case.timeline if timeline else case.by_id.values()
            sid,quality,needle=arg("source"),arg("quality"),arg("q").casefold().strip()
            type_,entity,start,end=arg("event_type"),arg("entity").casefold(),arg("start"),arg("end")
            relation=arg("relationship","observed")
            related={ref for f in result["facts"] if f["kind"]==relation for ref in f["refs"]} if relation not in ("observed","all","verified") else None
            relations={}
            if timeline:
                for fact in result["facts"]:
                    for ref in fact["refs"]:relations.setdefault(ref,set()).add(fact["kind"])
            offset=max(0,int(arg("offset","0")))
            found=[]
            count=0
            for r in rows:
                if timeline and (r.sid in ids or r.ref in ids or not r.usable):continue
                if sid and r.sid!=sid or quality and r.quality!=quality:continue
                if type_ and r.label!=type_:continue
                if entity and not any(entity in str(v).casefold() for v in (r.actor or "",r.target or "")):continue
                if start and (not r.utc or r.utc[:10]<start) or end and (not r.utc or r.utc[:10]>end):continue
                if relation=="verified" and not r.usable:continue
                if related is not None and r.ref not in related:continue
                if needle and not any(needle in str(v).casefold() for v in (r.ref,*r.raw.values())):continue
                if offset<=count<offset+40:
                    found.append({k:getattr(r,k) for k in ("ref","sid","label","actor","target","action","utc","quality","clock")}
                                 | {"relations":sorted(relations.get(r.ref,()))})
                count+=1
            return {"total":count,"rows":found,
                    "types":sorted({r.label for r in case.by_id.values()})}
        if path=="/api/report":
            return {"case":"CR-26-047","sources":case.sources,**result,"rules":RULES,
                    "limits":["Interpretations apply to their cited event sets.","Raw record locators and original time bases are retained.","Attribution, fund movement and historical scope require additional records."]}
        raise KeyError("Unknown endpoint")

    def extensions(self,path,arg,q):
        store=self.storage
        if not store:raise KeyError("Local storage is not enabled")
        if path=="/api/sentinel/catalog":
            return dict(scenarios=catalog(),identities=IDENTITIES,actions=ACTIONS,benchmark=benchmark())
        if path=="/api/sentinel/runs":return store.exercises()
        if path=="/api/sentinel/run":
            return store.exercise(arg("id"),tuple(filter(None,arg("sim_exclude").split(","))))
        if path=="/api/vault/inventory":return store.inventory()
        if path=="/api/vault/source":return store.source(arg("id"))
        if path=="/api/vault/rows":
            rows=store.rows(arg("id"))
            needle=arg("query").casefold()
            status,type_,start,end=arg("status"),arg("type"),arg("start"),arg("end")
            offset=max(int(arg("offset","0")),0)
            rows=[r for r in rows if (not status or r["status"]==status) and (not type_ or r["type"]==type_)
                  and (not needle or needle in json.dumps(r,ensure_ascii=False).casefold())
                  and (not start or r["utc"] and r["utc"][:10]>=start)
                  and (not end or r["utc"] and r["utc"][:10]<=end)]
            if arg("timeline")=="1":
                rows=sorted((r for r in rows if r["status"] in ADMITTED and r["utc"]),key=lambda r:r["utc"])
            return dict(rows=rows[offset:offset+40],total=len(rows))
        if path=="/api/vault/record":
            ref=arg("ref")
            sid,_,loc=ref.partition("/")
            row=next((r for r in store.rows(sid) if r["locator"]==loc),None)
            if not row:raise KeyError("Unknown upload record")
            return row|dict(reviews=store.upload_reviews(ref))
        if path=="/api/vault/original":
            raw,valid=store.original(arg("id"))
            if not valid:raise ValueError("Original failed its integrity check")
            return raw,"application/octet-stream",arg("id")+".bin"
        if path=="/api/vault/integrity":
            return dict(valid=store.original(arg("id"))[1])
        if path.startswith("/api/exports/"):
            sim=store.exercise(arg("run"),tuple(filter(None,arg("sim_exclude").split(",")))) if arg("run") else None
            inventory=store.inventory()
            if path.endswith("/csv"):
                rows=(r for source in inventory for r in store.rows(source["id"]))
                return evidence_csv(self.case,rows,sim),"text/csv","TRACE_ZERO_evidence.csv"
            report=build_report(self.case,self.api("/api/overview",q),inventory,sim)
            if path.endswith("/pdf"):return pdf(report),"application/pdf","TRACE_ZERO_report.pdf"
            if path.endswith("/json"):
                return json.dumps(report,ensure_ascii=False).encode(),"application/json","TRACE_ZERO_report.json"
        raise KeyError("Unknown endpoint")

def handler(work):
    resources={"/":("index.html","text/html"),"/app.js":("app.js","text/javascript"),
               "/modules.js":("modules.js","text/javascript"),"/style.css":("style.css","text/css"),
               "/prototype.css":("prototype.css","text/css")}
    class Handler(BaseHTTPRequestHandler):
        def respond(self,data,mime,status=200,filename=None):
            self.send_response(status)
            self.send_header("Content-Type",mime+("; charset=utf-8" if mime.startswith(("text/","application/json")) else ""))
            if filename:self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self,obj,status=200):
            self.respond(json.dumps(obj,ensure_ascii=False,default=str).encode(),"application/json",status)

        def do_GET(self):
            try:
                url=urlsplit(self.path)
                if url.path in resources:
                    name,mime=resources[url.path]
                    self.respond((ROOT/"frontend"/name).read_bytes(),mime)
                    return
                obj=work.api(url.path,parse_qs(url.query))
                if isinstance(obj,tuple):self.respond(obj[0],obj[1],filename=obj[2])
                elif url.path=="/api/report":
                    self.respond(json.dumps(obj,ensure_ascii=False).encode(),"application/json",filename="TRACE_ZERO_report.json")
                else:self.send_json(obj)
            except KeyError as exc:self.send_json({"error":str(exc)},404)
            except (ValueError,TypeError) as exc:self.send_json({"error":str(exc)},400)
            except (BrokenPipeError,ConnectionResetError):pass

        def do_POST(self):
            try:
                if self.headers.get("X-Trace-Local")!="1":
                    self.send_json({"error":"Local workbench request header required"},403)
                    return
                path=urlsplit(self.path).path
                limit=MAX_BYTES if path=="/api/vault/upload" else 16384
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=limit:
                    self.send_json({"error":"Request is empty or exceeds the upload limit"},413)
                    return
                store=work.storage
                if not store:raise KeyError("Local storage is not enabled")
                raw=self.rfile.read(size)
                if len(raw)!=size:raise ValueError("Incomplete request")
                if path=="/api/vault/upload":
                    result=store.upload(self.headers.get("X-File-Name",""),raw)
                else:
                    body=json.loads(raw)
                    if not isinstance(body,dict):raise ValueError("Expected a JSON object")
                    if path=="/api/vault/review":result=store.review_upload(body.get("ref",""),body.get("note"))
                    elif path=="/api/sentinel/run":result=store.run(body)
                    elif path=="/api/sentinel/demo":result=store.load_demo()
                    elif path=="/api/sentinel/review":result=store.review_exercise(body.get("id",""),body)
                    else:raise KeyError("Unknown endpoint")
                self.send_json(result,201)
            except KeyError as exc:self.send_json({"error":str(exc)},404)
            except (ValueError,TypeError,AttributeError) as exc:self.send_json({"error":str(exc)},400)
            except (BrokenPipeError,ConnectionResetError):pass

        def log_message(self,*args):pass
    return Handler

def config():
    values={}
    if (ROOT/".env").exists():
        for line in (ROOT/".env").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k,v=line.split("=",1);values[k.strip()]=v.strip()
    return values

if __name__=="__main__":
    settings=config()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",type=Path,default=BASE/"evidence")
    parser.add_argument("--port",type=int,default=int(os.environ.get("TRACE_PORT",settings.get("TRACE_PORT","8765"))))
    parser.add_argument("--open",action="store_true")
    parser.add_argument("--db",type=Path,default=Path(os.environ.get("TRACE_DB",settings.get("TRACE_DB",str(BASE/"data/workbench.sqlite3")))))
    args=parser.parse_args()
    print("Indexing the case evidence...",flush=True)
    work=Workbench(Case(args.evidence),Storage(args.db))
    passwords={role:secrets.token_urlsafe(12) for role in ROLES}
    guard=Access(work.storage,passwords)
    with ThreadingHTTPServer(("127.0.0.1",args.port),secured(handler(work),guard)) as server:
        print("Local demo accounts · passwords change on each launch",flush=True)
        for role,password in passwords.items():print(f"  {role:14} {password}",flush=True)
        del passwords
        url=f"http://127.0.0.1:{server.server_port}"
        print(f"TRACE//ZERO is ready at {url}. Use Ctrl+C to stop.",flush=True)
        if args.open:threading.Timer(.3,webbrowser.open,args=(url,)).start()
        try:server.serve_forever()
        except KeyboardInterrupt:pass
