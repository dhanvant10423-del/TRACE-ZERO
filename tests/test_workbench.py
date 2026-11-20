import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from ingest import BASE, CATALOG, Case, admit
from reasoning import api_change_matches, context_lookup, evaluate_status, run
from server import Workbench, lineage

class InvestigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case=Case()
        cls.work=Workbench(cls.case)
        cls.facts=cls.work.baseline["facts"]
        cls.bank=next(f for f in cls.facts if f["rule"]=="R02")
    def test_original_inventory(self):
        self.assertEqual(len(self.case.sources),20)
        self.assertTrue(all(i["sha256"]==CATALOG[s]["original_sha256"] for s,i in self.case.sources.items()))
        self.assertTrue(all(f["refs"] and all(r in self.case.by_id for r in f["refs"]) for f in self.facts))
    def test_case_controls(self):
        from collections import Counter
        c=Counter(f["rule"] for f in self.facts)
        self.assertEqual((c["R02"],c["R04"],c["R06"]),(1,70,71))
        self.assertEqual(set(c),{"R01","R02","R03","R04","R05","R06","R07","R09","R10","R11","R12","R13"})
    def test_selective_admission(self):
        r=self.case.by_id[self.bank["refs"][0]]
        for change,flag in [({"changed_by":""},"QUARANTINED"),({"ts_utc":"yesterday"},"QUARANTINED"),
                            ({"source_ip":"300.300.0.0"},"QUARANTINED"),({None:"extra"},"REJECTED")]:
            self.assertEqual(admit("E19","sample",r.raw|change).quality,flag)
    def test_clock_and_partial_fields(self):
        r=next(r for r in self.case.rows["E02"] if r.original=="11/08/2026 23:30:10")
        self.assertEqual(r.utc,"2026-08-11T18:00:10Z")
        blank=next(r for r in self.case.rows["E05"] if not r.raw["source_ip"])
        self.assertEqual(blank.quality,"PARTIAL")
        self.assertIn("unsynchronized",blank.clock)
    def test_join_rejects_conflicts_and_clock_only(self):
        change,req=[self.case.by_id[ref] for ref in self.bank["refs"][:2]]
        for edit in ({"request_id":"req-other"},{"api_key_id":"different"},{"status":"403"},{"method":"GET"},
                     {"caller_ip":"127.0.0.1"},{"endpoint":"/v2/vendors/V-9999/bank-details"},{"ts_utc":"2026-09-02T06:00:00Z"}):
            self.assertFalse(api_change_matches(admit("E18","variant",req.raw|edit),change))
    def test_new_ids_generalize(self):
        change,req=[self.case.by_id[ref] for ref in self.bank["refs"][:2]]
        alternate={"request_id":"req-unseen","source_ip":"10.20.4.99","vendor_id":"V-9876"}
        a=admit("E19","new",change.raw|alternate)
        b=admit("E18","new",req.raw|{"request_id":"req-unseen","caller_ip":"10.20.4.99","endpoint":"/v2/vendors/V-9876/bank-details"})
        self.assertTrue(api_change_matches(b,a))
    def test_scope_requires_documented_need(self):
        self.assertFalse(any(f["rule"]=="R03" for f in self.work.scenario(("E07",))["facts"]))
    def test_source_challenge(self):
        v=self.work.api("/api/overview",{"exclude":["E18"]})
        self.assertIn(self.bank,v["diff"]["lost"])
        self.assertEqual(sum(f["rule"]=="R08" for f in v["diff"]["added"]),71)
        self.assertTrue(any(f["rule"]=="R09" for f in v["facts"]))
        self.assertEqual(self.work.scenario(())["facts"],self.facts)
    def test_each_bank_dependency(self):
        for ref in self.bank["refs"]:
            with self.subTest(ref=ref):
                self.assertFalse(any(f["rule"]=="R02" for f in self.work.scenario((ref,))["facts"]))
    def test_unrelated_source(self):
        self.assertEqual(self.work.scenario(("E09",))["facts"],self.facts)
    def test_no_sources(self):
        r=run(self.case,self.case.sources)
        self.assertFalse(r["facts"])
        self.assertEqual({h["status"] for h in r["hypotheses"].values()},{"NOT EVALUATED"})
    def test_statuses(self):
        for tags,status in [([],"UNRESOLVED"),(["supports"],"SUPPORTED BY EVIDENCE"),(["contradicts"],"CONTRADICTED"),(["supports","contradicts"],"MIXED")]:
            self.assertEqual(evaluate_status(tags),status)
    def test_weak_link(self):
        f=next(f for f in self.facts if f["rule"]=="R05")
        self.assertEqual(f["kind"],"candidate")
        self.assertEqual(f["effects"]["H3"],"gap")
    def test_reference_gate(self):
        ref=self.bank["refs"][1]
        self.assertTrue(context_lookup(self.case,ref))
        self.assertFalse(context_lookup(self.case,ref,["E20"]))
        self.assertFalse(context_lookup(self.case,"E14/5"))
        self.assertEqual(self.work.scenario(("E20",))["facts"],self.facts)
    def test_graph_and_report(self):
        graph=lineage(self.case,self.bank)
        ids={node["id"] for node in graph["nodes"]}
        self.assertTrue(all(e["from"] in ids and e["to"] in ids and e["refs"] for e in graph["edges"]))
        r=self.work.api("/api/report",{"exclude":["E18"]})
        self.assertTrue(all(not any(v.startswith("E18/") for v in f["refs"]) for f in r["facts"]))
    def test_bad_files_duplicates_conflicts(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder=Path(scratch)
            p=folder/CATALOG["E18"]["filename"]
            row=self.case.rows["E18"][0].raw
            with p.open("w",newline="") as fp:
                out=csv.DictWriter(fp,fieldnames=row);out.writeheader();out.writerows([row,row,row|{"request_id":"req-new"},row|{"request_id":"req-new","status":"401"}])
            (folder/CATALOG["E07"]["filename"]).write_bytes(b"unreviewed")
            (folder/CATALOG["E03"]["filename"]).write_text("bad,schema\n")
            c=Case(folder)
            self.assertEqual([r.quality for r in c.rows["E18"]],["VALID","DUPLICATE","QUARANTINED","QUARANTINED"])
            for sid in ["E07","E03","E19"]:self.assertEqual(c.sources[sid]["state"],"unavailable")
    def test_variation_through_full_engine(self):
        change,req=[self.case.by_id[ref] for ref in self.bank["refs"][:2]]
        base={"E04":self.case.rows["E04"],"E07":self.case.rows["E07"],"E16":self.case.rows["E16"]}
        for edits,expected in [({},True),({"approval_ref":"FIN-NEW"},False),({"changed_by":"other"},False)]:
            rows={s:[] for s in CATALOG}
            rows.update(base)
            rows["E19"]=[admit("E19","new",change.raw|{"request_id":"req-variant","vendor_id":"V-9000"}|edits)]
            rows["E18"]=[admit("E18","new",req.raw|{"request_id":"req-variant","endpoint":"/v2/vendors/V-9000/bank-details"})]
            with patch.object(self.case,"rows",rows):
                self.assertEqual(any(f["rule"]=="R02" for f in run(self.case)["facts"]),expected)
    def test_typed_identifier_neighbors(self):
        r=self.work.api("/api/record",{"ref":[self.bank["refs"][1]]})
        req=next(e for e in r["entities"] if e["type"]=="request")
        self.assertIn(self.bank["refs"][0],req["refs"])
        r=self.work.api("/api/record",{"ref":[self.bank["refs"][1]],"exclude":["E19"]})
        self.assertFalse(any(x.startswith("E19/") for e in r["entities"] for x in e["refs"]))
    def test_local_http_entry_points(self):
        from server import handler,ThreadingHTTPServer
        from threading import Thread
        from urllib.request import build_opener,ProxyHandler
        with ThreadingHTTPServer(("127.0.0.1",0),handler(self.work)) as http:
            t=Thread(target=http.serve_forever,daemon=True)
            t.start()
            try:
                client=build_opener(ProxyHandler({}))
                root=f"http://127.0.0.1:{http.server_port}"
                for uri in ["/","/app.js","/style.css","/api/overview","/api/graph?id=R02%40E19%2F313",
                            "/api/record?ref=E18%2F1088","/api/report?exclude=E18"]:
                    with client.open(root+uri,timeout=10) as response:self.assertEqual(response.status,200)
                with client.open(root+"/api/records?timeline=1&q=req-5f61b0de8") as response:
                    self.assertEqual(json.load(response)["total"],2)
            finally:http.shutdown();t.join()
