from __future__ import annotations
import time, typing as t, math, requests

BASE = "https://api.binance.com"


def _ival(tf: str) -> str:
    return {"15m": "15m", "1h": "1h", "4h": "4h"}.get(tf, "1h")


def klines(
    symbol: str, tf: str, start_ms: int | None, end_ms: int | None
) -> list[dict]:
    # Spot-klinet, limit 1000 / pyyntö
    out = []
    limit = 1000
    params = {"symbol": symbol.upper(), "interval": _ival(tf), "limit": limit}
    if start_ms:
        params["startTime"] = start_ms
    if end_ms:
        params["endTime"] = end_ms
    while True:
        r = requests.get(BASE + "/api/v3/klines", params=params, timeout=30)
        if r.status_code in (429, 418, 451, 500, 502, 503, 504):
            time.sleep(0.7)
            continue
        r.raise_for_status()
        arr = r.json()
        if not arr:
            break
        for a in arr:
            out.append(
                {
                    "ts": a[0],
                    "open": float(a[1]),
                    "high": float(a[2]),
                    "low": float(a[3]),
                    "close": float(a[4]),
                    "volume": float(a[5]),
                }
            )
        if len(arr) < limit:
            break
        params["startTime"] = arr[-1][0] + 1
        time.sleep(0.01)
    return out
