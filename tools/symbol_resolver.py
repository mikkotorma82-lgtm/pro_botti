#!/usr/bin/env python3
from __future__ import annotations
import os
from typing import List, Tuple

_MAP = {
    "US500": "US SPX 500",
    "NAS100": "US Tech 100",
    "GER40": "Germany 40",
    "UK100": "UK 100",
    "FRA40": "France 40",
    "EU50": "EU Stocks 50",
    "JPN225": "Japan 225",
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "XTIUSD": "OIL WTI",
    "XBRUSD": "OIL BRENT",
    "XNGUSD": "NATURAL GAS",
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "XRPUSD": "XRP/USD",
}

def _fx_with_slash(sym: str) -> str:
    if "/" in sym or len(sym) != 6:
        return sym
    a, b = sym[:3], sym[3:]
    if a.isalpha() and b.isalpha():
        return f"{a}/{b}"
    return sym

def normalize_symbol(s: str) -> str:
    u = s.strip().upper()
    if u in _MAP:
        return _MAP[u]
    if len(u) == 6 and u.isalpha():
        return _fx_with_slash(u)
    return s.strip()

def read_symbols() -> List[str]:
    raw = os.getenv("SYMBOLS", "")
    if raw.strip():
        items = [normalize_symbol(x) for x in raw.split(",") if x.strip()]
        return items
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "config" / "symbols.txt"
    if p.exists():
        items = [normalize_symbol(x) for x in p.read_text().splitlines() if x.strip() and not x.strip().startswith("#")]
        return items
    return ["US SPX 500","EUR/USD","GOLD","AAPL","BTC/USD"]

def normalize_all(symbols: List[str]) -> List[str]:
    return [normalize_symbol(x) for x in symbols]

def as_symbol_tf_pairs(symbols: List[str], tfs: List[str]):
    return [(s, tf) for s in symbols for tf in tfs]
