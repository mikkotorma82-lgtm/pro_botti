#!/usr/bin/env python3
from __future__ import annotations
import os
from typing import List

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

    # Binance-tyyliset stableparit -> USD (BTCUSDT -> BTCUSD)
    if u.endswith("USDT"):
        u = u[:-1]  # poista T -> "...USD"

    # Tunnetut mapit suoraan
    if u in _MAP:
        return _MAP[u]

    # FX-tyyliset 6 merkin koodit -> lisää vinoviiva
    if len(u) == 6 and u.isalpha():
        return _fx_with_slash(u)

    # Muut (osakkeet, indeksien valmiit nimet)
    return s.strip()

def read_symbols() -> List[str]:
    raw = os.getenv("SYMBOLS", "")
    if raw.strip():
        return [normalize_symbol(x) for x in raw.split(",") if x.strip()]
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "config" / "symbols.txt"
    if p.exists():
        return [normalize_symbol(x) for x in p.read_text().splitlines() if x.strip() and not x.strip().startswith("#")]
    return ["US SPX 500","EUR/USD","GOLD","AAPL","BTC/USD"]
