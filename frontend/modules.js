"use strict";
const desk={scenario:"denied_bank",run:"",simExcluded:new Set(),vaultTab:"case",timelineTab:"case",graphTab:"case",arenaTab:"case",upload:"",uploadOffset:0,uploadFilter:{}};
let catalogPromise;
const moduleIDs={"H1":"Integration misuse","H2":"Excessive access scope","H3":"Unlinked or separate events"};
const statusClass=v=>["RESTRICT","CONTAIN","HIGH","CRITICAL","REJECTED","QUARANTINED"].includes(v)?"hot":
    ["VERIFY","MODERATE","AMBIGUOUS","PARTIAL","UNRESOLVED","DUPLICATE","MIXED"].includes(v)?"amber":"";
const pill=v=>tag(v,statusClass(v));
const section=(name,body,actions="")=>'<section class="panel"><div class="phead"><h2>'+esc(name)+'</h2>'+actions+'</div><div class="bodypad">'+body+'</div></section>';
const navTo=(view,label,style="btn")=>'<button class="'+style+'" data-jump="'+view+'">'+esc(label)+'</button>';
const notice=(message)=>'<div class="note">'+esc(message)+'</div>';
const simBadge=()=>tag("SYNTHETIC EXERCISE","amber");
const originLabel=origin=>origin==="case"?"Case evidence":origin==="uploaded"?"Local uploads":"Synthetic exercises";
const simParams=()=>({id:desk.run,sim_exclude:[...desk.simExcluded].join(",")});
const reportParams=()=>({run:desk.run,sim_exclude:[...desk.simExcluded].join(",")});
const byStatus=["VALID","PARTIAL","AMBIGUOUS","DUPLICATE","QUARANTINED","REJECTED"];
function tabs(key,values){
    return '<div class="tabbar" aria-label="Evidence origin">'+values.map(v=>'<button data-tab="'+key+'" data-value="'+v+'" class="'+(desk[key]===v?"on":"")+'">'+originLabel(v)+'</button>').join("")+'</div>';
}
function bindDataTabs(){
    document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{
        desk[b.dataset.tab]=b.dataset.value;desk.uploadOffset=0;render().catch(showError)
    });
}
function bindModule(){
    bind();bindDataTabs();
    document.querySelectorAll("[data-jump]").forEach(b=>b.onclick=()=>go(b.dataset.jump));
    document.querySelectorAll("[data-upload-ref]").forEach(b=>b.onclick=()=>inspectUpload(b.dataset.uploadRef));
    document.querySelectorAll("[data-sim-ref]").forEach(b=>b.onclick=()=>inspectSim(b.dataset.simRef));
}
async function post(path,payload,headers={}){
    const file=payload instanceof File;
    const response=await fetch("/api/"+path,{method:"POST",headers:{"X-Trace-Local":"1",...(!file&&{"Content-Type":"application/json"}),...headers},body:file?payload:JSON.stringify(payload)});
    const data=await response.json();
    if(!response.ok)throw Error(data.error||"Request failed");
    return data;
}
function act(form,callback){
    form.onsubmit=async event=>{
        event.preventDefault();
        const button=form.querySelector('button[type="submit"]');
        const message=form.querySelector("[role=status]");
        if(button)button.disabled=true;
        if(message)message.textContent="";
        try{await callback(new FormData(form));}
        catch(error){if(message)message.textContent=error.message;else showError(error);}
        finally{if(button)button.disabled=false;}
    };
}
const catalog=()=>catalogPromise||(catalogPromise=get("sentinel/catalog").catch(error=>{catalogPromise=null;throw error;}));
function pickRun(id){desk.run=id;desk.simExcluded.clear();}
function runSelector(runs,id="run-select"){
    return '<label class="control">Recorded exercise<select id="'+id+'">'+opt("","Choose a run",desk.run)+runs.map(r=>opt(r.id,r.label+" · "+r.id,desk.run)).join("")+'</select></label>';
}
const selectRun=()=>{const select=$("#run-select");if(select)select.onchange=()=>{pickRun(select.value);render().catch(showError)};};
async function selectedRun(){return desk.run?await get("sentinel/run",simParams()):null;}
function timelineSwitch(){return tabs("timelineTab",["case","uploaded","synthetic"]);}
function timelineFilters(rows,time){
    const dates='<div class="datefilters"><label>From <input id="date-start" type="date" value="'+esc(state.start)+'"></label><label>To <input id="date-end" type="date" value="'+esc(state.end)+'"></label></div>';
    return '<select id="event-type" aria-label="Record type">'+opt("","All record types",state.eventType)+rows.types.map(x=>opt(x,x,state.eventType)).join("")+'</select>'+dates+
        (time?'<input id="entity-filter" aria-label="Filter entity" placeholder="Actor or resource" value="'+esc(state.entity)+'"><select id="relation-filter" aria-label="Relationship status">'+[["observed","Observed events"],["inference","Inferred links"],["candidate","Candidate links"],["unresolved","Unresolved links"]].map(([a,b])=>opt(a,b,state.relationship)).join("")+'</select>':"");
}

async function renderModule(token){
    switch(state.view){
        case "Overview":await overviewModule(token);break;
        case "Risk sentinel":await riskModule(token);break;
        case "Scenario lab":await scenarioModule(token);break;
        case "Evidence vault":
            if(desk.vaultTab==="case"){
                await tableView(token);
                if(token===revision){content.querySelector(".intro").insertAdjacentHTML("afterend",tabs("vaultTab",["case","uploaded"]));bindDataTabs();}
            }else await uploadedModule(token);
            break;
        case "Timeline":
            if(desk.timelineTab==="case")return false;
            if(desk.timelineTab==="uploaded")await uploadedModule(token,true);
            else await simulationPage(token,"timeline");
            break;
        case "Evidence graph":
            if(desk.graphTab==="synthetic")await simulationPage(token,"graph");
            else {
                await graphView(token);
                if(token===revision){content.querySelector(".intro").insertAdjacentHTML("afterend",tabs("graphTab",["case","synthetic"]));bindDataTabs();}
            }
            break;
        case "Hypothesis arena":
            if(desk.arenaTab==="synthetic")await simulationPage(token,"arena");
            else {arena();content.querySelector(".intro").insertAdjacentHTML("afterend",tabs("arenaTab",["case","synthetic"]));bindModule();}
            break;
        case "Dependency analysis":
            if(desk.dependencyTab==="sim")await simulationPage(token,"dependency");
            else {dependency();content.querySelector(".intro").insertAdjacentHTML("afterend",dependencySwitch());bindDependencySwitch();}
            break;
        case "External context":contextModule();break;
        case "Investigation reports":await reportModule(token);break;
        default:return false;
    }
    return true;
}

async function overviewModule(token){
    const [uploads,runs]=await Promise.all([get("vault/inventory"),get("sentinel/runs")]);
    if(token!==revision)return;
    const sourceCount=Object.values(model.sources).filter(x=>x.state==="available").length;
    const mainFinding=model.facts.find(f=>f.rule==="R02");
    content.innerHTML=head("Investigation overview","Review the case record, run a local security exercise and test which conclusions survive an evidence challenge.")+
        stats([[sourceCount,"Available case sources"],[n(model.records),"Indexed case records"],[n(runs.length),"Recorded synthetic exercises"]])+
        '<div class="overview-grid">'+section("CR-26-047",'<div class="titleline">'+tag("CASE EVIDENCE")+'</div><p>Harbor &amp; Finch Freight Pvt. Ltd.</p>'+
        (mainFinding?factCard(mainFinding):notice("The current evidence selection changes the available findings."))+navTo("Evidence graph","Open Investigation Graph"))+
        section("Risk Sentinel",simBadge()+'<h3>Can this identity perform the action?</h3><p>Compare the baseline session checks with the permission and action-level decision. The preset includes a demo user whose sign-in checks pass and whose request is restricted.</p>'+
        navTo("Scenario lab","Run a scenario","primary")+demoForm()+(runs.length?'<p><small>Latest recorded run</small><br>'+esc(runs[0].label)+' · '+pill(runs[0].decision)+'</p>':""))+'</div>'+
        '<div class="overview-grid">'+section("Hypotheses",Object.entries(model.hypotheses).map(([id,h])=>'<div class="overview-line"><span>'+id+' · '+esc(h.name)+'</span>'+pill(h.status)+'</div>').join("")+navTo("Hypothesis arena","Compare hypotheses"))+
        section("Evidence Vault",'<p>'+n(uploads.length)+' locally uploaded files</p><p>Inspect source hashes, admission states and original record references.</p>'+navTo("Evidence vault","Browse the vault"))+'</div>';
    bindModule();bindDemo();
}

function demoForm(){
    return '<form id="load-demo" class="tools"><button class="btn" type="submit">Load repeatable demo</button><span role="status" class="feedback"></span></form>';
}
function bindDemo(){
    if(!$("#load-demo"))return;
    act($("#load-demo"),async()=>{const run=await post("sentinel/demo",{});pickRun(run.id);go("Risk sentinel");});
}
function hypothesisControls(model){
    const active=state.hypothesisScopes[state.h]||Object.keys(model.rules);
    return '<details class="panel bodypad"><summary>Configure evaluation scope for '+state.h+'</summary><form id="hyp-rules"><p>Select rules eligible to affect this hypothesis in the current investigation.</p>'+
        '<div class="sourcegrid">'+Object.entries(model.rules).map(([id,desc])=>'<label><input type="checkbox" name="rule" value="'+id+'" '+(active.includes(id)?"checked":"")+'><b>'+id+'</b> '+esc(desc)+'</label>').join("")+'</div>'+
        '<div class="tools"><button class="primary" type="submit">Apply rule selection</button><button type="button" class="btn" id="scope-reset">Restore default rules</button><span role="status" class="feedback"></span></div></form></details>';
}
function bindHypothesisControls(){
    act($("#hyp-rules"),async f=>{state.hypothesisScopes[state.h]=f.getAll("rule");await reload();});
    $("#scope-reset").onclick=()=>{delete state.hypothesisScopes[state.h];reload().catch(showError);};
}

const settingsLabels={familiar_network:"Familiar network",recognized_device:"Recognized device",business_hours:"Expected sign-in hours",
                      verified:"Independent verification complete",sensitive:"Sensitive resource",broad_scope:"Permission scope exceeds declared need",repeated:"Repeated suspicious activity"};
function scenarioForm(meta){
    const current=meta.scenarios.find(s=>s.id===desk.scenario)||meta.scenarios[0];
    const cfg=current.settings;
    const options=(list,map,selected)=>list.map(k=>opt(k,map(k),selected)).join("");
    return '<form id="run-form" class="stack"><label class="control">Fixture<select id="scenario" name="scenario">'+meta.scenarios.map(s=>opt(s.id,s.label,desk.scenario)).join("")+'</select></label>'+
        '<div class="field-grid"><label class="control">Simulated sign-in<select name="identity">'+options(Object.keys(meta.identities),k=>meta.identities[k].label,cfg.identity)+'</select></label>'+
        '<label class="control">Requested operation<select name="action">'+options(Object.keys(meta.actions),k=>meta.actions[k],cfg.action)+'</select></label>'+
        '<label class="control">Recorded event volume<input name="volume" type="number" min="1" max="10000" value="'+cfg.volume+'" required></label></div>'+
        '<fieldset class="settings"><legend>Observed context</legend>'+Object.entries(settingsLabels).map(([k,v])=>'<label><input type="checkbox" name="'+k+'" '+(cfg[k]?"checked":"")+'>'+v+'</label>').join("")+'</fieldset>'+
        '<div class="tools"><button class="primary" type="submit">Run and record simulation</button><span role="status" class="feedback"></span></div></form>';
}
async function scenarioModule(token){
    const meta=await catalog();
    if(token!==revision)return;
    content.innerHTML=head("Scenario Lab","Choose a demo identity and an operation. The local evaluator records separate sign-in, permissions, request and decision events.")+
        '<div class="mode-banner">'+simBadge()+'<span>Use fictional identities and banking records in this exercise.</span></div>'+
        section("Configure the exercise",scenarioForm(meta))+
        section("Demo permission matrix",'<div class="scroll"><table><thead><tr><th>Demo identity</th><th>Granted actions</th></tr></thead><tbody>'+
        Object.entries(meta.identities).map(([id,item])=>'<tr><td>'+esc(item.label)+'</td><td>'+esc(item.actions.map(a=>meta.actions[a]).join(", "))+'</td></tr>').join("")+'</tbody></table></div>');
    $("#scenario").onchange=e=>{desk.scenario=e.target.value;render().catch(showError);};
    act($("#run-form"),async form=>{
        const settings={identity:form.get("identity"),action:form.get("action"),volume:Number(form.get("volume"))};
        Object.keys(settingsLabels).forEach(key=>{settings[key]=form.has(key)});
        const run=await post("sentinel/run",{scenario:form.get("scenario"),settings});
        pickRun(run.id);go("Risk sentinel");
    });
}
function metrics(data){
    const percent=(count,total)=>total?(100*count/total).toFixed(1)+"% ("+count+"/"+total+")":"—";
    const columns=Object.entries(data.counts).map(([name,v])=>({name,fp:percent(v.fp,v.fp+v.tn),fn:percent(v.fn,v.fn+v.tp),tp:percent(v.tp,v.tp+v.fn)}));
    return '<p class="muted">Fixed labels cover '+data.size+' fixtures. Positive labels identify requests expected to require restriction or containment. The baseline predicts from sign-in and volume flags. Edited runs are excluded from these metrics.</p>'+
        '<div class="scroll"><table><thead><tr><th>Evaluator</th><th>False positive rate</th><th>False negative rate</th><th>Detection rate</th></tr></thead><tbody>'+
        columns.map(c=>'<tr><td>'+esc(c.name)+'</td><td>'+c.fp+'</td><td>'+c.fn+'</td><td>'+c.tp+'</td></tr>').join("")+'</tbody></table></div>'+
        '<p>Response accuracy '+percent(data.correct,data.size)+' &nbsp;·&nbsp; Legitimate access recovery '+percent(...data.recovery)+'</p>'+
        '<details><summary>Inspect fixture results</summary><div class="scroll"><table><thead><tr><th>Fixture</th><th>Expected response</th><th>Observed response</th><th>Baseline</th></tr></thead><tbody>'+
        data.rows.map(row=>'<tr><td>'+esc(row.label)+'</td><td>'+esc(row.expected)+'</td><td>'+pill(row.actual)+'</td><td>'+esc(row.baseline)+'</td></tr>').join("")+'</tbody></table></div></details>';
}
function runResult(run){
    const r=run.result;
    const baseline='<div class="titleline">'+pill(r.baseline)+'<h3>Baseline session checks</h3></div><ul class="signal-list">'+r.checks.map(c=>'<li><b>'+esc(c.signal)+'</b> '+pill(c.flagged?"FLAGGED":"PASS")+'<br><small>'+esc(c.detail)+'</small></li>').join("")+'</ul><p><b>Outside baseline scope</b> '+esc(r.baseline_omissions.join(", "))+'</p>';
    const action='<div class="titleline">'+pill(r.risk)+' '+pill(r.authorized?"ACTION PERMITTED":"ACTION OUTSIDE ROLE")+'</div><h3>'+esc(r.response)+'</h3><p>Identity certainty · '+esc(r.identity_certainty)+'</p><ul class="signal-list">'+r.signals.map(x=>'<li>'+esc(x)+'</li>').join("")+'</ul>';
    return section(run.label,'<div class="mode-banner">'+simBadge()+'<span>'+esc(run.id)+(run.edited?" · edited settings":"")+'</span></div>'+
        '<div class="comparison"><div>'+baseline+'</div><div>'+action+'</div></div><p class="muted">'+esc(r.limitations)+'</p>');
}
function reviewForm(run){
    if(run.review)return '<p>'+pill(run.review.decision)+' '+esc(run.review.event.raw.note)+'</p>'+simRef(run.review.event.ref);
    if(run.result.decision==="ALLOW")return '<p>This operation was allowed in the exercise. Its decision remains in the event trail.</p>';
    return '<form id="review-form" class="stack"><label class="control">Review outcome<select name="outcome">'+opt("held","Hold for authorized review","held")+
        (run.result.decision==="VERIFY"&&run.result.authorized?opt("verified","Verification completed · allow and monitor",""):"")+'</select></label>'+
        '<label class="control">Reviewer note<textarea name="note" required maxlength="500" rows="2"></textarea></label>'+
        '<div class="tools"><button class="primary" type="submit">Record human review</button><span role="status" class="feedback"></span></div></form>';
}
async function riskModule(token){
    const [catalogData,runs,run]=await Promise.all([catalog(),get("sentinel/runs"),selectedRun()]);
    if(token!==revision)return;
    content.innerHTML=head("Risk Sentinel","A session may pass its context checks while a specific action falls outside the demo identity’s role.")+
        '<div class="tools">'+runSelector(runs)+navTo("Scenario lab","New simulation","primary")+'</div>'+demoForm()+
        (run?runResult(run)+section("Decision trail",eventsTable(run.events),'<button class="btn" id="sim-graph">Open simulation graph</button><button class="btn" id="open-sim">Challenge synthetic evidence</button>')+
        section("Review and recovery",reviewForm(run)) : notice("Create a simulation to compare its checks and inspect the decision trail."))+
        section("Fixture evaluation",metrics(catalogData.benchmark));
    if($("#review-form"))act($("#review-form"),async f=>{await post("sentinel/review",{id:desk.run,outcome:f.get("outcome"),note:f.get("note")});await render();});
    if($("#open-sim"))$("#open-sim").onclick=()=>{desk.dependencyTab="sim";go("Dependency analysis");};
    if($("#sim-graph"))$("#sim-graph").onclick=()=>{desk.graphTab="synthetic";go("Evidence graph");};
    selectRun();bindModule();bindDemo();
}
function simRef(ref){return '<button class="ref" data-sim-ref="'+esc(ref)+'">'+esc(ref)+'</button>'}
function eventsTable(events){
    return '<div class="scroll"><table><thead><tr><th>Reference</th><th>Timestamp</th><th>Actor</th><th>Operation</th><th>Resource</th><th>Status</th></tr></thead><tbody>'+
        events.map(r=>'<tr><td>'+simRef(r.ref)+'</td><td>'+esc(r.utc)+'</td><td>'+esc(r.actor)+'</td><td>'+esc(r.action)+'</td><td>'+esc(r.target)+'</td><td>'+pill(r.status)+'</td></tr>').join("")+'</tbody></table></div>';
}
async function inspectSim(ref){
    try{
        const run=await selectedRun();
        const r=run.events.find(x=>x.ref===ref);
        $("#inspect").innerHTML=simBadge()+'<h2>'+esc(r.ref)+'</h2><p>'+esc(r.action)+' · '+esc(r.utc)+'</p><pre>'+esc(JSON.stringify(r.raw,null,2))+'</pre>'+
            '<button class="btn" id="sim-toggle">'+(desk.simExcluded.has(ref)?"Restore evidence":"Challenge evidence")+'</button>';
        if(!$("#detail").open)$("#detail").showModal();
        $("#sim-toggle").onclick=()=>{desk.simExcluded.has(ref)?desk.simExcluded.delete(ref):desk.simExcluded.add(ref);$("#detail").close();desk.dependencyTab="sim";go("Dependency analysis");};
    }catch(error){showError(error);}
}
function dependencySwitch(){
    return '<div class="tabbar"><button id="deps-case" class="'+(desk.dependencyTab!=="sim"?"on":"")+'">Case evidence</button><button id="deps-sim" class="'+(desk.dependencyTab==="sim"?"on":"")+'">Synthetic exercises</button></div>';
}
function bindDependencySwitch(){
    $("#deps-case").onclick=()=>{desk.dependencyTab="case";render().catch(showError);};
    $("#deps-sim").onclick=()=>{desk.dependencyTab="sim";render().catch(showError);};
}
function simGraph(run){
    const active=run.analysis.relationships;
    return '<div class="sim-flow">'+run.events.map(r=>'<button class="node" data-sim-ref="'+esc(r.ref)+'"><small>'+esc(r.kind)+'</small><br>'+esc(r.action)+(desk.simExcluded.has(r.ref)?'<br>'+tag("CHALLENGED","amber"):"")+'</button>').join("")+'</div>'+
        '<div class="facts">'+active.map(e=>'<article class="fact">'+pill(e.status)+' '+tag(e.rule)+
        '<div class="edge-route">'+simRef(e.source)+'<span aria-label="linked to">→</span>'+simRef(e.target)+'</div>'+
        '<p>'+esc(e.explanation)+'</p><small>Supporting references</small> '+e.refs.map(simRef).join("")+'</article>').join("")+'</div>';
}
function simComparison(run){
    return section("Original and current evaluation",'<div class="scroll"><table><thead><tr><th>Hypothesis</th><th>Original</th><th>Current</th><th>Explanation</th></tr></thead><tbody>'+
        Object.entries(run.analysis.hypotheses).map(([id,r])=>'<tr><td>'+id+' · '+esc(moduleIDs[id])+'</td><td>'+pill(run.baseline.hypotheses[id].status)+'</td><td>'+pill(r.status)+'</td><td>'+esc(r.explanation)+'<br>'+r.refs.map(simRef).join("")+'</td></tr>').join("")+'</tbody></table></div>');
}
function simDependency(run){
    return section("Challenge exercise records",'<form id="sim-exclude"><div class="sourcegrid">'+run.events.map(r=>'<label><input type="checkbox" name="refs" value="'+esc(r.ref)+'" '+(desk.simExcluded.has(r.ref)?"checked":"")+'>'+esc(r.action)+'</label>').join("")+'</div><div class="tools"><button class="primary" type="submit">Recompute analysis</button><button class="btn" type="button" id="restore-sim">Restore all records</button></div></form>')+
        simComparison(run)+section("Relationships and record provenance",simGraph(run)+
        '<h3>Withdrawn · '+run.diff.withdrawn.length+'</h3>'+run.diff.withdrawn.map(e=>'<p>'+esc(e.rule)+' · '+esc(e.explanation)+' '+e.refs.map(simRef).join("")+'</p>').join("")+
        '<p>'+run.diff.retained.length+' relationships retain support.</p>');
}
async function simulationPage(token,mode){
    const [runs,run]=await Promise.all([get("sentinel/runs"),selectedRun()]);
    if(token!==revision)return;
    const modes={
        dependency:["Dependency Analysis","Temporarily exclude supporting records from the synthetic analysis. Original events stay available.",dependencySwitch(),simDependency],
        timeline:["Timeline","Inspect synthetic events in their generated order.",timelineSwitch(),value=>section("Synthetic event timeline",eventsTable(value.events.filter(r=>!desk.simExcluded.has(r.ref))))],
        graph:["Investigation Graph","Inspect the links between recorded exercise events and their supporting records.",tabs("graphTab",["case","synthetic"]),value=>section("Synthetic event relationships",simGraph(value))],
        arena:["Hypothesis Arena","Compare the configured explanations against the synthetic evidence selection.",tabs("arenaTab",["case","synthetic"]),simComparison]
    };
    const [title,description,modeTabs,body]=modes[mode];
    content.innerHTML=head(title,description)+modeTabs+simBadge()+runSelector(runs)+
        (run?body(run):notice("Choose a recorded exercise or create one in Scenario Lab.")+navTo("Scenario lab","Open Scenario Lab","primary"));
    if($("#sim-exclude"))act($("#sim-exclude"),async f=>{desk.simExcluded=new Set(f.getAll("refs"));await render();});
    if($("#restore-sim"))$("#restore-sim").onclick=()=>{desk.simExcluded.clear();render().catch(showError);};
    if(mode==="dependency")bindDependencySwitch();
    selectRun();bindModule();
}
function uploadRef(ref){return '<button class="ref" data-upload-ref="'+esc(ref)+'">'+esc(ref)+'</button>';}
function uploadForm(){
    return '<form id="upload-evidence" class="stack"><label class="control">Evidence file<input type="file" id="upload-file" accept=".csv,.json,.pdf,.xlsx" required></label>'+
        '<div class="tools"><button class="primary" type="submit">Preserve original and index</button><span role="status" class="feedback"></span></div></form>';
}
function uploadPicker(inventory){
    return '<label class="control">Source file<select id="use-upload">'+opt("","Choose a local upload",desk.upload)+inventory.map(s=>opt(s.id,s.filename+" · "+s.id,desk.upload)).join("")+'</select></label>';
}
function uploadFilters(){
    const f=desk.uploadFilter;
    return '<form id="upload-filter" class="tools"><input name="query" aria-label="Search uploaded records" value="'+esc(f.query||"")+'" placeholder="Search uploaded records">'+
        '<select name="status" aria-label="Admission status">'+opt("","All admission states",f.status||"")+byStatus.map(x=>opt(x,x,f.status)).join("")+'</select>'+
        '<select name="type" aria-label="Record type">'+opt("","All record types",f.type||"")+["Structured record","Spreadsheet row","Document page"].map(x=>opt(x,x,f.type)).join("")+'</select>'+
        '<div class="datefilters"><label>From <input name="start" type="date" value="'+esc(f.start||"")+'"></label><label>To <input name="end" type="date" value="'+esc(f.end||"")+'"></label></div>'+
        '<button class="primary" type="submit">Filter records</button></form>';
}
function uploadTable(source,body){
    const rows=body.rows;
    return '<div class="titleline">'+pill(source.state)+' '+tag("UPLOADED")+'<b>'+esc(source.filename)+'</b></div>'+
        '<p>'+esc(source.id)+' · '+n(source.size)+' bytes · '+esc(source.file_type)+' · '+esc(source.uploaded_at)+'</p>'+
        '<p class="hash"><small>SHA-256</small> '+esc(source.sha256)+'</p>'+
        (source.duplicate_of?notice("Duplicate content preserved. First copy "+source.duplicate_of+"."):source.error?notice(source.error):"")+
        '<div class="tools"><a class="btn" href="/api/vault/original?id='+encodeURIComponent(source.id)+'">Download original bytes</a>'+
        '<button type="button" class="btn" id="check-integrity">Verify SHA-256</button><span id="integrity-state" role="status"></span></div>'+
        uploadFilters()+
        '<div class="scroll"><table><thead><tr><th>Reference</th><th>Type</th><th>Original time</th><th>Normalized time</th><th>Admission</th><th>Reason</th></tr></thead><tbody>'+
        rows.map(r=>'<tr><td>'+uploadRef(r.ref)+'</td><td>'+esc(r.type)+'</td><td>'+esc(r.original)+'</td><td>'+esc(r.utc)+'</td><td>'+pill(r.status)+'</td><td>'+esc(r.reason)+'</td></tr>').join("")+'</tbody></table></div>'+
        '<div class="foots"><button type="button" class="btn" id="upload-prev" '+(desk.uploadOffset===0?"disabled":"")+'>← Previous</button><small>'+n(body.total)+' matching records</small><button type="button" class="btn" id="upload-next" '+(desk.uploadOffset+rows.length>=body.total?"disabled":"")+'>Next →</button></div>';
}
async function uploadedModule(token,timeline=false){
    const inventory=await get("vault/inventory");
    const chosen=inventory.find(s=>s.id===desk.upload);
    const rows=chosen?await get("vault/rows",{id:chosen.id,timeline:timeline?"1":"0",offset:desk.uploadOffset,...desk.uploadFilter}):null;
    if(token!==revision)return;
    content.innerHTML=head(timeline?"Timeline":"Evidence Vault",timeline?"Only uploaded records with usable timezone-aware times appear in this timeline. The Evidence Vault retains every indexed record.":"Upload and inspect originals, record locators, integrity and admission decisions.")+
        (timeline?timelineSwitch():tabs("vaultTab",["case","uploaded"]))+
        (!timeline?section("Upload evidence",uploadForm()):"")+
        (inventory.length?section("Local uploads",uploadPicker(inventory)+(chosen?uploadTable(chosen,rows):"")):notice("No files have been uploaded."));
    if($("#upload-evidence"))act($("#upload-evidence"),async()=>{
        const file=$("#upload-file").files[0];
        if(!file)throw Error("Choose a file");
        const saved=await post("vault/upload",file,{"X-File-Name":encodeURIComponent(file.name)});
        desk.upload=saved.id;desk.uploadOffset=0;desk.uploadFilter={};await render();
    });
    if($("#use-upload"))$("#use-upload").onchange=e=>{desk.upload=e.target.value;desk.uploadOffset=0;desk.uploadFilter={};render().catch(showError);};
    if($("#upload-filter"))act($("#upload-filter"),async f=>{desk.uploadFilter=Object.fromEntries(f);desk.uploadOffset=0;await render();});
    if($("#upload-prev"))$("#upload-prev").onclick=()=>{desk.uploadOffset-=40;render().catch(showError);};
    if($("#upload-next"))$("#upload-next").onclick=()=>{desk.uploadOffset+=40;render().catch(showError);};
    if($("#check-integrity"))$("#check-integrity").onclick=async()=>{
        const target=$("#integrity-state");
        target.textContent="Checking…";
        try{const result=await get("vault/integrity",{id:chosen.id});target.textContent=result.valid?"SHA-256 verified":"Integrity check failed";}
        catch(error){target.textContent=error.message;}
    };
    bindModule();
}
async function inspectUpload(ref){
    try{
        const record=await get("vault/record",{ref});
        $("#inspect").innerHTML=tag("UPLOADED")+" "+pill(record.status)+"<h2>"+esc(ref)+"</h2><p>"+esc(record.reason)+"</p>"+
            "<pre>"+esc(JSON.stringify(record.raw,null,2))+"</pre><h3>Investigator reviews</h3>"+
            (record.reviews.length?record.reviews.map(r=>"<p><small>"+esc(r.time)+"</small><br>"+esc(r.note)+"</p>").join(""):"<p>No reviews recorded.</p>")+
            '<form id="upload-review" class="stack"><label class="control">Review note<textarea name="note" maxlength="500" required></textarea></label>'+
            '<div class="tools"><button type="submit" class="primary">Save review note</button><span class="feedback" role="status"></span></div></form>';
        if(!$("#detail").open)$("#detail").showModal();
        act($("#upload-review"),async f=>{await post("vault/review",{ref,note:f.get("note")});await inspectUpload(ref);});
    }catch(error){showError(error);}
}
function contextModule(){
    const sources=[
        ["MITRE ATT&CK","https://attack.mitre.org/","Reference library of adversary behaviors."],
        ["NIST Computer Security Resource Center","https://csrc.nist.gov/","Security standards and guidance."],
        ["CISA Cybersecurity Advisories","https://www.cisa.gov/news-events/cybersecurity-advisories","Public advisories."],
        ["NVD","https://nvd.nist.gov/","Public vulnerability reference."],
        ["FIRST EPSS","https://www.first.org/epss/","Vulnerability scoring reference."]
    ];
    content.innerHTML=head("External Context","Review references independently of case findings. This local prototype makes no live external API requests.")+
        section("Supplied context",'<p>E20 contains public-record snapshots supplied with the evidence pack. Record Inspector displays a relevant excerpt and reference when a supported relationship matches.</p>'+
        '<button class="btn" id="open-reference">Find E20 in Evidence Vault</button>')+
        section("External reference links",tag("EXTERNAL CONTEXT")+'<div class="reference-list">'+sources.map(([name,url,detail])=>
          '<div><a target="_blank" rel="noopener noreferrer" href="'+url+'">'+name+' ↗</a><p>'+detail+'</p><small>Reference link · retrieval pending</small></div>').join("")+'</div>');
    $("#open-reference").onclick=()=>{desk.vaultTab="case";state.source="E20";state.query="";state.quality="";state.eventType="";state.start="";state.end="";state.relationship="observed";state.entity="";go("Evidence vault");};
}
async function reportModule(token){
    const [runs,run,uploads]=await Promise.all([get("sentinel/runs"),selectedRun(),get("vault/inventory")]);
    if(token!==revision)return;
    const exportLinks=["pdf","json","csv"].map(ext=>'<a class="btn" href="/api/exports/'+ext+'?'+params(reportParams())+'">Download '+ext.toUpperCase()+'</a>').join("");
    content.innerHTML=head("Investigation Reports","Export the current case evidence assessment and the selected synthetic exercise with origin labels and record references.")+
        section("Report scope",'<div class="overview-line"><span>Case references under challenge</span><b>'+state.excluded.size+'</b></div>'+
        '<div class="overview-line"><span>Active case rule results</span><b>'+model.facts.length+'</b></div>'+
        '<div class="overview-line"><span>Upload inventory entries</span><b>'+uploads.length+'</b></div>'+
        runSelector(runs)+(run?'<p>'+simBadge()+' '+esc(run.id)+' · '+desk.simExcluded.size+' challenged exercise records</p>':"")+
        '<div class="tools">'+exportLinks+'</div>')+
        section("Hypothesis summary",Object.entries(model.hypotheses).map(([id,h])=>
          '<div class="overview-line"><span>'+id+' · '+esc(h.name)+'</span>'+pill(h.status)+'</div>').join(""));
    selectRun();bindModule();
}
