import csv
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler

from openpyxl import Workbook
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from ingest import Case
from sentinel import benchmark,evaluate,settings_for
from server import Workbench,ThreadingHTTPServer,handler
from storage import Storage
from vault import extract

class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case=Case()
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/"evidence.sqlite3"
        self.store=Storage(self.path)

    def test_control_comparison_and_dependencies(self):
        run=self.store.run({"scenario":"denied_bank"})
        self.assertEqual(run["result"]["baseline"],"PASSED")
        self.assertFalse(run["result"]["authorized"])
        self.assertEqual(run["result"]["decision"],"RESTRICT")
        self.assertEqual(run["analysis"]["hypotheses"]["H1"]["status"],"SUPPORTED BY EVIDENCE")
        permission=next(e["ref"] for e in run["events"] if e["kind"]=="POLICY")
        modified=self.store.exercise(run["id"],[permission])
        self.assertEqual(modified["analysis"]["hypotheses"]["H1"]["status"],"UNRESOLVED")
        self.assertEqual(len(modified["diff"]["withdrawn"]),2)
        self.assertEqual(len(modified["diff"]["retained"]),1)
        self.assertEqual(Storage(self.path).exercise(run["id"]),run)

    def test_review_recovery_and_restriction(self):
        travel=self.store.run({"scenario":"travel"})
        self.assertEqual(travel["result"]["decision"],"VERIFY")
        self.assertEqual(travel["result"]["baseline"],"FLAGGED")
        recovered=self.store.review_exercise(travel["id"],{"outcome":"verified","note":"Verified using independent exercise procedure."})
        self.assertEqual(recovered["review"]["decision"],"ALLOW AND MONITOR")
        with self.assertRaises(ValueError):
            self.store.review_exercise(travel["id"],{"outcome":"verified","note":"Repeat"})
        denied=self.store.run({"scenario":"denied_vendor"})
        with self.assertRaises(ValueError):
            self.store.review_exercise(denied["id"],{"outcome":"verified","note":"No escalation"})
        self.assertEqual(self.store.review_exercise(denied["id"],{"outcome":"held","note":"Authorization needed"})["review"]["decision"],"HOLD FOR AUTHORIZED REVIEW")

    def test_fixtures_validation_and_metrics(self):
        with self.assertRaises(ValueError):
            settings_for({"scenario":"normal","settings":{"volume":True}})
        with self.assertRaises(ValueError):
            settings_for({"scenario":"normal","settings":{"identity":"real-user"}})
        result=benchmark()
        self.assertEqual(result["size"],11)
        self.assertGreater(result["counts"]["baseline"]["fn"],0)
        self.assertGreater(result["counts"]["baseline"]["fp"],0)
        self.assertEqual(result["correct"],result["size"])
        self.assertEqual(result["recovery"][0],result["recovery"][1])
        self.assertEqual(evaluate(settings_for({"scenario":"sequence"})[1])["risk"],"CRITICAL")

    def test_repeatable_demo_is_idempotent(self):
        first=self.store.load_demo()
        self.assertEqual(self.store.load_demo(),first)
        self.assertEqual(len(self.store.exercises()),5)
        self.assertTrue(all(x["origin"]=="SYNTHETIC" for x in first["events"]))

    def test_original_hash_duplicate_and_review(self):
        raw=b"timestamp,actor\n2026-01-01T10:00:00,alice\n"
        original=self.store.upload("access%20log.csv",raw)
        self.assertEqual(original["filename"],"access log.csv")
        rows=self.store.rows(original["id"])
        self.assertEqual(rows[0]["status"],"AMBIGUOUS")
        self.assertIsNone(rows[0]["utc"])
        self.store.review_upload(rows[0]["ref"],"Confirm clock with source owner")
        self.assertEqual(self.store.upload_reviews(rows[0]["ref"])[0]["note"],"Confirm clock with source owner")
        copy=self.store.upload("repeat.csv",raw)
        self.assertEqual(copy["duplicate_of"],original["id"])
        self.assertEqual(self.store.original(original["id"]),(raw,True))
        with sqlite3.connect(self.path) as db:db.execute("UPDATE original SET raw=? WHERE id=?",(b"changed",original["id"]))
        self.assertFalse(self.store.original(original["id"])[1])

    def test_formats_and_statuses(self):
        rows,error=extract("valid.csv",b"timestamp,actor\n2026-02-01T01:02:03Z,alice\n2026-02-01T01:02:03Z,alice\nmalformed\n")
        self.assertFalse(error)
        self.assertEqual([r["status"] for r in rows],["VALID","DUPLICATE","REJECTED"])
        rows,error=extract("records.json",b'[{"timestamp":"bad"},{"action":"review"},false]')
        self.assertEqual([r["status"] for r in rows],["QUARANTINED","PARTIAL","REJECTED"])
        self.assertTrue(extract("broken.json",b"not-json")[1])
        workbook=Workbook()
        workbook.active.title="Access"
        workbook.active.append(["actor","action"])
        workbook.active.append(["finance-demo","read"])
        buf=io.BytesIO();workbook.save(buf)
        rows,error=extract("evidence.xlsx",buf.getvalue())
        self.assertFalse(error)
        self.assertEqual(rows[1]["locator"],"Access!2")
        buf=io.BytesIO();canvas=Canvas(buf);canvas.drawString(36,700,"A sample audit note");canvas.save()
        rows,error=extract("note.pdf",buf.getvalue())
        self.assertFalse(error)
        self.assertIn("sample audit",rows[0]["raw"]["text"])
        self.assertEqual(rows[0]["locator"],"p1")
        self.assertTrue(extract("bad.pdf",b"bad")[1])

    def test_filters_scopes_and_exports(self):
        work=Workbench(self.case,self.store)
        run=self.store.load_demo()
        scope=json.dumps({"H1":[]})
        overview=work.api("/api/overview",{"hyp_rules":[scope]})
        self.assertEqual(overview["hypotheses"]["H1"]["status"],"NOT EVALUATED")
        self.assertNotEqual(work.api("/api/overview",{})["hypotheses"]["H1"]["status"],"NOT EVALUATED")
        source=self.store.upload("filtered.json",b'[{"timestamp":"2026-09-02T11:00:00Z"},{"timestamp":"2026-09-01T11:00:00Z"}]')
        rows=work.api("/api/vault/rows",{"id":[source["id"]],"timeline":["1"]})["rows"]
        self.assertLess(rows[0]["utc"],rows[1]["utc"])
        ref=next(e["ref"] for e in run["events"] if e["kind"]=="POLICY")
        args={"run":[run["id"]],"sim_exclude":[ref]}
        report=json.loads(work.api("/api/exports/json",args)[0])
        self.assertEqual(report["simulation"]["analysis"]["hypotheses"]["H1"]["status"],"UNRESOLVED")
        self.assertTrue(report["timeline"])
        self.assertTrue(report["graph"][0]["refs"])
        self.assertTrue(all(r["origin"]=="CASE" for r in report["observations"]))
        payload,mime,_=work.api("/api/exports/pdf",args)
        self.assertEqual(mime,"application/pdf")
        reader=PdfReader(io.BytesIO(payload))
        self.assertIn("Investigation objective",reader.pages[0].extract_text())
        self.assertGreater(len(reader.pages),1)
        csv_data=work.api("/api/exports/csv",args)[0].decode("utf-8-sig")
        origins={r["origin"] for r in csv.DictReader(io.StringIO(csv_data))}
        self.assertEqual(origins,{"CASE","UPLOADED","SYNTHETIC"})

    def test_http_api_and_assets(self):
        work=Workbench(self.case,self.store)
        with ThreadingHTTPServer(("127.0.0.1",0),handler(work)) as http:
            thread=threading.Thread(target=http.serve_forever,daemon=True)
            thread.start()
            try:
                client=build_opener(ProxyHandler({}))
                base=f"http://127.0.0.1:{http.server_port}"
                def req(path,body=None,headers=None):
                    with client.open(Request(base+path,data=body,headers=headers or {})) as res:return res.read()
                self.assertIn(b"/modules.js",req("/"))
                self.assertIn(b"Scenario Lab",req("/modules.js"))
                run=json.loads(req("/api/sentinel/run",b'{"scenario":"approved_bank"}',{"X-Trace-Local":"1"}))
                self.assertTrue(run["result"]["authorized"])
                self.assertEqual(run["result"]["decision"],"VERIFY")
                persisted=json.loads(req("/api/sentinel/runs"))
                self.assertEqual(persisted[0]["id"],run["id"])
                entry=json.loads(req("/api/vault/upload",b"identity,timestamp\nfinance-demo,2026-01-01T08:00:00Z",{"X-Trace-Local":"1","X-File-Name":"new.csv"}))
                self.assertEqual(entry["counts"],{"VALID":1})
                self.assertTrue(req("/api/exports/pdf?run="+run["id"]).startswith(b"%PDF"))
                with self.assertRaises(HTTPError) as error:req("/api/sentinel/run",b"{}")
                self.assertEqual(error.exception.code,403)
            finally:
                http.shutdown()
                thread.join()
