from __future__ import annotations
import os, sys, json, time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from tools._dotenv import load_dotenv

load_dotenv()
from tools.provider_binance import klines as binance_kl
from tools.provider_capital import prices as cap_prices

HIST = Path("history")
HIST.mkdir(exist_ok=True)


def ms(dt):
    if isinstance(dt, int):
        return dt
    if isinstance(dt, float):
        return int(dt)
    if isinstance(dt, str):
        return int(datetime.fromisoformat(dt.replace("Z", "+00:00")).timestamp() * 1000)
    return int(dt.timestamp() * 1000)


def span(tf: str):
    now = datetime.now(timezone.utc)
    if tf == "15m":
        years = 2
    elif tf == "1h":
        years = 4
    else:
        years = 10
    start = now - timedelta(days=365 * years)
    return ms(start), ms(now)


def is_crypto(sym: str) -> bool:
    return sym.upper().endswith("USDT") or sym.upper() in {
        "BTCUSD",
        "ETHUSD",
        "XRPUSD",
        "SOLUSD",
    }


def load_universe() -> list[str]:
    import yaml

    y = Path("data/universe.yaml")
    if not y.exists():
        return [
            "EURUSD",
            "GBPUSD",
            "US500",
            "US100",
            "US30",
            "GER40",
            "FRA40",
            "UK100",
            "BTCUSDT",
            "ETHUSDT",
            "XAUUSD",
            "WTI",
            "AAPL",
            "MSFT",
            "NVDA",
        ]
    cfg = yaml.safe_load(y.read_text()) or {}
    out = []
    for _, arr in cfg.items():
        if isinstance(arr, list):
            for line in arr:
                if isinstance(line, str):
                    out += [
                        s for s in line.replace(",", " ").split() if s and s[0] != "#"
                    ]
    return list(dict.fromkeys(out))


def saverows(rows, path: Path):
    import pandas as pd

    if not rows:
        return False
    df = pd.DataFrame(rows)
    # normalisoi ts (ms → iso)
    if df["ts"].dtype != object:
        df["ts"] = df["ts"].astype("int64")
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    else:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").drop_duplicates("ts")
    df.to_csv(path, index=False)
    return True


def fetch_one(sym: str, tf: str):
    start, end = span(tf)
    out = []
    if is_crypto(sym):
        out = binance_kl(sym, tf, start, end)
    else:
        out = cap_prices(sym, tf, start, end)
    path = HIST / f"{sym.upper()}_{tf}.csv"
    ok = saverows(out, path)
    return {"symbol": sym, "tf": tf, "rows": len(out), "file": str(path), "ok": ok}


def main():
    import argparse, concurrent.futures as cf

    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", choices=["15m", "1h", "4h"], required=True)
    ap.add_argument("--symbols", nargs="*", default=None)
    args = ap.parse_args()
    syms = args.symbols or load_universe()
    res = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(lambda s: fetch_one(s, args.tf), syms):
            print(json.dumps(r, ensure_ascii=False))
            res.append(r)
    print(
        json.dumps(
            {
                "summary": {
                    "tf": args.tf,
                    "files": len(res),
                    "rows": sum(x["rows"] for x in res),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
