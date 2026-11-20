"""Source-specific admission and normalization for CR-26-047. All inputs are read-only."""
import csv
import hashlib
import ipaddress
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CATALOG = json.loads((BASE / "reference/catalog.json").read_text(encoding="utf-8"))
IST = timezone(timedelta(hours=5, minutes=30))
# Natural record identifier, actor, target, action, outcome, time, event class.
FIELDS = {
    "E01": ("request_id","api_key_id","endpoint","method","status","ts_utc","API request"),
    "E02": ("event_id","actor","object_id","action","result","ts_local","HelpDeskr activity"),
    "E03": ("event_id","user","device_id",None,"result","ts_utc","Staff sign-in"),
    "E04": ("credential_id","credential_id","system",None,"status",None,"Register entry"),
    "E05": ("event_id","principal","path","action","result","epoch_s","Storage activity"),
    "E13": (None,"author","channel",None,None,"ts_local","Chat message"),
    "E14": ("employee_id","username",None,None,"status",None,"Roster entry"),
    "E15": ("flow_id","src_ip","dst_system",None,"result","ts_utc","Network flow"),
    "E17": ("indicator",None,"indicator",None,None,None,"Vendor indicator"),
    "E19": ("change_id","changed_by","vendor_id","field",None,"ts_utc","Vendor change"),
}
FIELDS["E18"] = FIELDS["E01"]
PATTERNS = {"request_id":r"req-[a-zA-Z0-9-]+","change_id":r"chg-[a-zA-Z0-9-]+",
            "employee_id":r"HF[0-9]+","flow_id":r"flw-[a-zA-Z0-9-]+"}
UTC = timezone.utc

@dataclass(slots=True)
class Record:
    ref: str
    sid: str
    raw: dict
    label: str
    actor: str | None = None
    target: str | None = None
    action: str | None = None
    outcome: str | None = None
    original: str | None = None
    utc: str | None = None
    clock: str = "undated"
    quality: str = "VALID"
    note: str = "Passed source checks"
    @property
    def usable(self):
        return self.quality in ("VALID","PARTIAL")

def timestamp(value, key, sid):
    if key == "epoch_s":
        return datetime.fromtimestamp(int(value), UTC), "unsynchronized source clock"
    if key == "ts_local":
        fmt = "%d/%m/%Y %H:%M:%S" if sid=="E02" else "%Y-%m-%d %H:%M"
        return datetime.strptime(value,fmt).replace(tzinfo=IST), "local time assumed IST"
    dt = datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("UTC offset missing")
    return dt, "offset supplied"

def admit(sid, loc, raw):
    fields = FIELDS.get(sid,(None,None,None,None,None,None,"Document observation"))
    key,actor,target,action,outcome,clock,label = fields
    r = Record(f"{sid}/{loc}",sid,raw,label)
    if not isinstance(raw,dict) or None in raw or any(v is None for v in raw.values()) and sid in CATALOG and "columns" in CATALOG[sid]:
        r.raw={"input":str(raw)}
        r.quality,r.note="REJECTED","Malformed record or inconsistent CSV row width"
        return r
    r.actor,r.target,r.action,r.outcome,r.original = (raw.get(k) or None for k in (actor,target,action,outcome,clock))
    required=[key,actor,action,outcome,clock]
    if sid!="E03": required.append(target)
    required.extend({"E13":["text"],"E04":["integration","system","scope"],"E17":["type"],
                     "E19":["channel"],"E02":["actor_type"]}.get(sid,[]))
    missing=[k for k in required if k and raw.get(k) in ("",None)]
    if missing:
        r.quality,r.note="QUARANTINED","Missing required field(s) "+", ".join(missing)
        return r
    try:
        for k,pattern in PATTERNS.items():
            if raw.get(k) and not re.fullmatch(pattern,str(raw[k])):
                raise ValueError("Invalid "+k)
        if key=="event_id" and not re.fullmatch({"E02":"evt","E03":"sso","E05":"bv"}[sid]+r"-[a-zA-Z0-9-]+",raw[key]):
            raise ValueError("Invalid event_id")
        for k in ("caller_ip","source_ip","src_ip"):
            if raw.get(k): ipaddress.ip_address(raw[k])
        if sid=="E17" and raw["type"]=="ip": ipaddress.ip_address(raw["indicator"])
        for k in ("records_returned","bytes","bytes_in","bytes_out"):
            if k in raw and int(raw[k])<0: raise ValueError("Negative "+k)
        if sid in ("E01","E18") and not 100<=int(raw["status"])<=599: raise ValueError("Invalid HTTP status")
        if clock:
            dt,r.clock=timestamp(r.original,clock,sid)
            r.utc=dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00","Z")
    except (ValueError,TypeError,OSError,OverflowError) as exc:
        r.quality,r.note="QUARANTINED",f"Field validation failed ({exc})"
        return r
    if sid=="E05" and not raw["source_ip"] or sid=="E03" and not raw["device_id"]:
        r.quality,r.note="PARTIAL","Optional source IP or device missing. Attribute-specific links unavailable."
    if sid=="E14" and raw["status"]=="active" and raw["termination_date"]:
        r.quality,r.note="AMBIGUOUS","Roster reports both active status and a termination date"
    return r

def source_rows(path,sid,profile,digest):
    if "columns" in profile:
        with path.open(encoding="utf-8-sig",newline="") as f:
            reader=csv.DictReader(f,strict=True)
            if len(set(reader.fieldnames or []))!=len(reader.fieldnames or []) or set(profile["columns"])-set(reader.fieldnames or []):
                raise ValueError("Unexpected CSV header")
            for n,row in enumerate(reader,2): yield str(n),row
    elif sid in ("E04","E13"):
        key="integrations" if sid=="E04" else "messages"
        items=json.loads(path.read_text(encoding="utf-8-sig"))[key]
        if not isinstance(items,list): raise ValueError("Expected JSON array "+key)
        for n,row in enumerate(items): yield f"{key}[{n}]",row
    else:
        if digest!=profile["original_sha256"]:
            raise ValueError("Document changed. Re-review text before applying the original interpretation.")
        yield from profile["extract"]

class Case:
    def __init__(self,folder=None):
        folder=Path(folder or BASE/"evidence")
        self.by_id={}
        self.sources={}
        self.rows=defaultdict(list)
        for sid,p in CATALOG.items():
            matches=sorted(x for x in folder.glob(sid+"_*") if x.is_file() and x.suffix.lower()==Path(p["filename"]).suffix)
            info=self.sources[sid]={"filename":matches[0].name if len(matches)==1 else p["filename"],"sha256":None,"state":"available","reason":"","counts":{},"schema":p.get("columns",[])}
            batch=[]
            try:
                if len(matches)!=1: raise ValueError("Expected one source file, found "+str(len(matches)))
                digest=hashlib.sha256(matches[0].read_bytes()).hexdigest()
                info["sha256"]=digest
                batch=[admit(sid,loc,row) for loc,row in source_rows(matches[0],sid,p,digest)]
                if not info["schema"] and batch: info["schema"]=list(batch[0].raw)
            except (ValueError,KeyError,UnicodeError,OSError,csv.Error,TypeError) as exc:
                info.update(state="unavailable",reason=str(exc))
            seen=defaultdict(list)
            for r in batch:
                key=FIELDS.get(sid,(None,))[0]
                if key and r.raw.get(key): seen[str(r.raw[key])].append(r)
            for group in seen.values():
                if len(group)<2: continue
                if all(r.raw==group[0].raw for r in group):
                    for r in group[1:]: r.quality,r.note="DUPLICATE","Repeated record of "+group[0].ref
                else:
                    for r in group: r.quality,r.note="QUARANTINED","Conflicting rows share a source identifier"
            self.rows[sid]=batch
            info["counts"]=dict(Counter(r.quality for r in batch))
            self.by_id.update((r.ref,r) for r in batch)
        self.timeline=sorted((r for r in self.by_id.values() if r.utc),key=lambda r:(r.utc,r.ref))
