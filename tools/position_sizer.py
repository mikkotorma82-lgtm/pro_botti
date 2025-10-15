#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

STATE = Path(__file__).resolve().parents[1] / "state"
REG = STATE / "models_pro.json"

def _load_models() -> dict:
    if not REG.exists():
        return {"models":[]}
    return json.loads(REG.read_text())

def _find_model(symbol: str, tf: str) -> Optional[dict]:
    reg = _load_models()
    rows = [m for m in reg.get("models", []) if m.get("symbol")==symbol and m.get("tf")==tf]
    if not rows:
        return None
    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
    return rows[0]

def _atr(df: pd.DataFrame, n: int = 14) -> float:
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    tr = np.maximum.reduce([h[1:]-l[1:], np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])])
    atr = pd.Series(tr).rolling(n, min_periods=n).mean().values
    return float(atr[-1]) if atr.size else 0.0

def _risk_pct_from_metrics(sharpe: float, pf: float, maxdd: float) -> float:
    # Perusajatus: jos malli hyvä (korkea Sharpe, PF), ja DD pieni (lähellä 0), voidaan riskata enemmän.
    # Skaalataan konservatiivisesti tuottopainotteisesti ja rajoitetaan 0.1%–1.0% treidiä kohden ennen leikkureita.
    base = 0.25  # bps -> 0.25% lähtötaso
    # Sharpe-skaala (Sharpe 1.0 lisää ~0.2%-yks), PF-skaala (PF 2.0 lisää ~0.2%-yks), DD pienentää riskia
    add = 0.2 * max(0.0, min(2.0, sharpe)) + 0.2 * max(0.0, min(2.0, (pf-1.0)))
    dd_pen = 0.5 * min(0.0, max(-0.5, maxdd))  # maxdd on negatiivinen, esim -0.2 -> -0.1 lisävähennys
    risk_pct = base + add + dd_pen
    return float(max(0.1, min(1.0, risk_pct)))  # 0.1%..1.0%

def pick_size(symbol: str, tf: str, last_price: float, equity: float, df_recent: Optional[pd.DataFrame]=None) -> float:
    """
    Palauttaa määrän (qty) instrumentin yksikköinä (CFD:ssä sopivaa 'size').
    AUTO-tila: laskee riskiprosentin mallimetriikoista + ATR-stopista.
    Leikkurit: RISK_MAX_PER_TRADE_PCT, MAX_CONCURRENT_POSITIONS.
    """
    mode = os.getenv("POSITION_SIZER_MODE","auto").lower()
    max_risk = float(os.getenv("RISK_MAX_PER_TRADE_PCT", "1.0"))
    fallback_risk = float(os.getenv("RISK_FALLBACK_PER_TRADE_PCT", "0.25"))
    stop_k = float(os.getenv("RISK_STOP_ATR_MULT","2.0"))

    # Malli ja metriikat
    mdl = _find_model(symbol, tf)
    if mode != "auto" or not mdl:
        risk_pct = min(max_risk, fallback_risk)
    else:
        m = mdl.get("metrics", {})
        sharpe = float(m.get("sh_oos_mean") or m.get("sharpe_oos_mean") or 0.0)
        pf = float(m.get("pf_oos_mean", 1.0))
        maxdd = float(m.get("maxdd_oos_min", 0.0))  # negatiivinen
        risk_pct = _risk_pct_from_metrics(sharpe, pf, maxdd)
        risk_pct = min(max_risk, risk_pct)

    # ATR-stopin etäisyys (arvio), jos df annettu; muuten käytä 1% oletusta
    if df_recent is not None and len(df_recent) >= 20:
        atr_val = _atr(df_recent, 14)
        stop_dist = max(1e-12, stop_k * atr_val)
    else:
        stop_dist = max(1e-12, 0.01 * last_price)

    risk_cash = equity * (risk_pct / 100.0)
    # qty ~ risk_cash / stop_dist (CFD-peruslogiikka). Klippaa ettei poistu nollaan.
    qty = max(0.0, risk_cash / stop_dist)

    # TODO: huomioi Capitalin min size / lotin tikki, jos tiedossa (cap specs)
    return float(qty)
