"""Portable investigation exports from the current case and selected simulation."""
import csv
import io
from xml.sax.saxutils import escape

from vault import stamp

FIELDS=("origin","ref","type","actor","action","target","utc","status","time_note")

def safe_cell(value):
    text=str(value) if value is not None else ""
    return "'"+text if text.lstrip().startswith(("=","+","-","@")) or text.startswith(("\r","\n","\t")) else text

def evidence_csv(case,uploads,exercise):
    fp=io.StringIO(newline="")
    out=csv.writer(fp)
    out.writerow(FIELDS)
    for r in case.by_id.values():
        out.writerow([safe_cell(v) for v in ("CASE",r.ref,r.label,r.actor,r.action,r.target,r.utc,r.quality,r.clock)])
    for r in uploads:
        out.writerow([safe_cell(v) for v in ("UPLOADED",r["ref"],r["type"],r["raw"].get("actor"),r["raw"].get("action"),
                      r["raw"].get("target"),r["utc"],r["status"],r["reason"])])
    if exercise:
        for r in exercise["events"]:
            out.writerow([safe_cell(v) for v in ("SYNTHETIC",r["ref"],r["kind"],r["actor"],r["action"],r["target"],r["utc"],r["status"],"Simulated clock")])
    return fp.getvalue().encode("utf-8-sig")

def build_report(case,overview,uploads,exercise):
    findings=overview["facts"]
    refs=sorted({ref for f in findings for ref in f["refs"]})
    observations=[]
    for ref in refs:
        r=case.by_id[ref]
        observations.append(dict(ref=ref,type=r.label,actor=r.actor,action=r.action,target=r.target,
                                 utc=r.utc,original=r.original,time_note=r.clock,status=r.quality,origin="CASE"))
    timeline=sorted((r for r in observations if r["utc"]),key=lambda r:r["utc"])
    graph=[dict(rule=f["rule"],subject=f.get("entity"),refs=f["refs"],kind=f["kind"],explanation=f["summary"]) for f in findings]
    investigation_steps=[
        "Request historical role, credential scope and approval information for findings flagged for review.",
        "Compare original system clocks and timezone assumptions before making order-sensitive claims.",
        "Preserve original files and test alternative explanations by challenging individual corroborating records.",
    ]
    return dict(case="CR-26-047",organization="Harbor & Finch Freight Pvt. Ltd.",generated_at=stamp(),
                objective="Reconstruct recorded activity, assess competing explanations and examine which evidence supports each conclusion.",
                sources=overview["sources"],uploads=uploads,observations=observations,timeline=timeline,
                facts=findings,graph=graph,hypotheses=overview["hypotheses"],rules=overview["rules"],
                excluded=overview["excluded"],dependency=overview["diff"],simulation=exercise,
                assumptions=["Clock warnings and original times are attached to individual records.",
                             "File admission and entity matching establish provenance, with authorization and individual attribution assessed separately."],
                limits=["The incident narrative is limited to records admitted by the configured rules.",
                        "Uploaded sources require schema review before their observations can influence case-specific conclusions.",
                        "Simulations are fictional control evaluations."],
                unresolved={k:v["gap"] for k,v in overview["hypotheses"].items()},next_steps=investigation_steps)

def pdf(report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, KeepTogether
    stream=io.BytesIO()
    doc=SimpleDocTemplate(stream,pagesize=A4,title="TRACE//ZERO Investigation Report",author="TRACE//ZERO",
                          leftMargin=50,rightMargin=50,topMargin=48,bottomMargin=52)
    styles=getSampleStyleSheet()
    styles["Title"].textColor=colors.HexColor("#144c58")
    styles["Heading2"].textColor=colors.HexColor("#144c58")
    story=[]
    def para(value,kind="BodyText"):return Paragraph(escape(str(value)).replace("\n","<br/>"),styles[kind])
    def section(heading):story.extend([Spacer(1,12),para(heading,"Heading2")])
    def add(value):story.append(para(value))
    story.append(para("TRACE//ZERO","Title"))
    add("Investigation report | "+report["case"]+" | "+report["generated_at"])
    add(report["organization"])
    section("Investigation objective");add(report["objective"])
    section("Evidence inventory and validation")
    for sid,s in report["sources"].items():
        add(f"{sid} | {s['filename']} | "+", ".join(f"{k} {v}" for k,v in s["counts"].items())+(" | "+s["reason"] if s["reason"] else ""))
    for s in report["uploads"]:add(f"Uploaded | {s['id']} | {s['filename']} | {s['state']} | {s['counts']}")
    section("Hypothesis comparisons")
    for h,value in report["hypotheses"].items():
        add(f"{h}  {value['name']} | {value['status']} | {value['counts']}")
    section("Evidence dependency")
    d=report["dependency"]
    add("Challenged references: "+(", ".join(report["excluded"]) or "None"))
    add(f"{len(d['lost'])} withdrawn, {len(d['added'])} new, {len(d['changed'])} changed, {d['surviving']} retained.")
    for f in d["lost"]+d["changed"]:add(f"{f['rule']} | {f['title']} | {', '.join(f['refs'])}")
    section("Case findings and graph trail")
    for f in report["facts"]:
        story.append(KeepTogether([para(f"{f['rule']} | {f['title']}","Heading3"),para(f["summary"]),
                      para(f"{f['kind']} | {', '.join(f['refs'])} | {f['effects']}")]))
    section("Reconstructed timeline")
    for r in report["timeline"]:add(f"{r['utc']} | {r['ref']} | {r['actor'] or 'Unknown'} | {r['action'] or r['type']} | {r['time_note']}")
    section("Security-control simulation")
    sim=report["simulation"]
    if sim:
        add(f"SYNTHETIC | {sim['id']} | {sim['label']} | {sim['result']['baseline']} baseline, {sim['result']['decision']} action")
        for r in sim["events"]:add(f"{r['utc']} | {r['ref']} | {r['action']} | {r['raw']}")
        for h,v in sim["analysis"]["hypotheses"].items():add(f"{h} | {v['status']} | {v['explanation']} | {', '.join(v['refs'])}")
        add("Challenged simulation references: "+(", ".join(sim["analysis"]["excluded"]) or "None"))
    else:add("No simulation selected for this export.")
    section("Assumptions, limits and open questions")
    for item in report["assumptions"]+report["limits"]+list(report["unresolved"].values()):add(item)
    section("Recommended next investigative steps")
    for item in report["next_steps"]:add(item)
    def footer(canvas,doc):
        canvas.setFont("Helvetica",9);canvas.setFillColor(colors.HexColor("#42606a"))
        canvas.drawString(50,30,"TRACE//ZERO   /   "+report["case"])
        canvas.drawRightString(A4[0]-50,30,str(doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()
