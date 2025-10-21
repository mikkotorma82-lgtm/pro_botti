#!/usr/bin/env python3
from __future__ import annotations
import os, re, time, sys
import pandas as pd

try:
    import ccxt  # type: ignore
except Exception as e:
    print(f"[fail] import ccxt: {e}")
    sys.exit(1)

def have_capitalcom() -> bool:
    try:
        return hasattr(ccxt, "capitalcom") and ("capitalcom" in getattr(ccxt, "exchanges", []))
    except Exception:
        return hasattr(ccxt, "capitalcom")

def expand_candidates(alias: str) -> list[str]:
    ALIASES = {
        'US500':  ['US500','US SPX 500','SPX500','US 500'],
        'NAS100': ['US100','US TECH 100','NAS100'],
        'GER40':  ['DE40','GER40','Germany 40','DE 40'],
        'UK100':  ['UK100','FTSE 100','UK 100'],
        'FRA40':  ['FR40','France 40','FR 40'],
        'EU50':   ['EU50','EURO 50','EU 50'],
        'JPN225': ['JP225','Japan 225','JP 225'],
        'EURUSD': ['EUR/USD'],
        'GBPUSD': ['GBP/USD'],
        'USDJPY': ['USD/JPY'],
        'USDCHF': ['USD/CHF'],
        'AUDUSD': ['AUD/USD'],
        'USDCAD': ['USD/CAD'],
        'NZDUSD': ['NZD/USD'],
        'EURJPY': ['EUR/JPY'],
        'GBPJPY': ['GBP/JPY'],
        'XAUUSD': ['XAU/USD','GOLD'],
        'XAGUSD': ['XAG/USD','SILVER'],
        'XTIUSD': ['WTI','CRUDE OIL','US OIL','OIL'],
        'XBRUSD': ['BRENT'],
        'XNGUSD': ['NATURAL GAS','GAS'],
        'BTCUSD': ['BTC/USD','BTC-USD'],
        'ETHUSD': ['ETH/USD','ETH-USD'],
        'XRPUSD': ['XRP/USD','XRP-USD'],
        'AAPL':   ['AAPL'],
    }
    a = alias.strip()
    u = a.upper()
    c = [a, u]
    c += ALIASES.get(u, [])
    if re.fullmatch(r'[A-Z]{6}', u) and u.endswith('USD'):
        c.append(f"{u[:3]}/{u[3:]}")
    if u.endswith('USD') and '/' not in u:
        c.append(f"{u[:-3]}/USD")
    c.append(u.replace(' ', ''))
    # dedupe while preserving order
    out = []
    seen = set()
    for x in c:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def main():
    print("ccxt version:", getattr(ccxt, "__version__", "?"))
    if not have_capitalcom():
        print("[warn] This ccxt build does not expose 'capitalcom'.")
        print("      Try: pip install -U ccxt")
        print("      Available exchanges that contain 'cap':", [e for e in getattr(ccxt, "exchanges", []) if "cap" in e])
        sys.exit(2)

    ex = ccxt.capitalcom({'enableRateLimit': True})
    markets = ex.load_markets()
    mvals = list(markets.values())
    tfs = getattr(ex, "timeframes", {}) or {}
    print("Capital.com timeframes:", tfs)

    def resolve_symbol(alias: str) -> str | None:
        cands = expand_candidates(alias)
        for m in mvals:
            symU = m['symbol'].upper()
            idU  = str(m.get('id','')).upper()
            base = (m.get('base') or '')
            quote= (m.get('quote') or '')
            full = f"{base}/{quote}" if base and quote else ''
            for c in cands:
                cu = c.upper()
                if cu == symU or cu == idU or (full and cu == full.upper()):
                    return m['symbol']
                if cu in symU or cu in idU:
                    return m['symbol']
        return None

    SYMBOLS = os.getenv("SYMBOLS","US500,NAS100,GER40,UK100,EURUSD,XAUUSD,BTCUSD,AAPL").split(",")
    TEST_TFS = [tf for tf in ['15m','1h','4h'] if tf in tfs]

    delay = float(os.getenv("CAPITAL_DELAY","0.8"))

    print("\n[Mapping]")
    for alias in SYMBOLS:
        real = resolve_symbol(alias)
        print(f"- {alias} -> {real or '-'}")

    print("\n[Fetch test]")
    for alias in SYMBOLS:
        real = resolve_symbol(alias)
        if not real:
            print(f"- {alias}: NOT_FOUND in markets")
            continue
        for tf in TEST_TFS:
            try:
                time.sleep(delay)
                rows = ex.fetch_ohlcv(real, timeframe=tf, limit=60)
                if not rows:
                    print(f"- {alias} -> {real} tf={tf}: empty (0 rows)")
                    continue
                df = pd.DataFrame(rows, columns=['ts','open','high','low','close','volume'])
                df['time'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
                print(f"- {alias} -> {real} tf={tf}: ok, {len(df)} rows")
                print(df[['time','open','high','low','close','volume']].head(5).to_string(index=False))
            except Exception as e:
                print(f"- {alias} -> {real} tf={tf}: ERROR: {e}")

if __name__ == "__main__":
    main()
