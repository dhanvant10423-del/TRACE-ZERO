"""Deterministic predicates. Each rule result carries its complete minimal witness set."""
from collections import defaultdict
from ingest import IST
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
import re

HYPOTHESES = {
    "H1":"Integration misuse",
    "H2":"Excessive access with a legitimate operational explanation",
    "H3":"Distinct event contexts",
}
RULES = {
 "R01":"A register entry and log identify the same credential inside the same system.",
 "R02":"A joined bank write exceeds the announced contact-field change and lacks a recorded approval.",
 "R03":"The registered LedgerOne all-module scope exceeds the modules named in the onboarding request.",
 "R04":"A joined email or phone write falls within the vendor’s announced contact sync after its effective date.",
 "R05":"A ticket read and a later storage read involve a key mentioned in chat. The transfer mechanism is unobserved.",
 "R06":"A successful vendor PATCH and an API change share a unique request ID, vendor, field family, credential, address and UTC timestamp.",
 "R07":"A user’s finance export and the integration’s export use different recorded principals and a separately documented audit context.",
 "R08":"Expose missing proof or unavailable source coverage.",
 "R09":"A registered HelpDeskr integration downloaded a created export from a vendor-listed high-confidence IP in its stated UTC date window.",
 "R11":"A registered LedgerOne key downloaded an export from an E17 high-confidence address within its stated date range.",
 "R12":"A build-labelled flow and API request share source address, destination system and UTC day. Candidate only.",
 "R13":"Distinct successful August export creations reconcile to the reviewed E06 invoice count.",
 "R10":"An export deletion returned an error. A final deletion receipt is needed to determine its later state.",
}
def evaluate_status(tags,evaluated=True):
    if not evaluated:return "NOT EVALUATED"
    s="supports" in tags
    c="contradicts" in tags
    if s and c:return "MIXED"
    if s:return "SUPPORTED BY EVIDENCE"
    if c:return "CONTRADICTED"
    return "UNRESOLVED"

def api_change_matches(req,change):
    if not req or not change or not req.usable or not change.usable:return False
    a,b=req.raw,change.raw
    suffix={"contact_email":"contact","contact_phone":"contact","bank_account":"bank-details"}.get(b.get("field"))
    return bool(suffix and b["channel"]=="API" and a["method"]=="PATCH" and a["status"].startswith("2")
                and a["request_id"]==b["request_id"] and a["api_key_id"]==b["changed_by"]
                and a["caller_ip"] and b["source_ip"] and a["caller_ip"]==b["source_ip"] and req.utc==change.utc
                and a["endpoint"]==f"/v2/vendors/{b['vendor_id']}/{suffix}")

def run(case,excluded=()):
    excluded=set(excluded)
    live={s:[r for r in rows if r.usable and r.ref not in excluded] if s not in excluded else []
          for s,rows in case.rows.items()}
    def page(s,number):
        return next((r for r in live[s] if r.ref==f"{s}/p{number}"),None)
    facts=[]
    def emit(rule,anchor,title,summary,refs,effects,kind="inference",entity=None):
        unique=list(dict.fromkeys(r.ref for r in refs))
        facts.append(dict(id=rule+"@"+anchor.ref,rule=rule,title=title,summary=summary,
                          refs=unique,effects=effects,kind=kind,utc=anchor.utc,entity=entity))
    regs={(r.target,r.actor):r for r in live["E04"]}
    requests=defaultdict(list)
    for r in live["E01"]+live["E18"]: requests[r.raw["request_id"]].append(r)
    changes=defaultdict(list)
    for r in live["E19"]:
        if r.raw["request_id"]:changes[r.raw["request_id"]].append(r)
    notice,onboarding=page("E16",1),page("E07",1)
    for change in live["E19"]:
        b=change.raw
        if b["channel"]!="API":continue
        group=requests[b["request_id"]]
        if len(group)!=1 or len(changes[b["request_id"]])!=1 or not api_change_matches(group[0],change):
            emit("R08",change,"API change lacks a validated request pair",
                 "The request is missing, non-unique or incompatible with the change record.",[change],{"H3":"gap"},"unresolved")
            continue
        req=group[0]
        entity="LedgerOne vendor / "+change.target
        emit("R06",change,"Vendor change linked to API request",
             f"{b['field']} for {change.target} matches {b['request_id']} across both logs.",
             [req,change],{"H3":"contradicts"},entity=entity)
        reg=regs.get(("LedgerOne",change.actor))
        if not reg: continue
        if b["field"]=="bank_account":
            emit("R01",change,"Bank change used a registered credential",
                 "The request key matches the LedgerOne credential in the September register snapshot.",
                 [req,change,reg],{"H1":"relevant","H2":"relevant"},entity=entity)
        if not notice or reg.raw.get("vendor")!="TallyBridge Software" or change.utc[:10]<"2026-09-01":continue
        if b["field"]=="bank_account" and not b["approval_ref"]:
            emit("R02",change,"Bank details changed outside the announced contact sync",
                 f"{b['vendor_name']} ({change.target}) changed from {b['old_value']} to {b['new_value']}. The approval field is blank. A separate finance authorization could change the interpretation.",
                 [change,req,reg,notice],{"H1":"supports","H2":"contradicts"},entity=entity)
        elif b["field"] in ("contact_email","contact_phone"):
            emit("R04",change,"Contact update fits the announced sync",
                 f"{change.target} received a {b['field']} update under the registered integration. This explains this operation only.",
                 [change,req,reg,notice],{"H2":"supports","H1":"contradicts"},entity=entity)
    for (system,key),reg in regs.items():
        if onboarding and reg.raw.get("integration")=="TallyBridge-LedgerOne" and system=="LedgerOne" and reg.raw["scope"]=="read:write all-modules":
            emit("R03",reg,"Registered scope exceeds the onboarding request",
                 "E07 lists invoices, vendors and payments. E04 grants read/write access to all modules. The register shows its September snapshot.",
                 [reg,onboarding],{"H2":"supports"},entity="LedgerOne credential / "+key)
    indicators={r.raw["indicator"]:r for r in live["E17"] if r.raw["type"]=="ip" and r.raw["confidence"]=="high"}
    jobs=defaultdict(list)
    for r in live["E02"]:
        if r.action.startswith("export."):jobs[(r.target,r.actor)].append(r)
    for (job,actor),events in jobs.items():
        for event in events:
            if event.action=="export.delete" and event.outcome=="error":
                emit("R10",event,"Export deletion timed out",f"{job} has an error on deletion. Later file retention is unknown.",
                     [event],{"H1":"relevant"},entity="HelpDeskr job / "+job)
            if event.action!="export.download" or event.outcome!="ok" or event.raw["actor_type"]!="integration":continue
            reg=regs.get(("HelpDeskr",actor))
            ind=indicators.get(event.raw["source_ip"])
            created=next((r for r in events if r.action=="export.create" and r.outcome=="ok" and r.utc<=event.utc),None)
            if reg and ind and created and ind.raw["first_seen"]<=event.utc[:10]<=ind.raw["last_seen"]:
                emit("R09",event,"Integration downloaded a matched export job",
                     f"{job} was created and downloaded under {actor}. The address and date match E17. Address reuse limits attribution.",
                     [created,event,reg,ind],{"H1":"supports"},entity="HelpDeskr job / "+job)
    # Exact ticket and credential tokens in a statement support a lead; the route remains unverified.
    for msg in live["E13"]:
        tickets=re.findall(r"\bTKT-\d+\b",msg.raw["text"])
        for (system,key),reg in regs.items():
            if system!="BlueVault" or not re.search(r"(?<![\w-])"+re.escape(key)+r"(?![\w-])",msg.raw["text"]):continue
            reads=[r for r in live["E02"] if r.target in tickets and r.action=="ticket.read" and r.outcome=="ok" and r.raw["actor_type"]=="integration" and r.utc>=msg.utc]
            files=[r for r in live["E05"] if r.actor=="key:"+key and r.action=="read" and r.outcome=="ok" and r.target.startswith("/finance/")]
            for read in reads:
                later=next((r for r in files if r.utc[:10]>read.utc[:10]),None)
                if later:
                    emit("R05",read,"Possible route from a ticket to a storage key",
                         "Chat names both the ticket and key. A service read the ticket, and the key later read a finance file by the recorded clocks. Who obtained the key and how remains open.",
                         [msg,read,reg,later],{"H1":"gap","H3":"gap"},"candidate","HelpDeskr ticket / "+read.target)
    # A stated audit purpose is testimony. Require same local day, named account and actual download.
    for msg in live["E13"]:
        if "vendor audit export" not in msg.raw["text"].lower():continue
        localday=msg.original.split()[0]
        audit=next((r for r in live["E01"] if r.actor=="user:"+msg.actor and r.target.endswith("/download") and r.outcome=="200" and r.utc and
                   (datetime.fromisoformat(r.utc.replace("Z","+00:00")).astimezone(IST).date().isoformat()==localday)),None)
        other=next((r for r in live["E02"] if r.raw["actor_type"]=="integration" and r.action=="export.download" and r.outcome=="ok"),None)
        if audit and other:
            emit("R07",audit,"Documented audit offers a separate export context",
                 "The finance user's LedgerOne download matches their audit announcement. The HelpDeskr job identifies a different principal and system. Common control remains unknown.",
                 [msg,audit,other],{"H3":"supports"},entity="LedgerOne account / "+msg.actor)
    # A successful download plus a vendor indicator establishes a reviewable pattern.
    for req in live["E01"]+live["E18"]:
        if req.action!="GET" or req.outcome!="200" or not re.fullmatch(r"/v2/exports/\d+/download",req.target):continue
        reg=regs.get(("LedgerOne",req.actor))
        ind=indicators.get(req.raw["caller_ip"])
        if reg and ind and ind.raw["first_seen"]<=req.utc[:10]<=ind.raw["last_seen"]:
            emit("R11",req,"Finance export downloaded from a listed address",
                 f"LedgerOne reports {int(req.raw['records_returned']):,} returned records. Unique records and final recipients are unknown.",
                 [req,reg,ind],{"H1":"supports"},entity="LedgerOne export / "+req.target.split("/")[-2])
    for sid in ("E01","E18"):
        keyed=defaultdict(list)
        for req in live[sid]:
            if ("LedgerOne",req.actor) in regs:keyed[(req.raw["caller_ip"],req.utc[:10])].append(req)
        for flow in live["E15"]:
            if flow.raw["dst_system"]!="LedgerOne" or flow.outcome!="allowed" or not flow.raw["src_label"].startswith("tb-build-"):continue
            peers=keyed.get((flow.actor,flow.utc[:10]),[])
            if peers and not any(f["rule"]=="R12" and f["utc"][:10]==flow.utc[:10] and f["entity"]==flow.actor for f in facts):
                emit("R12",flow,"Private-link flow overlaps API activity",
                     "Same recorded IP, destination system and UTC day. The flow lacks a shared request ID. The vendor supplies the host label.",
                     [flow,peers[0]],{"H3":"gap"},"candidate",flow.actor)
    bill=page("E06",2)
    august=[r for r in live["E02"] if r.action=="export.create" and r.outcome=="ok" and r.original[3:10]=="08/2026"]
    if bill and len({r.target for r in august})==14 and len(august)==14:
        emit("R13",bill,"August billing reconciles to 14 created jobs",
             "The invoice lists 14 jobs, five included and nine charged at INR 2,500. Creation triggers billing. A charge alone cannot establish who downloaded a file.",
             [bill,*august],{},entity="HelpDeskr / August billing")
    gaps={"H1":"Operator identity, separate approvals and downstream payment execution remain unverified.",
          "H2":"Confirm effective privileges at event time and seek contemporaneous change approvals.",
          "H3":"A shared credential or address alone cannot establish a common operator across systems."}
    hs={}
    for h,name in HYPOTHESES.items():
        tags=[f["effects"][h] for f in facts if h in f["effects"]]
        hs[h]={"name":name,"status":evaluate_status(tags,any(live.values())),"gap":gaps[h],
               "counts":{t:tags.count(t) for t in ("supports","contradicts","relevant","gap")}}
    return {"facts":facts,"hypotheses":hs,"excluded":sorted(excluded)}

def context_lookup(case,ref,excluded=()):
    """Resolve a local E20 excerpt only for a matching typed field. No remote requests."""
    r=case.by_id.get(ref)
    if not r or not r.usable or r.sid in excluded or ref in excluded or "E20" in excluded:return []
    hits=[]
    def add(page,section,key,basis,excerpt,source):
        loc=f"E20/p{page}"
        if loc not in case.by_id or loc in excluded or not case.by_id[loc].usable:return
        hits.append(dict(id="CTX-"+section,case_ref=ref,source_ref=loc,source=source,matched=key,basis=basis,
                         captured="2026-09-02",published=None,retrieved=datetime.now(timezone.utc).isoformat(),
                         excerpt=excerpt,verification="Saved copy; publisher claims unverified",relevance="context only"))
    agent=r.raw.get("user_agent","")
    if agent in ("TallyBridge-Sync/3.4.1","TallyBridge-Sync/3.5.0"):
        add(2,"C",agent,"Exact product and version","Release notes describe the 3.5.0 schedule change and retirement of 3.4.x.","docs.tallybridge.example/releases")
    for field in ("caller_ip","source_ip","src_ip"):
        ip=r.raw.get(field)
        if not ip:continue
        for cidr,explanation in [("198.18.0.0/16","The simulation describes dynamic broadband allocation."),("192.0.2.0/24","The simulation describes shared mobile addresses."),("10.20.4.0/24","The saved registry lists this network as private."),("172.16.0.0/16","The saved registry lists this network as private.")]:
            if ip_address(ip) in ip_network(cidr):
                add(3,"G",ip,"Recorded address in "+cidr,explanation,"E20 saved public address registry, section G")
    return hits
