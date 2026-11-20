"use strict";
const $ = s => document.querySelector(s);
const content = $("#content");
const views = {"Overview":"◫","Risk sentinel":"◈","Scenario lab":"◉","Evidence vault":"▤","Evidence graph":"⌘","Timeline":"◷","Hypothesis arena":"◇","Dependency analysis":"⤨","External context":"↗","Investigation reports":"⇩"};
const titles={"Risk sentinel":"Risk Sentinel","Scenario lab":"Scenario Lab","Evidence vault":"Evidence Vault","Evidence graph":"Investigation Graph","Hypothesis arena":"Hypothesis Arena","Dependency analysis":"Dependency Analysis","External context":"External Context","Investigation reports":"Investigation Reports"};
const state = {view:"Overview", excluded:new Set(), selected:"", h:"H1", direction:"all", source:"", quality:"", query:"", offset:0, start:"", end:"", entity:"", eventType:"", relationship:"observed", hypothesisScopes:{}};
let model, revision=0, graphResize;
const esc=v=>String(v??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const tag=(s,cl="")=>'<span class="tag '+cl+'">'+esc(s)+'</span>';
const refs=items=>items.map(r=>'<button class="ref" data-ref="'+esc(r)+'">'+esc(r)+'</button>').join(" ");
const opt=(v,label,current)=>'<option value="'+esc(v)+'" '+(current===v?"selected":"")+'>'+esc(label)+'</option>';
const n=v=>Number(v).toLocaleString();
const params=extra=>new URLSearchParams({exclude:[...state.excluded].join(","),hyp_rules:JSON.stringify(state.hypothesisScopes),...extra});
async function get(route,extra={}){const res=await fetch("/api/"+route+"?"+params(extra));if(!res.ok)throw Error("Unable to load "+route+" ("+res.status+")");return res.json()}
function head(title,description){return '<div class="kicker">HARBOR &amp; FINCH FREIGHT &nbsp; / &nbsp; CR-26-047</div><h1>'+title+'</h1><p class="intro">'+description+'</p>'+(state.excluded.size?'<div class="scenario">Scenario active · '+esc([...state.excluded].join(", "))+' challenged.</div>':'')}
function stats(items){return '<div class="stats">'+items.map(([v,l])=>'<div class="stat"><strong>'+esc(v)+'</strong><span>'+esc(l)+'</span></div>').join("")+'</div>'}
function factCard(f){return '<div class="fact"><div class="titleline">'+tag(f.rule)+tag(f.kind,f.kind==="candidate"?"amber":"")+'<h3>'+esc(f.title)+'</h3></div><p>'+esc(f.summary)+'</p>'+refs(f.refs)+' <button class="ref" data-fact="'+esc(f.id)+'">View graph ↗</button></div>'}
function bind(){document.querySelectorAll("[data-ref]").forEach(b=>b.onclick=()=>inspect(b.dataset.ref));document.querySelectorAll("[data-fact]").forEach(b=>b.onclick=()=>{state.selected=b.dataset.fact;desk.graphTab="case";go("Evidence graph")})}
function nav(){ $("#nav").innerHTML=Object.entries(views).map(([v,i])=>'<button class="'+(v===state.view?"active":"")+'" data-v="'+v+'"><span class="ico">'+i+'</span>'+(titles[v]||v)+'</button>').join("");document.querySelectorAll("[data-v]").forEach(b=>b.onclick=()=>go(b.dataset.v));$("#report").href="#reports";$("#report").onclick=e=>{e.preventDefault();go("Investigation reports")}}
function go(v){state.view=v;state.offset=0;render().catch(showError)}
function showError(e){content.innerHTML='<div class="note">'+esc(e.message)+'</div><button class="btn" onclick="location.reload()">Reload workspace</button>'}
async function reload(){const token=++revision;const data=await get("overview");if(token!==revision)return;model=data;await render()}
async function render(){
 const token=++revision;graphResize?.disconnect();nav();
 if(typeof renderModule==="function"&&await renderModule(token))return;
 if(state.view==="Evidence graph")return graphView(token);
 if(state.view==="Timeline")return tableView(token);
 if(state.view==="Hypothesis arena")arena();else dependency();
 bind()
}
async function graphView(token){
 const facts=model.facts, f=facts.find(x=>x.id===state.selected)||facts.find(x=>x.rule==="R02")||facts[0];
 content.innerHTML=head("Investigation Graph","Trace an assessment back to the records and fields that produced it.")+
 stats([[n(Object.values(model.sources).filter(s=>s.state==="available").length),"Available evidence sources"],[n(model.records),"Indexed observations"],[n(facts.length),"Active rule results"]]);
 if(!f){content.insertAdjacentHTML("beforeend",'<div class="note">No rule has sufficient input in this scenario. Restore evidence in Dependency analysis.</div>');return}
 state.selected=f.id;
 const g=await get("graph",{id:f.id});if(token!==revision)return;
 const ordered=[...facts].sort((a,b)=>a.rule.localeCompare(b.rule));
 content.insertAdjacentHTML("beforeend",'<section class="panel"><div class="phead"><h2>Evidence trail</h2><select id="pick" aria-label="Choose assessment">'+ordered.map(x=>opt(x.id,x.rule+" · "+x.title+" · "+x.refs[0],f.id)).join("")+'</select></div><div class="bodypad"><div class="titleline">'+tag(f.rule)+tag(f.kind,f.kind==="candidate"?"amber":"")+'</div><h2 style="margin-top:10px">'+esc(f.title)+'</h2><p>'+esc(f.summary)+'</p></div><div class="graphwrap"><div class="graph" id="graph"><canvas aria-hidden="true"></canvas></div></div><div class="bodypad"><small>Rule condition</small><p>'+esc(model.rules[f.rule])+'</p><details><summary>Inspect '+g.edges.length+' relationships</summary>'+g.edges.map(e=>'<p><b>'+esc(e.label)+'</b> · '+esc(e.from)+' → '+esc(e.to)+' · '+esc(e.status)+' · '+esc(e.rule)+(e.explanation?" · "+esc(e.explanation):"")+' '+refs(e.refs)+'</p>').join("")+'</details></div></section>');
 $("#pick").onchange=e=>{state.selected=e.target.value;go("Evidence graph")};
 const graph=$("#graph");
 const cols=[["SOURCE RECORD",["evidence"]],["OBSERVATION",["observation"]],["ASSESSMENT",["assessment"]],["SUBJECT & HYPOTHESES",["entity","hypothesis"]]];
 cols.forEach(([name,types])=>{const col=document.createElement("div");col.className="graphcol";col.innerHTML='<div class="graphhead">'+name+'</div>';g.nodes.filter(x=>types.includes(x.type)).forEach(x=>{const b=document.createElement("button");b.className="node "+x.type;b.dataset.id=x.id;b.textContent=x.label;b.onclick=()=>{if(["evidence","observation"].includes(x.type))inspect(x.id.replace(/^obs:/,""));else if(x.type==="hypothesis"){state.h=x.id;desk.arenaTab="case";go("Hypothesis arena")}else{document.querySelector("details").open=true;document.querySelector("details").scrollIntoView({block:"nearest"})}};col.append(b)});graph.append(col)});
 function lines(){const c=graph.querySelector("canvas"),rect=graph.getBoundingClientRect(),d=window.devicePixelRatio||1;c.width=rect.width*d;c.height=rect.height*d;c.style.width=rect.width+"px";c.style.height=rect.height+"px";const ctx=c.getContext("2d");ctx.scale(d,d);let nodes=new Map([...graph.querySelectorAll(".node")].map(x=>[x.dataset.id,x.getBoundingClientRect()]));for(const e of g.edges){let a=nodes.get(e.from),b=nodes.get(e.to);let x=a.right-rect.left,y=a.top+a.height/2-rect.top,z=b.left-rect.left,w=b.top+b.height/2-rect.top;ctx.strokeStyle=e.status==="CANDIDATE"?"#a3793e":"#8da797";ctx.setLineDash(e.status==="CANDIDATE"?[3,3]:[]);ctx.beginPath();ctx.moveTo(x,y);ctx.bezierCurveTo((x+z)/2,y,(x+z)/2,w,z,w);ctx.stroke()}}
 graphResize=new ResizeObserver(lines);graphResize.observe(graph);lines();bind()
}
function arena(){
 content.innerHTML=head("Hypothesis Arena","Each rule applies to its own records. Supporting and contradicting results can coexist across different operations.")+
 '<div class="cards">'+Object.entries(model.hypotheses).map(([id,h])=>'<div class="hcard">'+tag(id)+'<h3>'+esc(h.name)+'</h3>'+tag(h.status,h.status==="MIXED"?"amber":"")+'<p>'+h.counts.supports+' supporting · '+h.counts.contradicts+' contradicting</p><button class="btn" data-h="'+id+'">Inspect '+id+' →</button></div>').join("")+'</div>';
 const controls=hypothesisControls(model);
 const h=model.hypotheses[state.h],group=model.facts.filter(f=>f.effects[state.h]&&(state.direction==="all"||f.effects[state.h]===state.direction));
 content.insertAdjacentHTML("beforeend",'<div class="phead"><h2>'+esc(state.h)+' · Rule results</h2><select id="dir" aria-label="Evidence direction">'+["all","supports","contradicts","relevant","gap"].map(d=>opt(d,d,state.direction)).join("")+'</select></div>'+controls+'<div class="note"><b>Open question</b> · '+esc(h.gap)+'</div><div class="facts">'+(group.map(f=>'<div>'+tag(f.effects[state.h],"amber")+factCard(f)+'</div>').join("")||"No matching results.")+'</div>');
 document.querySelectorAll("[data-h]").forEach(b=>b.onclick=()=>{state.h=b.dataset.h;state.direction="all";render()});$("#dir").onchange=e=>{state.direction=e.target.value;render()};bindHypothesisControls()
}
function dependency(){
 const d=model.diff;
 content.innerHTML=head("Dependency Analysis","Challenge one or more sources, then compare the new results with the full case. Excluding evidence affects the current analysis. Original files remain intact and available for inspection.")+
 '<section class="panel"><div class="phead"><h2>Challenge evidence</h2><button class="light" id="reset">Restore full case</button></div><div class="bodypad"><div class="sourcegrid">'+Object.entries(model.sources).map(([s,i])=>'<label><input type="checkbox" value="'+s+'" '+(state.excluded.has(s)?"checked":"")+'>'+s+' · '+esc(i.filename.slice(4).split(".")[0].replaceAll("_"," "))+'</label>').join("")+'</div><div class="tools"><button class="primary" id="apply">Recompute scenario</button></div><small>Individual records can also be challenged from the record inspector.</small></div></section>'+
 stats([[d.lost.length,"Results withdrawn"],[d.surviving,"Results unchanged"],[d.added.length,"New results or gaps"]])+
 '<div class="panel"><div class="phead"><h2>Hypothesis changes</h2></div><div class="bodypad">'+Object.entries(model.hypotheses).map(([h,x])=>'<p><b>'+h+'</b> &nbsp; '+esc(d.baseline[h].status)+' → '+esc(x.status)+' · '+x.counts.supports+' supporting, '+x.counts.contradicts+' contradicting</p>').join("")+'</div></div>'+
 [["Withdrawn results",d.lost],["Newly visible results",d.added],["Changed witnesses",d.changed]].map(([title,arr])=>arr.length?'<details class="panel bodypad"><summary>'+title+' ('+arr.length+')</summary>'+arr.map(f=>'<p>'+tag(f.rule)+' '+esc(f.title)+' '+refs(f.refs)+'</p>').join("")+'</details>':"").join("")+'<details class="panel bodypad"><summary>Surviving evidence trails</summary>'+model.facts.filter(f=>!d.added.some(x=>x.id===f.id)).map(f=>'<p>'+tag(f.rule)+' '+esc(f.title)+' '+refs(f.refs)+'</p>').join("")+'</details>';
 $("#reset").onclick=()=>{state.excluded.clear();reload().catch(showError)};$("#apply").onclick=()=>{document.querySelectorAll(".sourcegrid input").forEach(b=>b.checked?state.excluded.add(b.value):state.excluded.delete(b.value));reload().catch(showError)}
}
async function tableView(token){
 const time=state.view==="Timeline", rows=await get("records",{source:state.source,quality:state.quality,q:state.query,offset:state.offset,timeline:time?"1":"0",event_type:state.eventType,entity:state.entity,start:state.start,end:state.end,relationship:state.relationship});if(token!==revision)return;
 content.innerHTML=head(time?"Timeline":"Case Evidence Vault",time?"Recorded events in UTC order. Open a row to compare its original clock and normalized time.":"Search all source records, inspect the original fields and review admission decisions.")+
 (time?timelineSwitch():"")+(!time?'<details class="panel bodypad"><summary>Source inventory and integrity · 20 items</summary>'+Object.entries(model.sources).map(([s,i])=>'<p><b>'+s+'</b> '+esc(i.filename)+' · '+esc(i.state)+' '+esc(i.reason)+'<br><small>'+esc(JSON.stringify(i.counts))+'</small><br><small style="overflow-wrap:anywhere">SHA-256 '+esc(i.sha256)+'</small></p>').join("")+'</details>':'')+
 '<form class="tools" id="filter"><input aria-label="Search records" placeholder="Search a request ID, actor or value" id="q" value="'+esc(state.query)+'"><select id="src" aria-label="Source">'+opt("","All sources",state.source)+Object.keys(model.sources).map(s=>opt(s,s,state.source)).join("")+'</select><select id="quality" aria-label="Quality">'+opt("","All quality flags",state.quality)+["VALID","PARTIAL","AMBIGUOUS","QUARANTINED","REJECTED","DUPLICATE"].map(s=>opt(s,s,state.quality)).join("")+'</select>'+timelineFilters(rows,time)+'<button class="primary">Search</button></form>'+
 '<section class="panel"><div class="phead"><h2>'+n(rows.total)+(rows.total===1?' record':' records')+'</h2></div><div class="scroll"><table><thead><tr><th>Record</th><th>Recorded time · UTC</th><th>Actor / action</th><th>Target</th><th>Quality</th>'+(time?'<th>Linked as</th>':'')+'</tr></thead><tbody>'+rows.rows.map(r=>'<tr><td>'+refs([r.ref])+'</td><td>'+esc(r.utc)+'<br><small>'+esc(r.clock)+'</small></td><td>'+esc(r.actor)+'<br><small>'+esc(r.action||r.label)+'</small></td><td>'+esc(r.target)+'</td><td>'+tag(r.quality,r.quality==="VALID"?"":"amber")+'</td>'+(time?'<td>Observed'+(r.relations.length?' · '+esc(r.relations.join(', ')):'')+'</td>':'')+'</tr>').join("")+'</tbody></table></div><div class="foots"><button id="prev" class="btn" '+(state.offset===0?"disabled":"")+'>← Previous</button><small>'+n(rows.total?state.offset+1:0)+'–'+n(state.offset+rows.rows.length)+' of '+n(rows.total)+'</small><button id="next" class="btn" '+(state.offset+40>=rows.total?"disabled":"")+'>Next →</button></div></section>';
 $("#filter").onsubmit=e=>{e.preventDefault();state.source=$("#src").value;state.quality=$("#quality").value;state.query=$("#q").value;state.start=$("#date-start").value;state.end=$("#date-end").value;state.eventType=$("#event-type").value;state.entity=$("#entity-filter")?.value||"";state.relationship=$("#relation-filter")?.value||"observed";state.offset=0;render().catch(showError)};
 $("#prev").onclick=()=>{state.offset-=40;render()};$("#next").onclick=()=>{state.offset+=40;render()};bind();bindDataTabs()
}
async function inspect(ref){
 try{const r=await get("record",{ref});$("#inspect").innerHTML='<div class="titleline">'+tag(r.quality)+' '+tag(r.sid)+'</div><h2>'+esc(r.ref)+'</h2><p>'+esc(r.label)+' · '+esc(r.note)+'</p><p><small>Original</small> '+esc(r.original)+' &nbsp; <small>UTC</small> '+esc(r.utc)+'<br><small>'+esc(r.clock)+'</small></p><pre>'+esc(JSON.stringify(r.raw,null,2))+'</pre><h3>Linked identifiers</h3>'+
 (r.entities.map(e=>'<p><b>'+esc(e.system)+' · '+esc(e.type)+'</b> '+esc(e.value)+'<br><small>'+n(e.count)+' other records · '+esc(e.rule)+'</small><br>'+refs(e.refs)+'</p>').join('')||'<p class="muted">No eligible typed identifier for this observation.</p>')+'<h3>External context</h3>'+
 (r.context.map(c=>'<p>'+tag(c.source_ref)+' '+esc(c.excerpt)+'</p><details><summary>Lookup provenance</summary><pre>'+esc(JSON.stringify(c,null,2))+'</pre></details>').join("")||'<p class="muted">No applicable offline reference for this record in the active scenario.</p>')+
 '<div class="tools"><button id="challenge" class="btn" '+(state.excluded.has(r.sid)?"disabled":"")+'>'+(state.excluded.has(r.sid)?"Source challenged":r.excluded?"Restore this record":"Challenge this record")+'</button></div>';
 bind();if(!$("#detail").open)$("#detail").showModal();$("#detail").scrollTop=0;$("#challenge").onclick=()=>{state.excluded.has(ref)?state.excluded.delete(ref):state.excluded.add(ref);$("#detail").close();desk.dependencyTab="case";state.view="Dependency analysis";reload().catch(showError)}
 }catch(e){showError(e)}
}
$("#close").onclick=()=>$("#detail").close();
window.addEventListener("DOMContentLoaded",()=>reload().catch(showError));
