#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot Dashboard v13 Pro
✅ Näyttää koulutukset (TF, Sharpe)
✅ Näyttää live-positiot (entry, SL, TP, PnL %)
✅ Tilin saldon/oman pääoman graafi (1 h / 1 d / 1 kk)
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json, asyncio, datetime, math

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
LOGS = BASE / "logs"

app = FastAPI(title="CapitalBot Dashboard v13 Pro")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def jload(p):
    try: return json.load(open(p))
    except: return {}

@app.get("/status")
def status():
    return JSONResponse({
        "time": datetime.datetime.utcnow().isoformat()+"Z",
        "positions": jload(DATA/"open_positions.json"),
        "risk": jload(DATA/"risk_state.json"),
        "train": jload(DATA/"train_history.json"),
        "equity": jload(DATA/"equity_history.json")
    })

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    last_hash = ""
    try:
        while True:
            data = {
                "time": datetime.datetime.utcnow().isoformat()+"Z",
                "positions": jload(DATA/"open_positions.json"),
                "risk": jload(DATA/"risk_state.json"),
                "train": jload(DATA/"train_history.json"),
                "equity": jload(DATA/"equity_history.json")
            }
            h = hash(json.dumps(data))
            if h != last_hash:
                await websocket.send_json(data)
                last_hash = h
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'/>
<title>CapitalBot Dashboard v13 Pro</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{background:#0d0f18;color:#e0e0e0;font-family:Segoe UI,Arial;margin:0}
header{background:#171a28;padding:12px 24px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 2px 6px #000}
h1{color:#72e2ff;margin:0;font-size:22px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:15px}
.card{background:#171a28;padding:15px;border-radius:12px;box-shadow:0 0 8px #0007}
th,td{padding:6px;text-align:left;border-bottom:1px solid #333}
th{color:#72e2ff;font-weight:600}
.pos-LONG{color:#00ff9c;font-weight:700}
.pos-SHORT{color:#ff6060;font-weight:700}
.small{font-size:13px;color:#999}
canvas{background:#10121c;border-radius:8px;padding:6px}
</style>
</head>
<body>
<header><h1>CapitalBot Dashboard v13 Pro</h1><span id="clock" class="small"></span></header>

<div class="grid">
  <div class="card"><h2>Sharpe History</h2><canvas id="sharpe"></canvas></div>
  <div class="card"><h2>Equity Growth</h2><canvas id="equity"></canvas></div>
</div>

<div class="card">
  <h2>Live Positions</h2>
  <table id="pos"><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>TP</th><th>SL</th><th>PnL %</th></tr></thead><tbody></tbody></table>
</div>

<div class="card">
  <h2>Training Results</h2>
  <table id="train"><thead><tr><th>Timestamp</th><th>TF</th><th>Model</th><th>Sharpe</th><th>Notes</th></tr></thead><tbody></tbody></table>
</div>

<script>
const ws=new WebSocket("ws://"+window.location.host+"/ws");
const ctxS=document.getElementById('sharpe').getContext('2d');
const ctxE=document.getElementById('equity').getContext('2d');
let sharpeChart=new Chart(ctxS,{type:'line',data:{labels:[],datasets:[{label:'Sharpe',borderColor:'#72e2ff',fill:false,tension:0.4,data:[]}]},options:{scales:{x:{ticks:{color:'#888'}},y:{ticks:{color:'#888'}}}}});
let equityChart=new Chart(ctxE,{type:'line',data:{labels:[],datasets:[{label:'Equity €',borderColor:'#00ff9c',fill:false,tension:0.3,data:[]}]},options:{scales:{x:{ticks:{color:'#888'}},y:{ticks:{color:'#888'}}}}});

ws.onmessage=ev=>{
  let d=JSON.parse(ev.data);
  document.getElementById("clock").textContent="Updated "+new Date(d.time).toLocaleTimeString();

  // Positions
  let tb=document.querySelector("#pos tbody");tb.innerHTML='';
  for(let [sym,v] of Object.entries(d.positions.positions||{})){
    let tr=document.createElement('tr');
    tr.innerHTML=`<td>${sym}</td><td class="pos-${v.side}">${v.side}</td><td>${v.size}</td><td>${v.entry||'-'}</td><td>${v.tp||'-'}</td><td>${v.sl||'-'}</td><td>${(v.pnl_pct||0).toFixed(2)}%</td>`;
    tb.appendChild(tr);
  }

  // Training
  let tbt=document.querySelector("#train tbody");tbt.innerHTML='';
  for(let e of (d.train||[]).slice(-10)){
    let tr=document.createElement('tr');
    tr.innerHTML=`<td>${e.timestamp}</td><td>${e.tf||'-'}</td><td>${e.model||'-'}</td><td>${(e.sharpe||0).toFixed(3)}</td><td>${e.notes||''}</td>`;
    tbt.appendChild(tr);
  }

  // Sharpe
  let hist=(d.train||[]);
  sharpeChart.data.labels=hist.map(x=>x.timestamp);
  sharpeChart.data.datasets[0].data=hist.map(x=>x.sharpe);
  sharpeChart.update();

  // Equity
  let eq=d.equity.entries||[];
  equityChart.data.labels=eq.map(x=>x.timestamp);
  equityChart.data.datasets[0].data=eq.map(x=>x.equity);
  equityChart.update();
};
</script>
</body></html>
""")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
