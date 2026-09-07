#!/usr/bin/env python3
"""webdash.py - interactive local dashboard for the whole monthly ritual.

    python webdash.py          # opens http://127.0.0.1:8642 in your browser

From the page you can:
  * pick Paper (port 4002) or LIVE (port 4001)  - host fixed to 127.0.0.1
  * set contribution / deploy / min-order
  * "Prepare" -> runs fetch_prices.py + rebalance.py DRY RUN, shows the
    staged orders, weights vs target, regime and compliance checklist
  * tick/untick individual orders, type the confirmation phrase, "Execute"
    -> places ONLY the ticked orders (rebalance.py --execute --yes)
  * "Undo state" -> if you prepared but did NOT execute, restores state.json

Safety model (same human gate as the terminal, different skin):
  * server binds to 127.0.0.1 only - nothing is reachable from outside
  * nothing is ever sent to IBKR without you typing the confirmation phrase:
       paper account:  EXECUTE
       live  account:  EXECUTE LIVE     (page turns red in live mode)
  * per-order approval = the checkboxes; unticked orders are never sent
  * Gateway's own Read-Only API toggle stays your hardware-level safety

Requires: standard library only (rebalance.py itself needs pandas/ib_async).
"""

import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import workspace

HERE = Path(__file__).resolve().parent
PY = sys.executable or "python3"
# One folder serves BOTH accounts: every stateful file is namespaced, so the
# paper account's memory can never be read or written by a live run.
PORTS = {"paper": 4002, "live": 4001}
CONFIRM = {"paper": "EXECUTE", "live": "EXECUTE LIVE"}


def P(acct):
    """Per-account file paths."""
    a = "live" if acct == "live" else "paper"
    return dict(
        state=HERE / f"state.{a}.json",
        undo=HERE / f"state.{a}.undo.json",
        pending=HERE / f"state.{a}.pending",
        orders=HERE / f"orders.{a}.json",
        approved=HERE / f"orders_approved.{a}.json",
        result=HERE / f"orders_result.{a}.json",
        report=HERE / f"prep_report.{a}.md",
    )


def _pending(acct):
    try:
        return P(acct)["pending"].read_text().strip() == "1"
    except Exception:
        return False
SERVER_PORT = 8642


# ------------------------------------------------------------------ helpers

def run_step(args_list):
    p = subprocess.run([PY] + args_list, cwd=HERE, capture_output=True,
                       text=True)
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return p.returncode == 0, out.strip()


def parse_report(md_text):
    lines = md_text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    meta = lines[1].strip() if len(lines) > 1 else ""
    sections, current, buf = {}, None, []
    for ln in lines[2:]:
        if ln.startswith("## "):
            if current:
                sections[current] = buf
            current, buf = ln[3:].strip(), []
        else:
            buf.append(ln)
    if current:
        sections[current] = buf
    return title, meta, sections


def parse_table(section_lines):
    rows = []
    for ln in section_lines:
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells and not all(set(c) <= {"-", " ", ":"} for c in cells):
            rows.append(cells)
    return (rows[0], rows[1:]) if rows else ([], [])


def section_by_prefix(sections, prefix):
    for k, v in sections.items():
        if k.lower().startswith(prefix.lower()):
            return v
    return []


def report_payload(acct, run_logs):
    """Parse this account's report + orders into the JSON the page renders."""
    import re
    pp = P(acct)
    if not pp["report"].exists():
        return {"ok": False, "log": f"no report yet for the {acct} account"}
    title, meta, sections = parse_report(pp["report"].read_text())
    regime_txt = " ".join(section_by_prefix(sections, "Regime"))
    m = re.search(r"D = ([\-\d.]+)%.*?(Calm|Correction|Crash)", regime_txt)
    dm = re.search(r"\*\*DRIFT:\*\*\s*(.+)", " ".join(
        section_by_prefix(sections, "Regime")))
    _, wrows = parse_table(section_by_prefix(sections, "Current vs target"))
    _, crows = parse_table(section_by_prefix(sections, "Manual compliance"))
    try:
        orders = json.loads(pp["orders"].read_text())
    except Exception:
        orders = []
    try:
        history = json.loads(pp["state"].read_text()).get("history", [])
    except Exception:
        history = []
    return {"ok": True, "title": title, "meta": meta,
            "d": m.group(1) if m else "?",
            "regime": m.group(2) if m else "?",
            "orders": orders, "weights": wrows, "checklist": crows,
            "units": [h.get("unit", 0) for h in history],
            "log": "\n\n".join(f"$ {c}\n{o}" for c, o in run_logs),
            "drift": dm.group(1).strip() if dm else None,
            "account": acct, "pending": _pending(acct)}


# ------------------------------------------------------------------ actions

def api_prepare(p):
    account = "live" if p.get("account") == "live" else "paper"
    pp, port = P(account), PORTS[account]
    # state hygiene: a previous prepare that was never executed gets rolled
    # back before we run again, so previews don't stack up in state
    if _pending(account) and pp["undo"].exists():
        shutil.copy(pp["undo"], pp["state"])
    if pp["state"].exists():
        shutil.copy(pp["state"], pp["undo"])

    logs = []
    if p.get("fetch", True):
        ok, out = run_step(["fetch_prices.py"])
        logs.append(("python fetch_prices.py", out))
    cmd = ["rebalance.py", "--contribute", str(p.get("contribute", 0) or 0),
           "--ib", f"127.0.0.1:{port}",
           "--expect-account", account,          # hard account verification
           "--state", str(pp["state"]),
           "--orders-out", str(pp["orders"]),
           "--out", str(pp["report"])]
    if p.get("deploy"):
        cmd += ["--deploy", str(p["deploy"])]
    if p.get("min_order") is not None:      # 0 is a valid value, not "unset"
        cmd += ["--min-order", str(p["min_order"])]
    ok, out = run_step(cmd)
    logs.append(("python " + " ".join(cmd), out))
    if not ok:
        return {"ok": False, "account": account,
                "log": "\n\n".join(f"$ {c}\n{o}" for c, o in logs)}
    payload = report_payload(account, logs)
    if payload.get("ok"):
        # a "pending preview" only exists when something was actually staged
        pp["pending"].write_text("1" if payload.get("orders") else "0")
        payload["pending"] = _pending(account)
    return payload


def api_execute(p):
    account = "live" if p.get("account") == "live" else "paper"
    pp, port = P(account), PORTS[account]
    phrase = (p.get("confirm") or "").strip()
    if phrase != CONFIRM[account]:
        return {"ok": False, "log": f"confirmation phrase wrong - type "
                                    f"exactly: {CONFIRM[account]}"}
    try:
        orders = json.loads(pp["orders"].read_text())
    except Exception:
        return {"ok": False, "log": "no staged orders found"}
    sel = p.get("selected", [])
    chosen = [o for i, o in enumerate(orders) if i in sel]
    if not chosen:
        return {"ok": False, "log": "no orders selected"}
    pp["approved"].write_text(json.dumps(chosen, indent=1))
    pp["result"].write_text("[]")            # clear stale results
    ok, out = run_step(["rebalance.py", "--execute", str(pp["approved"]),
                        "--ib", f"127.0.0.1:{port}", "--yes",
                        "--expect-account", account,
                        "--state", str(pp["state"]),
                        "--result-out", str(pp["result"])])
    if ok:
        pp["pending"].write_text("0")        # state reflects executed orders
    try:
        results = json.loads(pp["result"].read_text())
    except Exception:
        results = []
    return {"ok": ok, "log": out, "results": results, "account": account,
            "sent": len(chosen), "total": len(orders)}


def api_resync(p):
    """Re-baseline: today's portfolio becomes the reference (D back to 0)."""
    account = "live" if p.get("account") == "live" else "paper"
    pp, port = P(account), PORTS[account]
    ok, out = run_step(["rebalance.py", "--contribute", "0",
                        "--ib", f"127.0.0.1:{port}", "--reset-baseline",
                        "--expect-account", account,
                        "--state", str(pp["state"]),
                        "--orders-out", str(pp["orders"]),
                        "--out", str(pp["report"])])
    if not ok:
        return {"ok": False, "account": account, "log": out}
    pp["pending"].write_text("0")
    payload = report_payload(account, [("resync baseline", out)])
    payload["pending"] = _pending(account)
    return payload


def api_undo(p):
    account = "live" if p.get("account") == "live" else "paper"
    pp = P(account)
    if pp["undo"].exists():
        shutil.copy(pp["undo"], pp["state"])
        pp["pending"].write_text("0")
        return {"ok": True, "log": f"{account} state restored from before "
                                   f"the last prepare"}
    return {"ok": False, "log": f"no undo snapshot for the {account} account"}


# ------------------------------------------------------------------ web page

PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lens · Monthly investing</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f5f6f8;color:#1a202c;margin:0;padding:24px 14px}
body.live{background:#fdf3f3}
.wrap{max-width:920px;margin:0 auto}
.card{background:#fff;border-radius:12px;padding:18px 22px;margin-bottom:16px;
      box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{font-size:20px;margin:0 0 2px} h2{font-size:13px;text-transform:uppercase;
   letter-spacing:.06em;color:#4a5568;margin:0 0 12px}
.muted{color:#718096;font-size:13px}
.banner{padding:10px 14px;border-radius:8px;font-weight:700;margin-bottom:14px}
.banner.paper{background:#e6fffa;color:#234e52}
.banner.live{background:#c0392b;color:#fff}
label{font-size:13px;color:#4a5568;margin-right:4px}
input[type=number]{width:90px;padding:6px;border:1px solid #cbd5e0;
  border-radius:6px} input[type=text]{padding:6px;border:1px solid #cbd5e0;
  border-radius:6px}
button{background:#2b6cb0;color:#fff;border:0;padding:9px 18px;
  border-radius:8px;font-weight:600;cursor:pointer;font-size:14px}
button:disabled{background:#a0aec0;cursor:not-allowed}
button.danger{background:#c0392b} button.ghost{background:#edf2f7;color:#2d3748}
.chip{color:#fff;padding:2px 10px;border-radius:10px;font-size:12px;
  font-weight:600;margin-right:6px;display:inline-block}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;color:#718096;font-size:11.5px;text-transform:uppercase;
   letter-spacing:.04em;padding:5px 8px;border-bottom:2px solid #e2e8f0}
td{padding:6px 8px;border-bottom:1px solid #edf2f7;vertical-align:top}
.track{position:relative;height:15px;background:#edf2f7;border-radius:8px}
.tgt{position:absolute;top:0;left:0;height:15px;background:#bee3f8;
  border-radius:8px}
.cur{position:absolute;top:3px;left:0;height:9px;background:#2b6cb0;
  border-radius:5px}
pre{background:#1a202c;color:#e2e8f0;padding:12px;border-radius:8px;
  font-size:12px;overflow-x:auto;white-space:pre-wrap;max-height:340px;
  overflow-y:auto}
#spin{display:none;color:#2b6cb0;font-weight:600}
details summary{cursor:pointer;color:#718096;font-size:13px}
.exrow{margin-top:12px;display:flex;gap:10px;align-items:center;
  flex-wrap:wrap}
/* Match the research workspace while retaining the live-account red state. */
body{background:#f7f8f4;color:#202d29;padding-top:32px}
.wrap{max-width:1100px}.card{border:1px solid #e2e7df;border-radius:16px;box-shadow:none;padding:22px 26px}
h1{font:32px Georgia,serif;letter-spacing:-.7px;margin-bottom:10px}
h2{color:#52664b}button{background:#335c44}button.ghost{background:#edf3e8;color:#335c44}
.banner.paper{background:#edf3e8;color:#335c44}.cur{background:#335c44}.tgt{background:#d8eaa6}
@media(max-width:620px){.card{padding:18px 14px}td,th{padding:6px 4px;font-size:11px}h1{font-size:27px}}
</style></head><body><div class="wrap">

<div class="card">
  <a href="/" style="display:inline-block;margin-bottom:14px;color:#335c44;text-decoration:none">&larr; Lens workspace</a>
  <h1>Monthly investing</h1>
  <p class="muted">Monthly investing uses the targets in manual.json. Your Lens research draft is separate.</p>
  <div id="banner" class="banner paper">PAPER account &middot; port 4002 &middot;
    nothing is sent without the confirmation phrase</div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
    <span id="modebox"></span>
    <span><label for="contribute">Add new money &euro;</label>
      <input type="number" id="contribute" value="600" step="50"></span>
    <span><label for="deploy" title="Sell this amount of the parked XEON cash sleeve to fund purchases">Use parked cash &euro;</label>
      <input type="number" id="deploy" value="0" step="50"></span>
    <span><label for="minorder">Minimum order &euro;</label>
      <input type="number" id="minorder" placeholder="100"></span>
    <span><label><input type="checkbox" id="fetch" checked>
      refresh prices</label></span>
    <button onclick="prepare()" id="prepbtn">Prepare (dry run)</button>
    <button class="ghost" onclick="undoState()">Undo state</button>
    <button class="ghost" onclick="resync()">Resync baseline</button>
    <span id="spin">&#9203; running&hellip;</span>
  </div>
</div>

<div class="card" id="statuscard" style="display:none">
  <h2>Status</h2><div id="chips"></div>
  <p class="muted" id="meta"></p>
</div>

<div class="card" id="orderscard" style="display:none">
  <h2>Staged orders - tick what you approve</h2>
  <div id="orders"></div>
  <div class="exrow" id="exrow">
    <input type="text" id="confirm" size="16" placeholder="type EXECUTE">
    <button class="danger" id="execbtn" onclick="doExecute()" disabled>
      Execute selected</button>
    <span id="spin2" style="display:none;color:#c0392b;font-weight:600">
      &#9203; executing&hellip;</span>
    <span class="muted" id="exhint"></span>
  </div>
</div>

<div class="card" id="weightscard" style="display:none">
  <h2>Current vs target</h2><div id="weights"></div>
  <p class="muted">light bar = target &nbsp;|&nbsp; dark = current</p>
</div>

<div class="card" id="checkcard" style="display:none">
  <h2>Compliance checklist</h2><div id="checklist"></div>
</div>

<div class="card" id="logcard" style="display:none">
  <h2>Technical log</h2><details><summary>run output</summary>
  <pre id="log"></pre></details>
</div>

</div><script>
const COLORS={PASS:"#1a7f37",CHECK:"#b35900",HUMAN:"#4a5568",FAIL:"#c0392b",
  Calm:"#1a7f37",Correction:"#b35900",Crash:"#c0392b"};
let DATA=null;
function acct(){return MODE}
function phrase(){return acct()==="live"?"EXECUTE LIVE":"EXECUTE"}
let FOLDER="", MODE="paper";      // always starts on paper, every load
function acctSet(m){ MODE=m; setAcct(); }
function armLive(){
  const w=prompt("Switch to the LIVE account?\n\n"+
    "Orders you approve there use REAL money.\n"+
    "IB Gateway must be logged into your live account (port 4001).\n\n"+
    "Type  LIVE  to continue:");
  if(w===null) return;
  if(w.trim().toUpperCase()!=="LIVE"){ alert("Not switched - phrase did not match."); return; }
  acctSet("live");
}
function setAcct(){
  const a=acct(), b=document.getElementById("banner");
  const mismatch = false;
  document.getElementById("modebox").innerHTML = a==="live"
    ? "<b style='color:#c0392b'>&#9679; LIVE</b> "+
      "<button class='ghost' style='padding:4px 10px;font-size:12px' "+
      "onclick='acctSet(\"paper\")'>back to paper</button>"
    : "<b style='color:#1a7f37'>&#9679; PAPER</b> "+
      "<button class='ghost' style='padding:4px 10px;font-size:12px' "+
      "onclick='armLive()'>switch to LIVE&hellip;</button>";
  document.body.className = a==="live"?"live":"";
  b.className="banner "+a;
  b.innerHTML = a==="live"
    ? "&#9888;&#65039; LIVE account &middot; port 4001 &middot; real money - "
      + "confirmation phrase: <b>EXECUTE LIVE</b>"
    : "PAPER account &middot; port 4002 &middot; nothing is sent without "
      + "the confirmation phrase";
  b.innerHTML += " &middot; state file: <code>state."+a+".json</code>";
  document.getElementById("confirm").placeholder="type "+phrase();
  checkConfirm();
  fetch("/api/last",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({account:a})})
    .then(r=>r.json()).then(d=>{if(d.ok)render(d);}).catch(()=>{});
}
function chip(t,c){return `<span class="chip" style="background:${c}">${t}</span>`}
async function call(url,body,spinId){
  const sp=document.getElementById(spinId||"spin");
  sp.style.display="inline";
  document.getElementById("prepbtn").disabled=true;
  try{
    const r=await fetch(url,{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body||{})});
    return await r.json();
  } finally {
    sp.style.display="none";
    document.getElementById("prepbtn").disabled=false;
  }
}
function esc(s){const d=document.createElement("div");
  d.textContent=String(s);return d.innerHTML}
function render(d){
  DATA=d;
  document.getElementById("logcard").style.display="block";
  document.getElementById("log").textContent=d.log||"";
  if(!d.ok){
    const L=(d.log||"").split("\n").filter(x=>x.trim());
    const i=L.findIndex(x=>x.includes("CANNOT REACH IB GATEWAY"));
    alert(i>=0 ? L.slice(i,i+6).join("\n")
               : "run failed - see log at the bottom");
    return;
  }
  document.getElementById("statuscard").style.display="block";
  document.getElementById("meta").textContent=(d.title||"")+"  -  "+(d.meta||"");
  let pass=0,check=0,fail=0;
  (d.checklist||[]).forEach(r=>{if(r[2]==="PASS")pass++;
    else if(r[2]==="CHECK")check++;else if(r[2]==="FAIL")fail++});
  document.getElementById("chips").innerHTML=
    chip("Regime: "+d.regime,COLORS[d.regime]||"#4a5568")+
    chip("D = "+d.d+"%","#2b6cb0")+chip(pass+" PASS",COLORS.PASS)+
    (check?chip(check+" CHECK",COLORS.CHECK):"")+
    (fail?chip(fail+" FAIL",COLORS.FAIL):"")+
    (d.pending?chip("preview not executed","#805ad5"):"")+
    (d.drift?chip("positions changed outside the tool","#c0392b"):"")+
    chip((d.account||"paper").toUpperCase()+" account",
         d.account==="live"?"#c0392b":"#1a7f37");
  if(d.drift){
    document.getElementById("meta").innerHTML+=
      "<br><b style='color:#c0392b'>"+esc(d.drift)+"</b>";
  }
  // orders
  const oc=document.getElementById("orderscard");
  oc.style.display="block";
  if(!(d.orders||[]).length){
    document.getElementById("orders").innerHTML=
      "<p class='muted'>None this month.</p>";
    document.getElementById("exrow").style.display="none";
  } else {
    document.getElementById("exrow").style.display="flex";
    let h="<table><tr><th></th><th>Side</th><th>Ticker</th><th>Qty</th>"+
      "<th>Est. price</th><th>Est. &euro;</th></tr>";
    d.orders.forEach((o,i)=>{
      const col=o.side==="BUY"?"#1a7f37":"#c0392b";
      h+=`<tr><td><input type="checkbox" class="osel" data-i="${i}" checked
        onchange="checkConfirm()"></td>
        <td>${chip(o.side,col)}</td><td><b>${esc(o.ticker)}</b></td>
        <td>${o.qty}</td><td>${o.est_price}</td>
        <td>${(o.qty*o.est_price).toLocaleString(undefined,
              {maximumFractionDigits:0})}</td></tr>`;});
    h+="</table>";
    document.getElementById("orders").innerHTML=h;
  }
  checkConfirm();
  // weights
  const wr=d.weights||[];
  if(wr.length){
    document.getElementById("weightscard").style.display="block";
    let scale=1;
    wr.forEach(r=>{scale=Math.max(scale,parseFloat(r[1])||0,
      parseFloat(r[2])||0)});
    let h="<table><tr><th>Sleeve</th><th style='width:44%'></th>"+
      "<th>Cur %</th><th>Tgt %</th><th>Gap &euro;</th><th>Routed</th></tr>";
    wr.forEach(r=>{
      const cur=parseFloat(r[1])||0,tgt=parseFloat(r[2])||0;
      const bold=(r[4]&&r[4]!=="0")?" style='font-weight:700'":"";
      h+=`<tr${bold}><td>${esc(r[0])}</td><td><div class="track">
        <div class="tgt" style="width:${100*tgt/scale}%"></div>
        <div class="cur" style="width:${100*cur/scale}%"></div></div></td>
        <td>${cur.toFixed(2)}</td><td>${tgt.toFixed(1)}</td>
        <td>${esc(r[3]||"")}</td><td>${esc(r[4]||"")}</td></tr>`;});
    document.getElementById("weights").innerHTML=h+"</table>";
  }
  // checklist
  const cr=d.checklist||[];
  if(cr.length){
    document.getElementById("checkcard").style.display="block";
    let h="<table><tr><th>&sect;</th><th>Criterion</th><th>Status</th>"+
      "<th>Detail</th></tr>";
    cr.forEach(r=>{
      const det=(r[3]||"").length>110
        ?`<details><summary>${esc((r[3]||"").slice(0,90))}&hellip;</summary>`+
         `${esc(r[3])}</details>`:esc(r[3]||"");
      h+=`<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td>
        <td>${chip(r[2],COLORS[r[2]]||"#4a5568")}</td>
        <td class="muted">${det}</td></tr>`;});
    document.getElementById("checklist").innerHTML=h+"</table>";
  }
}
function renderResults(res){
  if(!res||!res.length) return;
  const oc=document.getElementById("orderscard");
  oc.style.display="block";
  document.getElementById("exrow").style.display="none";
  const BG={filled:"#e8f5e9",partial:"#fff8e1",working:"#fff8e1",
            skipped:"#fdecea",failed:"#fdecea"};
  const CH={filled:["FILLED","#1a7f37"],partial:["PARTIAL","#b35900"],
            working:["WORKING","#b35900"],skipped:["SKIPPED","#c0392b"],
            failed:["FAILED","#c0392b"]};
  let h="<p style='font-weight:700;margin:0 0 8px'>Last execution results</p>"+
    "<table><tr><th>Result</th><th>Side</th><th>Ticker</th>"+
    "<th>Filled</th><th>Note</th></tr>";
  res.forEach(r=>{
    const m=CH[r.status]||["?","#4a5568"];
    h+=`<tr style="background:${BG[r.status]||'#fff'}">`+
       `<td>${chip(m[0],m[1])}</td><td>${esc(r.side)}</td>`+
       `<td><b>${esc(r.ticker)}</b></td>`+
       `<td>${r.filled!=null?r.filled:""}/${r.qty}</td>`+
       `<td class="muted">${esc(r.note||"")}</td></tr>`;});
  document.getElementById("orders").innerHTML=h+"</table>"+
    "<p class='muted'>green = fully filled &middot; yellow = partial or "+
    "still working &middot; red = skipped/failed &middot; "+
    "run Prepare to stage the next batch</p>";
}
function selected(){return [...document.querySelectorAll(".osel")]
  .filter(c=>c.checked).map(c=>parseInt(c.dataset.i))}
function checkConfirm(){
  const ok=document.getElementById("confirm").value.trim()===phrase()
    && selected().length>0;
  document.getElementById("execbtn").disabled=!ok;
  document.getElementById("exhint").textContent=
    selected().length+" order(s) selected - phrase: "+phrase();
}
document.getElementById("confirm").addEventListener("input",checkConfirm);
async function prepare(){
  const d=await call("/api/prepare",{account:acct(),
    contribute:parseFloat(document.getElementById("contribute").value)||0,
    deploy:parseFloat(document.getElementById("deploy").value)||0,
    min_order:(function(){
      const v=document.getElementById("minorder").value.trim();
      return v===""?null:parseFloat(v);   // 0 must survive
    })(),
    fetch:document.getElementById("fetch").checked});
  render(d);
}
async function doExecute(){
  if(!confirm("Send "+selected().length+" order(s) to the "+
      acct().toUpperCase()+" account?")) return;
  const btn=document.getElementById("execbtn"); btn.disabled=true;
  const d=await call("/api/execute",{account:acct(),selected:selected(),
    confirm:document.getElementById("confirm").value.trim()},"spin2");
  const execLog=d.log||"";
  document.getElementById("logcard").style.display="block";
  document.getElementById("log").textContent=execLog;
  if(d.ok){
    document.getElementById("confirm").value="";
    // refresh the whole view against the account's NEW positions
    const r=await call("/api/prepare",
      {account:acct(),contribute:0,deploy:0,fetch:false},"spin2");
    render(r);
    renderResults(d.results);   // paint green/yellow/red per-order outcomes
    document.getElementById("log").textContent=
      "=== EXECUTION ===\n"+execLog+
      "\n\n=== POST-EXECUTION REFRESH ===\n"+(r.log||"");
    alert("Sent "+d.sent+" order(s). View refreshed - see the colored "+
          "results table.");
  } else {
    alert("Execute refused: "+execLog.split("\n")[0]);
    checkConfirm();
  }
}
async function resync(){
  if(!confirm("Re-baseline: today's portfolio becomes the reference.\n\n"+
     "Drawdown D resets to 0% and the dry-powder ladder is cleared.\n\n"+
     "Use this ONLY after changing positions by hand.\n"+
     "Do NOT use it during a real market drawdown - it erases the "+
     "drawdown the ladder needs.")) return;
  const d=await call("/api/resync",{account:acct()});
  render(d);
  alert(d.ok?"Baseline reset to today's portfolio.":"Resync failed - see log.");
}
async function undoState(){
  const d=await call("/api/undo",{account:acct()});
  alert(d.log);
}
// on load: show whatever the last run produced
fetch("/api/where",{method:"POST",body:"{}"})
  .then(r=>r.json()).then(d=>{FOLDER=d.folder||"";setAcct();}).catch(()=>{});
fetch("/api/last",{method:"POST",body:"{}"})
  .then(r=>r.json()).then(d=>{if(d.ok)render(d)}).catch(()=>{});
setAcct();
</script></body></html>"""


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                       # quiet console
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/rebalance"):
            body = PAGE.encode() if self.path == "/rebalance" else (HERE / "workspace.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"ok": False, "log": "not found"}, 404)

    def do_POST(self):
        # Reject cross-site posts to this localhost app, including requests to
        # order endpoints. Same-origin browser calls and local CLI calls work.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{SERVER_PORT}", f"localhost:{SERVER_PORT}") or (
                origin and urlsplit(origin).netloc != host):
            self._json({"ok": False, "error": "Cross-origin request refused."}, 403)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            self._json({"ok": False, "error": "Use application/json."}, 415)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 <= n <= 256000:
                raise ValueError()
        except ValueError:
            self._json({"ok": False, "error": "Request too large or invalid length."}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError()
        except Exception:
            self._json({"ok": False, "error": "Expected a JSON object."}, 400)
            return
        try:
            if self.path.startswith("/api/workspace/"):
                self._json(workspace.api(self.path.rsplit("/", 1)[-1], payload))
            elif self.path == "/api/prepare":
                self._json(api_prepare(payload))
            elif self.path == "/api/execute":
                self._json(api_execute(payload))
            elif self.path == "/api/resync":
                self._json(api_resync(payload))
            elif self.path == "/api/undo":
                self._json(api_undo(payload))
            elif self.path == "/api/where":
                self._json({"ok": True, "folder": HERE.name,
                            "path": str(HERE)})
            elif self.path == "/api/last":
                self._json(report_payload(
                    "live" if payload.get("account") == "live" else "paper",
                    []))
            else:
                self._json({"ok": False, "log": "unknown endpoint"}, 404)
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self._json({"ok": False, "log": f"server error: {e}"}, 500)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", SERVER_PORT), Handler)
    url = f"http://127.0.0.1:{SERVER_PORT}"
    print(f"dashboard running at {url}   (Ctrl-C to stop)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
