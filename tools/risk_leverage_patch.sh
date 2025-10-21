#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/pro_botti"
LD="$ROOT/tools/live_daemon.py"
TR="$ROOT/tools/trainer_daemon.py"

backup() {
  local f="$1"
  cp -a "$f" "${f}.BAK.$(date +%Y%m%d_%H%M%S)"
}

echo "==> Patch 3: live_daemon.py riskipohjainen position sizer"
backup "$LD"

# 3a) lisää import (vain jos puuttuu)
grep -q 'from tools.position_sizer import' "$LD" || \
  sed -i '1,60s@from tools.instrument_loader import load_instruments@from tools.instrument_loader import load_instruments\nfrom tools.position_sizer import calc_order_size, instr_info@' "$LD"

# 3b) korvaa pick_size-funktio riskisizerillä (yksinkertainen ja turvallinen override)
python - "$LD" <<'PY'
import re,sys
p=sys.argv[1]
s=open(p,'r',encoding='utf-8').read()

pat=r"def pick_size\\(symbol, sizes_map, default_size\\):[\\s\\S]*?\\n\\s*return size, m, step"
new = """def pick_size(symbol, sizes_map, default_size):
    \"\"\"Riskipohjainen sizing: käyttää margin_factor/leverage, fallback defaultiin jos ei dataa.\"\"\"
    try:
        info_cfg = sizes_map.get(symbol, {}) if isinstance(sizes_map, dict) else {}
        step = float(info_cfg.get("step", 0) or 0)
    except Exception:
        step = 0.0
    try:
        ii = instr_info(symbol)
        minsz = ii.get("min_trade_size")
    except Exception:
        ii = {}; minsz = None

    # defaultit, jos live-klientti/tili ei saatavilla -> pidä entinen käytös
    used = float(default_size)

    # Jos globaalissa kontekstissa on CapitalClient-instanssi, yritä hakea hinta + vapaa pääoma
    free = 0.0; px = 1.0
    try:
        # haetaan dynaamisesti 'cli' muuttuja pääloopista kutsuhetkellä
        import inspect
        frm = inspect.currentframe()
        while frm and 'cli' not in frm.f_locals: frm = frm.f_back
        cli = frm.f_locals.get('cli') if frm else None
    except Exception:
        cli = None

    if cli is not None:
        try:
            epic = cli.resolve_epic(symbol) if hasattr(cli,'resolve_epic') else symbol
            px = cli.last_price(epic) or 1.0
        except Exception:
            px = 1.0
        try:
            ai = cli.account_info()
            if isinstance(ai, dict) and 'accounts' in ai:
                for a in ai['accounts']:
                    if a.get('preferred') or a.get('status')=='ENABLED':
                        free = float(a.get('balance',{}).get('available',0.0)); break
        except Exception:
            free = 0.0

        import os
        risk_pct    = float(os.getenv("RISK_PCT", "0.10"))
        safety_mult = float(os.getenv("RISK_SAFETY", "0.95"))
        try:
            used = calc_order_size(symbol=symbol, price=px, free_balance=free,
                                   risk_pct=risk_pct, min_size=minsz, step=step, safety_mult=safety_mult)
            if not used or used <= 0:
                used = float(default_size)
        except Exception:
            used = float(default_size)
    else:
        # ei liveä -> palataan entiseen min/step logiikkaan
        m = float(minsz or default_size)
        st = float(step or 0)
        size = max(m, float(default_size))
        if st and st>0:
            k = int((size + st - 1e-12) // st)
            size = max(m, (k if k>0 else 1)*st)
            size = float(f"{size:.8f}")
        return size, m, st

    # Palautetaan sama kolmikko kuin ennenkin (size, min, step)
    try: m_out = float(minsz) if minsz is not None else float(default_size)
    except: m_out = float(default_size)
    try: st_out = float(step or 0.0)
    except: st_out = 0.0
    return float(used), m_out, st_out
"""
s2,repl=re.subn(pat,new,s,flags=re.M)
open(p,'w',encoding='utf-8').write(s2)
print(f"Replaced pick_size (matched={repl})")
PY

echo "==> Patch 5: trainer_daemon.py leverage-metriikat"
backup "$TR"

# 5a) lisää instrumenttikartta-helperit (vain jos puuttuu)
grep -q '_lev_for(' "$TR" || python - "$TR" <<'PY'
import sys,re
p=sys.argv[1]
s=open(p,'r',encoding='utf-8').read()
anchor = "from datetime import datetime, timezone"
ins = """
# --- leverage helpers (instrument_map.json) ---
import json
INSTR_MAP_PATH = "/root/pro_botti/data/instrument_map.json"
try:
    INSTR_MAP = json.load(open(INSTR_MAP_PATH,"r",encoding="utf-8"))
except Exception:
    INSTR_MAP = {}

def _norm_sym(s: str) -> str:
    s = (s or "").upper()
    return s[:-4] + "USD" if s.endswith("USDT") else s

def _lev_for(sym: str) -> float:
    d = INSTR_MAP.get(sym) or {}
    mf = d.get("margin_factor"); lev = d.get("leverage")
    try: mf = float(mf) if mf is not None else None
    except: mf = None
    try: lev = float(lev) if lev is not None else None
    except: lev = None
    if (lev is None) and (mf not in (None,0)):
        lev = 100.0/float(mf)
    return float(lev or 1.0)
# --- end leverage helpers ---
"""
s=s.replace(anchor, anchor + ins)
open(p,'w',encoding='utf-8').write(s)
print("Inserted leverage helpers")
PY

# 5b) korvaa metrics_from_preds vivullisella versiolla
python - "$TR" <<'PY'
import re,sys
p=sys.argv[1]
s=open(p,'r',encoding='utf-8').read()
pat=r"def metrics_from_preds\\(close: pd\\.Series, y_true: np\\.ndarray, p: np\\.ndarray\\):[\\s\\S]*?return \\{\\\"pnl\\\": float\\(pnl\\), \\\"win_rate\\\": float\\(wr\\), \\\"pf\\\": float\\(pf\\)\\}"
new = """def metrics_from_preds(close: pd.Series, y_true: np.ndarray, p: np.ndarray, lev: float = 1.0):
    \"\"\"P&L-approx vivulla: ret1 * sign * lev; PF vivulla skaalatuista tuotoista.\"\"\"
    ret1 = close.pct_change().shift(-1).values
    long = p>=0.55; short = p<=0.45
    sig = np.where(long, 1, np.where(short,-1,0))
    pnl_step = (sig * ret1[:len(sig)]) * float(max(1.0, lev))
    pnl = float(np.nansum(pnl_step))
    wins = int((pnl_step > 0).sum())
    losses = int((pnl_step < 0).sum())
    wr = wins / max(1, wins+losses)
    gross_pos = float(np.sum((pnl_step > 0) * pnl_step))
    gross_neg = float(np.sum((pnl_step < 0) * (-pnl_step)))
    pf = gross_pos / (gross_neg if gross_neg > 1e-12 else 1e-12)
    return {"pnl": pnl, "win_rate": float(wr), "pf": float(pf)}"""
s2,repl = re.subn(pat,new,s,flags=re.M)
open(p,'w',encoding='utf-8').write(s2)
print(f"Replaced metrics_from_preds (matched={repl})")
PY

# 5c) lisää train_one:lle vivun haku ja välitys metricsille (vain jos puuttuu)
grep -q 'lev = _lev_for(_norm_sym(sym))' "$TR" || \
  sed -i 's@met = metrics_from_preds(close.iloc\[len(Xtr):\], yte, p)@lev = _lev_for(_norm_sym(sym))\n    met = metrics_from_preds(close.iloc[len(Xtr):], yte, p, lev=lev)@' "$TR"

echo "OK"
