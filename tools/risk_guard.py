#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
risk_guard.py – suojat, ATR ja treidipäiväkirja live- ja koulutusputkea varten

Tarjoaa:
- atr(symbol, tf): float
- atr(symbol, tf+"_ref"): float (viite-ATR esim. median lähimenneisyydestä)
- make_sl_tp(symbol, side, entry_px, atr, sl_mult, tp_mult) -> (sl, tp)
- todays_realized_R() -> float | None   (päivän realisoitu R-summa; None jos ei laskettavissa)
- update_trade_journal(event_dict)      (kirjaa OPEN/SCALE_IN/CLOSE jne.)
- position_R_progress(open_position_dict) -> (current_R, can_add_more, orig_size, adds_done)

Riippuvuudet: pandas, numpy (jos ei saatavilla tai data puuttuu, funktiot palauttavat None/fallit eivätkä kaada liveä)
Dataoletukset:
- Historia löytyy kansiosta /root/pro_botti/data/history  nimellä  {SYMBOL}_{TF}.parquet  tai  .csv
  ja sisältää sarakkeet: time, open, high, low, close (lowercase riittää)
- CapitalClient.list_open_positions() palauttaa dictin, jonka puitteissa:
  p["position"]["openLevel"], p["position"]["size"], p["position"]["direction"] ("BUY"/"SELL")
  p["position"].get("stopLevel")   (voi puuttua)
  p["market"].get("bid") / .get("offer") tai .get("lastTraded")
Jos rakenne poikkeaa, funktiot palauttavat varovaiset oletukset.

Ympäristömuuttujat (valinnaisia):
- VOL_ATR_LOOKBACK (oletus 14)
- ATR_REF_WINDOW_MULT (oletus 5; viite-ATR lasketaan median viimeisten (lookback*mult) arvojen yli)
- SCALE_IN_MAX_ADDS (oletus 2; käytetään can_add_more-lippuun yhdessä päiväkirjan kanssa)
"""

from __future__ import annotations
import os, json, math
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any

# Pandas/numpy valinnaisesti; jos puuttuvat, guardit eivät kaadu
try:
    import pandas as pd
    import numpy as np
except Exception:  # pragma: no cover
    pd = None
    np = None

ROOT   = Path("/root/pro_botti")
HIST   = ROOT / "data" / "history"
STATE  = ROOT / "state"
STATE.mkdir(parents=True, exist_ok=True)

JOURNAL = STATE / "trade_journal.jsonl"     # rivikohtainen JSONL
SCALE_STATE = STATE / "scale_state.json"    # synteettinen lisäyslaskuri (fallback)

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _envf(name:str, default:float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return float(default)

def _load_df(symbol:str, tf:str) -> Optional["pd.DataFrame"]:
    """Lataa historian (parquet > csv). Palauttaa None jos ei saatavilla."""
    if pd is None:
        return None
    base = f"{symbol.upper()}_{tf}.parquet"
    p = HIST / base
    if p.exists():
        try:
            df = pd.read_parquet(p)
            return df
        except Exception:
            pass
    # csv fallback
    p = HIST / f"{symbol.upper()}_{tf}.csv"
    if p.exists():
        try:
            df = pd.read_csv(p)
            return df
        except Exception:
            pass
    return None

def _norm_cols(df: "pd.DataFrame") -> "pd.DataFrame":
    """Yhtenäistä sarakeotsikot: time/open/high/low/close"""
    cols = {c.lower(): c for c in df.columns}
    need = ["time", "open", "high", "low", "close"]
    miss = [c for c in need if c not in cols]
    if miss:
        # yritetään parhaita arvauksia
        for c in list(df.columns):
            lc = c.lower()
            if lc.startswith("date") or lc.startswith("time"):
                cols.setdefault("time", c)
            if lc.startswith("o"):
                cols.setdefault("open", c)
            if lc.startswith("h"):
                cols.setdefault("high", c)
            if lc.startswith("l"):
                cols.setdefault("low", c)
            if lc.startswith("c"):
                cols.setdefault("close", c)
    m = {v: k for k, v in cols.items() if k in ["time","open","high","low","close"]}
    df = df.rename(columns=m)
    return df

def _sma(a: "np.ndarray", n: int) -> "np.ndarray":
    if np is None:  # pragma: no cover
        return None
    if n <= 1:
        return a
    w = np.ones(n, dtype=float) / n
    return np.convolve(a, w, mode="valid")

def _atr_series(df: "pd.DataFrame", lookback: int) -> Optional["np.ndarray"]:
    """PERIODIN ATR-sarja (SMA TR:stä), pituus len(df)-lookback+1"""
    if pd is None or np is None or df is None or len(df) < (lookback + 2):
        return None
    df = _norm_cols(df.copy())
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = _sma(tr, lookback)
    return atr

def atr(symbol: str, tf: str) -> Optional[float]:
    """Palauta tämänhetkinen ATR tai viite-ATR (tf+"_ref")."""
    look = int(_envf("VOL_ATR_LOOKBACK", 14))
    is_ref = False
    base_tf = tf
    if tf.endswith("_ref"):
        is_ref = True
        base_tf = tf[:-4]  # poista "_ref"

    df = _load_df(symbol, base_tf)
    if df is None:
        return None

    atr_arr = _atr_series(df, look)
    if atr_arr is None or len(atr_arr) == 0:
        return None

    if not is_ref:
        # viimeisin ATR (sma-sarjan uusin)
        return float(atr_arr[-1])

    # viite: median viimeisten (lookback * ATR_REF_WINDOW_MULT) havaintojen yli
    mult = max(2, int(_envf("ATR_REF_WINDOW_MULT", 5)))
    k = min(len(atr_arr), look * mult)
    ref = float(np.median(atr_arr[-k:]))
    return ref

def make_sl_tp(symbol: str, side: str, entry_px: float, atr_val: float,
               sl_mult: float, tp_mult: float) -> Tuple[Optional[float], Optional[float]]:
    """ATR-pohjainen SL/TP; jos atr/entry puuttuu palautetaan (None,None)."""
    try:
        entry = float(entry_px)
        atrf = float(atr_val)
    except Exception:
        return None, None
    s = side.upper()
    if s == "BUY":
        sl = max(1e-12, entry - sl_mult * atrf)
        tp = max(1e-12, entry + tp_mult * atrf)
    elif s == "SELL":
        sl = max(1e-12, entry + sl_mult * atrf)  # shortissa SL yli entryn
        tp = max(1e-12, entry - tp_mult * atrf)
    else:
        return None, None
    return (float(sl), float(tp))

# ---------- Päiväkirja / R-laskenta ----------

def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _read_jsonl(path: Path):
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    yield json.loads(ln)
                except Exception:
                    continue
    except Exception:
        return

def _same_day_utc(iso_ts: str, day_key: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d") == day_key
    except Exception:
        return False

def update_trade_journal(ev: Dict[str, Any]) -> None:
    """
    Odotettu minimi:
    - event: "OPEN" | "SCALE_IN" | "CLOSE"
    - symbol, side, size
    - entry, sl, tp (OPEN)
    - exit (CLOSE)
    Lisämausteet: R_now, pf_med, ai_thr, tf
    """
    # Täydennä riskiperus jos mahdollista
    if ev.get("event") == "OPEN":
        try:
            entry = float(ev.get("entry"))
            sl    = float(ev.get("sl")) if ev.get("sl") is not None else None
            if sl is not None:
                risk_per_unit = abs(entry - sl)
                ev["risk_per_unit"] = risk_per_unit
                ev["orig_size"] = float(ev.get("size", 0.0))
        except Exception:
            pass

    if ev.get("event") == "CLOSE":
        # Laske realisoitu R, jos saadaan tarvittavat kentät
        try:
            entry = float(ev.get("entry"))
            exitp = float(ev.get("exit"))
            side  = (ev.get("side","") or "").upper()
            rpu   = float(ev.get("risk_per_unit"))
            if rpu > 0 and side in ("BUY","SELL"):
                pnl = (exitp - entry) if side == "BUY" else (entry - exitp)
                ev["r_realized"] = pnl / rpu
        except Exception:
            pass

    _append_jsonl(JOURNAL, ev)

    # Päivitä myös synteettinen lisäysloki (fallback adds_donein laskentaan)
    if ev.get("event") == "OPEN":
        # nollaa laskuri
        st = _load_scale_state()
        sym = (ev.get("symbol") or "").upper()
        st[sym] = {"orig_size": float(ev.get("size", 0.0)), "adds_done": 0}
        _save_scale_state(st)
    elif ev.get("event") == "SCALE_IN":
        st = _load_scale_state()
        sym = (ev.get("symbol") or "").upper()
        d = st.get(sym, {"orig_size": 0.0, "adds_done": 0})
        d["adds_done"] = int(d.get("adds_done", 0)) + 1
        st[sym] = d
        _save_scale_state(st)

def todays_realized_R() -> Optional[float]:
    """
    Summaa kuluvan UTC-päivän realisoidut R:t.
    Jos ei löydy tietoa, palauttaa 0.0 (turvallinen – ei käynnistä cooldownia koska raja on negatiivinen).
    """
    day = _utcnow().strftime("%Y-%m-%d")
    total = 0.0
    found = False
    for ev in _read_jsonl(JOURNAL) or []:
        if ev.get("event") == "CLOSE" and ev.get("ts") and _same_day_utc(ev["ts"], day):
            r = ev.get("r_realized")
            if isinstance(r, (int, float)):
                total += float(r)
                found = True
    if not found:
        return 0.0
    return total

def _load_scale_state() -> Dict[str, Any]:
    try:
        return json.loads(SCALE_STATE.read_text())
    except Exception:
        return {}

def _save_scale_state(st: Dict[str, Any]) -> None:
    try:
        SCALE_STATE.write_text(json.dumps(st, indent=2))
    except Exception:
        pass

def position_R_progress(open_pos: Dict[str, Any]) -> Tuple[float, bool, float, int]:
    """
    Arvioi nykyisen position R-kehityksen ja skaalausmahdollisuuden.

    Palauttaa: (current_R, can_add_more, orig_size, adds_done)

    Lähteet:
    - entry  = p["position"]["openLevel"]
    - size   = p["position"]["size"]
    - side   = p["position"]["direction"]  ("BUY"/"SELL")
    - sl     = p["position"].get("stopLevel")
    - price  = p["market"].get("bid"/"offer"/"lastTraded")
    - symbol = p["market"].get("epic") (tai vastaava)

    Jos data ei riitä, palauttaa (0, False, size, adds_done).
    """
    try:
        pos = open_pos.get("position", {}) or {}
        mkt = open_pos.get("market", {}) or {}
        entry = float(pos.get("openLevel"))
        size  = float(pos.get("size", 0.0))
        side  = (pos.get("direction","") or "").upper()
        sl    = pos.get("stopLevel")
        sl    = float(sl) if sl is not None else None

        price = None
        for k in ("lastTraded", "mid", "offer", "bid"):
            v = mkt.get(k)
            if v is not None:
                try:
                    price = float(v); break
                except Exception:
                    continue

        # symbol (epic -> symbol), käytetään vain scale_state-avaimena
        sym = (mkt.get("epic") or "").upper()

        if entry is None or price is None or sl is None or side not in ("BUY","SELL"):
            # ei voida laskea R:ää
            adds_done, orig_size = _adds_done_for(sym), _orig_size_for(sym, default=size)
            return 0.0, False, orig_size, adds_done

        risk_per_unit = abs(entry - sl)
        if risk_per_unit <= 0:
            adds_done, orig_size = _adds_done_for(sym), _orig_size_for(sym, default=size)
            return 0.0, False, orig_size, adds_done

        pnl = (price - entry) if side == "BUY" else (entry - price)
        curR = pnl / risk_per_unit

        # montako lisäystä sallitaan
        max_adds = int(max(0, _envf("SCALE_IN_MAX_ADDS", 2)))
        adds_done, orig_size = _adds_done_for(sym), _orig_size_for(sym, default=size)
        can_add = adds_done < max_adds

        return float(curR), bool(can_add), float(orig_size), int(adds_done)

    except Exception:
        # konservatiivinen fallback
        size  = float(((open_pos.get("position") or {}).get("size", 0.0)) or 0.0)
        mkt   = open_pos.get("market", {}) or {}
        sym   = (mkt.get("epic") or "").upper()
        adds_done, orig_size = _adds_done_for(sym), _orig_size_for(sym, default=size)
        return 0.0, False, float(orig_size), int(adds_done)

def _adds_done_for(sym: str) -> int:
    st = _load_scale_state()
    d = st.get((sym or "").upper(), {})
    try:
        return int(d.get("adds_done", 0))
    except Exception:
        return 0

def _orig_size_for(sym: str, default: float = 0.0) -> float:
    st = _load_scale_state()
    d = st.get((sym or "").upper(), {})
    try:
        v = d.get("orig_size")
        return float(v) if v is not None else float(default)
    except Exception:
        return float(default)
