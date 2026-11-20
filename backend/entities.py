"""Entity occurrences are typed and scoped. Sharing a value describes a reference only."""
from collections import defaultdict

def typed_keys(r):
    d=r.raw
    if r.sid in ("E01","E18"):
        yield ("LedgerOne","request",d["request_id"])
        if not r.actor.startswith("user:"):yield ("LedgerOne","credential",r.actor)
    elif r.sid=="E19":
        yield ("LedgerOne","vendor",r.target)
        if d["channel"]=="API":
            if d["request_id"]:yield ("LedgerOne","request",d["request_id"])
            yield ("LedgerOne","credential",r.actor)
    elif r.sid=="E04":
        yield (r.target,"credential",r.actor)
        yield (r.target,"integration",d["integration"])
    elif r.sid=="E02":
        if d["actor_type"]=="integration":yield ("HelpDeskr","credential",r.actor)
        if r.target.startswith("TKT-"):yield ("HelpDeskr","ticket",r.target)
        elif r.target.startswith("EXP-"):yield ("HelpDeskr","export job",r.target)
    elif r.sid=="E05":
        if r.actor.startswith("key:"):yield ("BlueVault","credential",r.actor[4:])
        yield ("BlueVault","resource",r.target)
    elif r.sid=="E15":
        yield ("private link","tunnel",d["tunnel_id"])
    elif r.sid=="E03":
        yield ("SSO","account",r.actor)
        if d["device_id"]:yield ("SSO","device",d["device_id"])

class EntityIndex:
    def __init__(self,case):
        self.occurrences=defaultdict(list)
        for r in case.by_id.values():
            if r.usable:
                for key in typed_keys(r):self.occurrences[key].append(r)
    def neighbors(self,record,excluded):
        if not record.usable or record.sid in excluded or record.ref in excluded:return []
        output=[]
        for key in typed_keys(record):
            peers=[r for r in self.occurrences[key] if r.ref!=record.ref and r.sid not in excluded and r.ref not in excluded]
            # Put independent source observations first for manual inspection.
            peers.sort(key=lambda r:r.sid==record.sid)
            output.append({"system":key[0],"type":key[1],"value":key[2],"count":len(peers),
                           "rule":"L01: exact identifier in the same system and semantic field",
                           "refs":[r.ref for r in peers[:8]]})
        return output
