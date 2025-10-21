#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_gate.py — mallin kynnyslogiikka (ai_thresholds) ja päätöksen muodostus

Toiminto:
- Lukee mallimetan tiedostosta /root/pro_botti/models/pro_{SYMBOL}_{TF}.json
  ja hakee siitä ai_thresholds = {"long": x, "short": y}. Jos puuttuu -> 0.50/0.50
- Tarjoaa kaksi pääfunktiota:
    * load_thresholds(symbol, tf) -> (thr_long, thr_short, meta_dict)
    * gate_decision(symbol, tf, p_up=None, p_down=None, scores=None, side_hint=None, log=True)
        - p_up = mallin todennäköisyys nousulle (0..1)
        - p_down = laskulle (0..1); jos None -> käytetään 1-p_up
        - scores = vaihtoehtoinen: dict {"long": float, "short": float}
        - side_hint = "BUY"|"SELL" jos upstream haluaa pakottaa suuntaa (harvoin tarpeen)
        - palauttaa (decision, details_dict)

- details_dict sisältää: thresholds, scores, syy/why, meta (pf/wr/lev), lokimerkkijonon.

Ei ulkoisia riippuvuuksia. Telegram-lähetys on valinnainen (try/except).
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

ROOT = Path("/root/pro_botti")
MODELS_DIR = ROOT / "models"

def _load_meta(symbol: str, tf: str) -> Dict[str, Any]:
    p = MODELS_DIR / f"pro_{symbol}_{tf}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _thr_from_meta(meta: Dict[str, Any]) -> Tuple[float, float]:
    thr = meta.get("ai_thresholds")
    if isinstance(thr, dict):
        try:
            tl = float(thr.get("long", 0.50))
        except Exception:
            tl = 0.50
        try:
            ts = float(thr.get("short", 0.50))
        except Exception:
            ts = 0.50
    else:
        tl = ts = 0.50
    # turvarajat
    tl = max(0.30, min(0.995, tl))
    ts = max(0.30, min(0.995, ts))
    return tl, ts

def load_thresholds(symbol: str, tf: str) -> Tuple[float, float, Dict[str, Any]]:
    meta = _load_meta(symbol, tf)
    tl, ts = _thr_from_meta(meta)
    return tl, ts, meta

def _tg_send_safe(msg: str):
    try:
        from tools.tele import send as tgsend
        tgsend(msg)
    except Exception:
        pass

def gate_decision(
    symbol: str,
    tf: str,
    p_up: Optional[float] = None,
    p_down: Optional[float] = None,
    scores: Optional[Dict[str, float]] = None,
    side_hint: Optional[str] = None,
    log: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """
    Päätöksen muodostus: BUY / SELL / HOLD

    Ensisijainen käyttö:
        decision, info = gate_decision("BTCUSDT", "1h", p_up=0.61)

    Vaihtoehto:
        decision, info = gate_decision("BTCUSDT","1h", scores={"long":0.61,"short":0.38})

    Jos p_down puuttuu ja p_up annettu -> p_down = 1 - p_up (softmaxia arvaamatta).
    """
    tl, ts, meta = load_thresholds(symbol, tf)
    pf = float(meta.get("pf") or 0.0)
    wr = float(meta.get("win_rate") or 0.0)

    # lue pisteet
    if scores and isinstance(scores, dict):
        pL = float(scores.get("long") or 0.0)
        pS = float(scores.get("short") or (1.0 - pL))
    else:
        pL = float(p_up or 0.0)
        if p_down is None:
            pS = max(0.0, min(1.0, 1.0 - pL))
        else:
            pS = float(p_down)

    # päätös
    why = []
    decision = "HOLD"
    if side_hint in ("BUY", "SELL"):
        why.append(f"side_hint={side_hint}")
        decision = side_hint
    else:
        if pL >= tl and pL >= pS:
            decision = "BUY"
            why.append(f"pL≥thr_long ({pL:.3f}≥{tl:.3f})")
        elif pS >= ts and pS > pL:
            decision = "SELL"
            why.append(f"pS≥thr_short ({pS:.3f}≥{ts:.3f})")
        else:
            why.append(f"below thresholds (long {pL:.3f}<{tl:.3f}, short {pS:.3f}<{ts:.3f})")

    details = {
        "symbol": symbol,
        "tf": tf,
        "decision": decision,
        "thresholds": {"long": tl, "short": ts},
        "scores": {"long": pL, "short": pS},
        "why": "; ".join(why),
        "meta": {"pf": pf, "win_rate": wr, "leverage_used": meta.get("leverage_used")},
    }

    if log:
        line = (f"[AIGATE] {symbol} {tf} -> {decision} | "
                f"pL={pL:.3f} thrL={tl:.3f} | pS={pS:.3f} thrS={ts:.3f} | "
                f"pf={pf:.2f} wr={wr*100:.1f}% | {details['why']}")
        try:
            print(line, flush=True)
        except Exception:
            pass
        if os.getenv("AIGATE_TG", "0") == "1" and decision != "HOLD":
            _tg_send_safe(line)

    return decision, details

# Pieni itseajo-testi:
if __name__ == "__main__":
    d, info = gate_decision("BTCUSDT", "1h", p_up=0.61)
    print(d, info)
