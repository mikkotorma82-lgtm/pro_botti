#!/usr/bin/env python3
from __future__ import annotations
import os
from typing import List, Tuple

# Normalisoi käyttäjän symbolit Capital/IG-ystävällisiksi hakuavaimiksi.
# - Indeksit: US500->"US SPX 500", NAS100->"US Tech 100", GER40->"Germany 40", UK100->"UK 100", FRA40->"France 40",
#             EU50->"EU Stocks 50", JPN225->"Japan 225"
# - FX: EURUSD->"EUR/USD" jne (lisätään vinoviiva)
# - Commodities: XAUUSD->"GOLD", XAGUSD->"SILVER", XTIUSD->"OIL WTI", XBRUSD->"OIL BRENT", XNGUSD->"NATURAL GAS"
# - Crypto: BTCUSD->"BTC/USD", ETHUSD->"ETH/USD", XRPUSD->"XRP/USD"
# - Equities: AAPL, MSFT, NVDA, TSLA, META, AMZN (sellaisenaan)
_MAP = {
    "US500": "US SPX 500",
    "NAS100": "US Tech 100",
    "GER40": "Germany 40",
    "UK100": "UK 100",
    "FRA40": "France 40",
    "EU50": "EU Stocks 50",
    "JPN225": "Japan 225",
    # Commodities
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "XTIUSD": "OIL WTI",
    "XBRUSD": "OIL BRENT",
    "XNGUSD": "NATURAL GAS",
    # Crypto (use slash for safer search)
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "XRPUSD": "XRP/USD",
}

def _fx_with_slash(sym: str) -> str:
    # esim EURUSD -> EUR/USD
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
    # FX compact code -> with slash
    if len(u) == 6 and u.isalpha():
        return _fx_with_slash(u)
    # Equities and others: return as-is (AAPL, MSFT, NVDA, TSLA, META, AMZN)
    return s.strip()

def read_symbols() -> List[str]:
    # Ensisijaisesti SYMBOLS env (comma-separated)
    raw = os.getenv("SYMBOLS", "")
    if raw.strip():
        items = [normalize_symbol(x) for x in raw.split(",") if x.strip()]
        return items
    # Toissijaisesti config/symbols.txt (yksi per rivi)
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "config" / "symbols.txt"
    if p.exists():
        items = [normalize_symbol(x) for x in p.read_text().splitlines() if x.strip() and not x.strip().startswith("#")]
        return items
    # Fallback
    return ["US SPX 500","EUR/USD","GOLD","AAPL","BTC/USD"]

def normalize_all(symbols: List[str]) -> List[str]:
    return [normalize_symbol(x) for x in symbols]

def as_symbol_tf_pairs(symbols: List[str], tfs: List[str]) -> List[Tuple[str,str]]:
    out = []
    for s in symbols:
        for tf in tfs:
            out.append((s, tf))
    return out
