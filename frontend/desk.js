const $=id=>document.getElementById(id);
let actor=null;
async function request(url,data){
 const options=data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-Trace-Local":"1"},body:JSON.stringify(data)};
 const response=await fetch(url,{...options,cache:"no-store"}), body=await response.json();
 if(response.status===401 && actor) show(null);
 return {body,ok:response.ok,status:response.status};
}
function show(user){
 actor=user;$("desk").hidden=!user;$("entrance").hidden=!!user;
 $("identity").textContent=user?"Signed in as "+user:"";$("history").replaceChildren();
 $("result").replaceChildren();outcome("Awaiting request","Choose an operation to see its outcome.");
}
function outcome(title,detail,cls=""){
 const h=document.createElement("h2"),p=document.createElement("p");
 h.textContent=title;p.textContent=detail;h.className=cls;$("result").replaceChildren(h,p);
}
async function activity(){
 const {body,ok}=await request("/access/activity");if(!ok)return;
 $("history").replaceChildren(...body.map(r=>{const tr=document.createElement("tr");
 for(const v of [r.utc,r.actor,r.operation,r.decision]){const cell=tr.insertCell();cell.textContent=v;if(v===r.decision)cell.className=v.toLowerCase();}
 return tr;}));
}
function bind(id,event,fn){
 $(id).addEventListener(event,async e=>{e.preventDefault();const el=e.currentTarget;el.setAttribute("aria-busy","true");
 try{await fn()}catch{const msg="Server unavailable. Check the local server and retry.";if(actor)outcome("Request interrupted",msg);else $("failure").textContent=msg;}
 finally{el.removeAttribute("aria-busy")}});
}
bind("login","submit",async()=>{const {ok,body}=await request("/access/login",{username:$("username").value.trim().toLowerCase(),password:$("password").value});
 $("password").value="";$("failure").textContent=ok?"":body.error;if(ok){show(body.user);await activity()}});
bind("logout","click",async()=>{await request("/access/logout",{});show(null)});
async function action(url,data){
 const {body,ok,status}=await request(url,data);
 if(!actor)return;
 const details=body.error || (body.statement?body.statement+"   ·   "+body.amount+"\nRegistered beneficiary: "+body.beneficiary:"Saved beneficiary: "+body.beneficiary);
 outcome((ok?"Allowed":"Blocked")+" · "+status,details,ok?"allowed":"blocked");await activity();
}
bind("statement","click",()=>action("/access/statement"));
bind("change","click",()=>action("/access/beneficiary",{beneficiary:$("payee").value}));
bind("case","click",async()=>{if(actor==="investigator"){location.assign("/workspace");return}await action("/workspace")});
bind("refresh","click",activity);
request("/access/session").then(async({body})=>{show(body.user);if(actor)await activity()}).catch(()=>{$("failure").textContent="The local server could not be reached."});
