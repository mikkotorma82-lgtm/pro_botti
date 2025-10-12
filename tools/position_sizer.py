#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
position_sizer.py — riskipohjainen position koko + symbolikohtaiset riskiohjaukset

Toiminto:
- Lukee instrumenttien tiedot /root/pro_botti/data/instrument_map.json (min_trade_size, step, margin_factor, leverage).
- Lukee (valinnainen) /root/pro_botti/config/risk_overrides.json:
    { "BTCUSDT": 0.08, "US500": 0.04, ... }  # absoluuttinen riskiprosentti symbolille
- Tarjoaa:
    * instr_info(symbol) -> saneerattu dict instrumentista
    * effective_risk_pct(symbol, default_risk_pct) -> symbolikohtainen riskiprosentti
    * calc_order_size(symbol, price, free_balance, risk_pct_base, safety_mult=0.95, atr=None, vol_ref=None)
      -> (size, info_dict)

Huom:
- free_balance = vapaana oleva pääoma (esim. Capital "available").
- risk_budget = free_balance * effective_risk_pct * safety_mult
- Jos instrumentilla on leverage (lev), muodostetaan position_notional = risk_budget * lev (konservatiivinen).
  Muussa tapauksessa oletetaan 1x.
- size = position_notional / price, jonka jälkeen pyöristetään brokerin step/min vaatimus.
"""

import os
import json
import math
from pathlib import Path
from typing import Dict, Any, Tuple

ROOT = Path("/root/pro_botti")
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"

INSTR_PATH = DATA_DIR / "instrument_map.json"
RISK_OVR   = CONFIG_DIR / "risk_overrides.json"

# ---------- Helpers ----------

def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def _round_step(x: float, step: float) -> float:
    if step and step > 0:
        return math.floor(x / step) * step
    return float(x)

def _ceil_step(x: float, step: float) -> float:
    if step and step > 0:
        n = math.ceil(x / step)
        return n * step
    return float(x)

# ---------- Instruments ----------

_INSTR: Dict[str, Dict[str, Any]] = _load_json(INSTR_PATH) or {}

def instr_info(symbol: str) -> Dict[str, Any]:
    """
    Palauttaa instrumentin tiedot turvallisessa muodossa:
    {
        "min_trade_size": float|0.0,
        "step": float|0.0,
        "margin_factor": float|None,  # prosentteina esim. 5.0 = 5%
        "leverage": float|None,       # jos margin_factor on annettu, lev = 100.0/margin_factor
    }
    """
    d = dict(_INSTR.get(symbol, {}) or {})
    def _as_float(v):
        try:
            return float(v)
        except Exception:
            return None

    mf = _as_float(d.get("margin_factor"))
    lev = _as_float(d.get("leverage"))
    if lev is None and mf not in (None, 0):
        try:
            lev = 100.0 / float(mf)
        except Exception:
            lev = None

    try:
        mmin = float(d.get("min_trade_size")) if d.get("min_trade_size") is not None else 0.0
    except Exception:
        mmin = 0.0
    try:
        step = float(d.get("step")) if d.get("step") is not None else 0.0
    except Exception:
        step = 0.0

    return {
        "min_trade_size": max(0.0, mmin),
        "step": max(0.0, step),
        "margin_factor": mf if mf not in (None, float("nan")) else None,
        "leverage": lev if lev not in (None, float("nan")) else None,
    }

# ---------- Risk overrides ----------

_RISK_OVR_MAP: Dict[str, float] = _load_json(RISK_OVR) or {}

def refresh_overrides() -> None:
    """Lataa risk_overrides.json uudelleen (jos halutaan dynaamisesti päivittää lennossa)."""
    global _RISK_OVR_MAP
    _RISK_OVR_MAP = _load_json(RISK_OVR) or {}

def effective_risk_pct(symbol: str, default_risk_pct: float) -> float:
    """
    Palauttaa symbolikohtaisen riskiprosentin. Jos overrides:ssa on arvo, käytetään sitä.
    Muuten käytetään default_risk_pct:tä (esim. env RISK_PCT).
    """
    try:
        v = _RISK_OVR_MAP.get(symbol)
        if v is None:
            return float(default_risk_pct)
        v = float(v)
        # pientä varmistusta: järkevä alue 0..0.5
        if v < 0.0:
            v = 0.0
        if v > 0.5:
            v = 0.5
        return v
    except Exception:
        return float(default_risk_pct)

# ---------- Position sizing ----------

def calc_order_size(
    symbol: str,
    price: float,
    free_balance: float,
    risk_pct_base: float,
    safety_mult: float = 0.95,
    atr: float = None,
    vol_ref: float = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Laskee position koon riskibudjetista:

      risk_pct = effective_risk_pct(symbol, risk_pct_base)
      risk_budget = free_balance * risk_pct * safety_mult
      lev = instrumentin leverage (jos tiedossa, muuten 1)
      notional = risk_budget * lev
      raw_size = notional / price
      size = pyöristetty(min/step)

    Palauttaa (size, info_dict) — info_dict: kaikki välivaiheet + käytetyt parametrit.

    Huom: atr/vol_ref ei vielä skaalaa kokoa, mutta jätetään parametri tulevaan
    volatiliteetti-sääntöön (esim. jos ATR poikkeaa paljon omasta perusviitearvosta).
    """
    price = float(price or 0.0)
    free_balance = float(free_balance or 0.0)
    risk_pct = effective_risk_pct(symbol, float(risk_pct_base or 0.0))
    risk_pct = max(0.0, min(0.5, risk_pct))
    safety_mult = float(safety_mult or 1.0)
    safety_mult = max(0.0, min(1.0, safety_mult))

    info = instr_info(symbol)
    lev = info.get("leverage") or 1.0
    min_size = float(info.get("min_trade_size") or 0.0)
    step = float(info.get("step") or 0.0)

    # jos hinta puuttuu, ei pystytä laskemaan järkevästi
    if price <= 0.0:
        return 0.0, {
            "reason": "price<=0",
            "symbol": symbol,
            "price": price,
            "free_balance": free_balance,
            "risk_pct": risk_pct,
            "safety_mult": safety_mult,
            "leverage": lev,
            "min_trade_size": min_size,
            "step": step,
        }

    # riskibudjetti pääomasta
    risk_budget = free_balance * risk_pct * safety_mult

    # konservatiivinen malli: notional = risk_budget * lev
    notional = risk_budget * max(1.0, float(lev))

    raw_size = notional / price

    # pyöristykset brokkerin step/min mukaan: ensin alas stepille, sitten vähintään min_size
    sized = _round_step(raw_size, step)
    if min_size > 0 and sized < min_size:
        sized = _ceil_step(min_size, step or min_size)

    # ei negatiivisia/nollattomia
    sized = max(0.0, float(sized))

    meta = {
        "symbol": symbol,
        "price": price,
        "free_balance": free_balance,
        "risk_pct_base": risk_pct_base,
        "risk_pct_effective": risk_pct,
        "safety_mult": safety_mult,
        "risk_budget": risk_budget,
        "leverage": lev,
        "notional": notional,
        "raw_size": raw_size,
        "min_trade_size": min_size,
        "step": step,
        "final_size": sized,
        "atr": float(atr) if atr is not None else None,
        "vol_ref": float(vol_ref) if vol_ref is not None else None,
    }

    return sized, meta

# Pieni itseajo-testi:
if __name__ == "__main__":
    import pprint
    sym = os.getenv("TEST_SYMBOL", "BTCUSDT")
    px  = float(os.getenv("TEST_PX", "60000"))
    free = float(os.getenv("TEST_FREE", "1000"))
    base = float(os.getenv("TEST_RISK", "0.10"))
    size, meta = calc_order_size(sym, px, free, base)
    print(f"size={size}")
    pprint.pp(meta)
