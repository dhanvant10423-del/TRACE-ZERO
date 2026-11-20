"""Deterministic policy evaluation over fictional observations."""
from datetime import datetime, timedelta, timezone

IDENTITIES = {
    "finance-demo": {"label":"Finance operator", "actions":["read","vendor_change","beneficiary_change"]},
    "support-demo": {"label":"Support analyst", "actions":["read"]},
    "integration-demo": {"label":"Enterprise connector", "actions":["api_read","read"]},
    "admin-demo": {"label":"Configuration reviewer", "actions":["read","permission_change"]},
}
DEFAULT = dict(identity="finance-demo", action="read", familiar_network=True,
               recognized_device=True, business_hours=True, verified=True,
               sensitive=False, volume=3, broad_scope=False, repeated=False)
SCENARIOS = {
    "normal": ("Routine sign-in and read", False, {}, "ALLOW"),
    "travel": ("Legitimate employee travelling", False, dict(familiar_network=False, recognized_device=False, verified=False), "VERIFY"),
    "after_hours": ("Legitimate work outside office hours", False, dict(business_hours=False), "VERIFY"),
    "approved_bank": ("Authorized beneficiary review · banking simulation", False, dict(action="beneficiary_change", sensitive=True, verified=False), "VERIFY"),
    "denied_bank": ("Support user requests beneficiary change · banking simulation", True, dict(identity="support-demo",action="beneficiary_change",sensitive=True), "RESTRICT"),
    "denied_vendor": ("Support user requests vendor account change", True, dict(identity="support-demo",action="vendor_change",sensitive=True), "RESTRICT"),
    "sensitive_read": ("Sensitive document access", False, dict(identity="support-demo",action="read",sensitive=True,verified=False), "VERIFY"),
    "api_volume": ("Unusual API activity", True, dict(identity="integration-demo",action="api_read",volume=60,sensitive=True,verified=False), "RESTRICT"),
    "excess_scope": ("Connector has excessive scope", True, dict(identity="integration-demo",action="api_read",broad_scope=True,sensitive=True), "RESTRICT"),
    "admin_review": ("Authorized administrator reviews a policy change", False, dict(identity="admin-demo",action="permission_change",sensitive=True,verified=False), "VERIFY"),
    "sequence": ("Repeated prohibited sensitive requests", True, dict(identity="support-demo",action="vendor_change",sensitive=True,repeated=True), "CONTAIN"),
}
ACTIONS = dict(read="Read document", api_read="Read through API", vendor_change="Change vendor account",
               beneficiary_change="Change beneficiary", permission_change="Change integration permissions")
RESPONSES = {
    "ALLOW":("LOW","Allow and monitor"),
    "VERIFY":("MODERATE","Require verification for the requested operation"),
    "RESTRICT":("HIGH","Restrict the operation and refer it for review"),
    "CONTAIN":("CRITICAL","Simulate isolating this session and refer it for review"),
}

def catalog():
    return [{"id":key,"label":label,"settings":DEFAULT|settings} for key,(label,_,settings,_) in SCENARIOS.items()]

def settings_for(body):
    scenario=body.get("scenario","normal")
    if not isinstance(scenario,str) or scenario not in SCENARIOS:raise ValueError("Unknown scenario")
    changes=body.get("settings",{})
    if not isinstance(changes,dict) or set(changes)-DEFAULT.keys():raise ValueError("Unknown scenario settings")
    settings=DEFAULT|SCENARIOS[scenario][2]|changes
    for key,default in DEFAULT.items():
        if type(settings[key]) is not type(default):raise ValueError("Invalid setting "+key)
    if settings["identity"] not in IDENTITIES or settings["action"] not in ACTIONS or not 1<=settings["volume"]<=10000:
        raise ValueError("Use a demo identity, a listed action and a volume from 1 to 10000")
    return scenario,settings

def evaluate(settings):
    s=settings
    identity=IDENTITIES[s["identity"]]
    sensitive=s["sensitive"] or s["action"] in {"vendor_change","beneficiary_change","permission_change"}
    authorized=s["action"] in identity["actions"]
    baseline=[
        ("Network context",not s["familiar_network"],"Familiar network is a context signal"),
        ("Device context",not s["recognized_device"],"Recognized device is a context signal"),
        ("Sign-in hours",not s["business_hours"],"Timestamp is within the expected hours"),
        ("Activity volume",s["volume"]>=50,"Below the fixed volume threshold"),
    ]
    signals=[]
    if not authorized:signals.append("This demo identity lacks permission for the operation.")
    if sensitive:signals.append("The resource or requested change is sensitive.")
    if s["broad_scope"]:signals.append("Granted connector scope exceeds the declared need in this fixture.")
    if s["repeated"]:signals.append("Review telemetry shows repeated sensitive requests.")
    if not s["verified"]:signals.append("Independent session verification is pending.")
    if s["volume"]>=50:signals.append("Volume exceeded the baseline review threshold.")
    flagged=any(x[1] for x in baseline)
    if not authorized and s["repeated"]:decision="CONTAIN"
    elif not authorized or sensitive and (s["broad_scope"] or s["volume"]>=50):decision="RESTRICT"
    elif not s["verified"] or flagged or s["broad_scope"] or s["repeated"]:decision="VERIFY"
    else:decision="ALLOW"
    category,response=RESPONSES[decision]
    certainty="BETTER ESTABLISHED" if s["verified"] else "LIMITED" if s["recognized_device"] else "UNKNOWN"
    return {"baseline":"FLAGGED" if flagged else "PASSED",
            "checks":[{"signal":name,"flagged":flag,"detail":"Triggered configured baseline rule" if flag else detail}
                      for name,flag,detail in baseline],
            "baseline_omissions":["Operation permission","Resource sensitivity","Permission scope","Repeated operation context","Independent verification"],
            "authorized":authorized,"sensitive":sensitive,"risk":category,"identity_certainty":certainty,
            "decision":decision,"response":response,"signals":signals or ["No configured operation-level review trigger."],
            "limitations":"Fixture observations describe a simulated session. Identity certainty and risk describe different things."}

def event_records(run_id, timestamp, s, result):
    when=datetime.fromisoformat(timestamp)
    identity=s["identity"]
    resource={"vendor_change":"Fictional vendor account","beneficiary_change":"Fictional beneficiary",
              "permission_change":"Demo connector policy","api_read":"Demo enterprise API","read":"Demo document"}[s["action"]]
    events = [
        record(run_id,"01",when,identity,"AUTH","Simulated sign-in",identity,{"baseline":result["baseline"],"verified":s["verified"]}),
        record(run_id,"02",when+timedelta(seconds=1),identity,"POLICY","Read permission snapshot",resource,
               {"authorized":result["authorized"],"declared_scope_exceeded":s["broad_scope"]}),
        record(run_id,"03",when+timedelta(seconds=2),identity,"REQUEST",ACTIONS[s["action"]],resource,
               {"action_key":s["action"],"sensitive":result["sensitive"],"volume":s["volume"],"repeated":s["repeated"]}),
        record(run_id,"04",when+timedelta(seconds=3),identity,"DECISION","Evaluate requested operation",resource,
               {"decision":result["decision"],"risk":result["risk"],"identity_certainty":result["identity_certainty"]}),
    ]
    events.append(record(run_id,"network",when-timedelta(seconds=1),identity,"NETWORK",
                         "Record network context","Demo network boundary",{"familiar":s["familiar_network"]}))
    if s["action"]=="vendor_change":
        events.append(record(run_id,"ticket",when+timedelta(milliseconds=1500),"support-demo","HELPDESK",
                             "Log vendor update ticket","Fictional vendor account",{"ticket_id":"TICKET-"+run_id,
                              "service":"Demo Helpdesk","confirmation":"Pending"}))
    return sorted(events,key=lambda evt:evt["utc"])

def record(run_id, suffix, when, actor, type_, action, target, raw):
    return dict(ref=f"{run_id}/{suffix}",utc=when.isoformat(),actor=actor,kind=type_,action=action,
                target=target,raw=raw,status="VALID",origin="SYNTHETIC")

def analyze(events, exclusions):
    included={r["kind"]:r for r in events if r["ref"] not in exclusions and r["kind"]!="REVIEW"}
    hypotheses={key:{"status":"UNRESOLVED","refs":[],"explanation":text} for key,text in {
        "H1":"Request, permission and control records are needed to assess use outside permission.",
        "H2":"A request and permission snapshot are needed to assess access scope.",
        "H3":"Request and decision records are needed to establish an exact simulated operation link.",
    }.items()}
    edges=[]
    def finding(key,status,inputs,rule,explanation):
        refs=[included[k]["ref"] for k in inputs]
        hypotheses[key]={"status":status,"refs":refs,"explanation":explanation}
        edges.append(dict(id=key,source=refs[0],target=refs[-1],refs=refs,rule=rule,
                          status="VERIFIED" if key=="H3" else "INFERRED",explanation=explanation))
    if {"REQUEST","POLICY","DECISION"}<=included.keys():
        allowed=included["POLICY"]["raw"]["authorized"]
        finding("H1","CONTRADICTED" if allowed else "SUPPORTED BY EVIDENCE",
                ["REQUEST","POLICY","DECISION"],"SIM-01","The policy snapshot "+("allows" if allowed else "denies")+" this operation for the demo identity.")
    if {"REQUEST","POLICY"}<=included.keys():
        broad=included["POLICY"]["raw"]["declared_scope_exceeded"]
        finding("H2","SUPPORTED BY EVIDENCE" if broad else "CONTRADICTED",
                ["REQUEST","POLICY"],"SIM-02","The fixture declares "+("scope exceeds" if broad else "scope within")+" operational need.")
    if {"REQUEST","DECISION"}<=included.keys():
        finding("H3","CONTRADICTED",["REQUEST","DECISION"],"SIM-03",
                "The fixture emitter recorded both under the same unique simulation run.")
    return {"hypotheses":hypotheses,"relationships":edges,"excluded":sorted(exclusions)}

def benchmark():
    """Compare fixed fixture outcomes. Edited runs never become labelled tests."""
    scores={engine:dict(tp=0,fp=0,tn=0,fn=0) for engine in ("baseline","sentinel")}
    correct=recovered=eligible=0
    rows=[]
    for key,(label,needs_restriction,changes,expected) in SCENARIOS.items():
        s=DEFAULT|changes
        r=evaluate(s)
        predictions={"baseline":r["baseline"]=="FLAGGED","sentinel":r["decision"] in ("RESTRICT","CONTAIN")}
        for name,positive in predictions.items():
            code=("t" if positive==needs_restriction else "f")+("p" if positive else "n")
            scores[name][code]+=1
        correct+=r["decision"]==expected
        if not needs_restriction and expected=="VERIFY" and s["action"] in IDENTITIES[s["identity"]]["actions"]:
            eligible+=1
            recovered+=evaluate(s|{"verified":True,"familiar_network":True,"recognized_device":True,
                                   "business_hours":True})["decision"]=="ALLOW"
        rows.append(dict(id=key,label=label,expected=expected,actual=r["decision"],baseline=r["baseline"]))
    return {"size":len(rows),"counts":scores,"correct":correct,"recovery":[recovered,eligible],"rows":rows}
