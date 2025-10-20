#!/usr/bin/env python3
from __future__ import annotations
import os, io, sys, argparse, json, time, urllib.request
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

# Headless-renderointi
import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf

from tools.capital_session import capital_get_candles_df

STATE = Path(__file__).resolve().parents[1] / "state"
OUTDIR = STATE / "charts"; OUTDIR.mkdir(parents=True, exist_ok=True)

def _send_telegram_photo(png_bytes: bytes, caption: str) -> bool:
    tok = os.getenv("TELEGRAM_BOT_TOKEN"); chat = os.getenv("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("[TG] Missing TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID", file=sys.stderr)
        return False
    boundary = "-----agentboundary"
    data = []
    def part(k, v, filename=None, ctype=None):
        data.append(f"--{boundary}\r\n".encode())
        if filename:
            data.append(f'Content-Disposition: form-data; name="{k}"; filename="{filename}"\r\n'.encode())
            if ctype:
                data.append(f"Content-Type: {ctype}\r\n\r\n".encode())
            else:
                data.append(b"\r\n")
            data.append(v); data.append(b"\r\n")
        else:
            data.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    part("chat_id", chat)
    part("caption", caption[:1024])
    part("photo", png_bytes, filename="chart.png", ctype="image/png")
    data.append(f"--{boundary}--\r\n".encode())
    body = b"".join(data)
    url = f"https://api.telegram.org/bot{tok}/sendPhoto"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            json.loads(r.read() or b"{}")
        return True
    except Exception as e:
        print(f"[TG] sendPhoto failed: {e}", file=sys.stderr)
        return False

def _ensure_dtindex(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    # Jos index jo datetime
    if isinstance(d.index, pd.DatetimeIndex):
        return d
    # Tyypilliset aikakentät
    for col in ("time","timestamp","ts","date"):
        if col in d.columns:
            s = d[col]
            try:
                if np.issubdtype(s.dtype, np.number):
                    unit = "ms" if float(s.iloc[-1]) > 1e12 else "s"
                    dt = pd.to_datetime(s, unit=unit, utc=True)
                else:
                    dt = pd.to_datetime(s, utc=True, errors="coerce")
                d = d.set_index(dt)
                d.index.name = None
                return d
            except Exception:
                pass
    # Fallback: parsi indeksistä
    try:
        d.index = pd.to_datetime(d.index, utc=True, errors="coerce")
    except Exception:
        pass
    return d

def build_chart(df: pd.DataFrame, symbol: str, tf: str, entry: Optional[float], exit_: Optional[float], action: Optional[str]) -> bytes:
    d = _ensure_dtindex(df).copy()
    addplots = []
    title = f"{symbol} {tf}  bars={len(d)}"
    if entry and action:
        color = "g" if action.upper()=="BUY" else "r"
        addplots.append(mpf.make_addplot([entry]*len(d), type='line', color=color))
        title += f"  entry={entry:.5f}"
    if exit_ and action:
        color = "r" if action.upper()=="BUY" else "g"
        addplots.append(mpf.make_addplot([exit_]*len(d), type='line', color=color))
        title += f"  exit={exit_:.5f}"

    fig, _ = mpf.plot(
        d, type='candle', style='charles',
        addplot=addplots, volume=False,
        datetime_format='%Y-%m-%d %H:%M',
        returnfig=True, figsize=(10,6), dpi=160
    )
    fig.suptitle(title)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--tf", required=True, choices=["15m","1h","4h"])
    ap.add_argument("--bars", type=int, default=200)
    ap.add_argument("--entry", type=float, default=None)
    ap.add_argument("--exit",  type=float, default=None)
    ap.add_argument("--action", type=str, default=None, choices=["BUY","SELL"])
    args = ap.parse_args()

    df = capital_get_candles_df(args.symbol, args.tf, total_limit=args.bars)
    if df.empty or not all(c in df.columns for c in ("open","high","low","close")):
        print("[ERR] empty or missing OHLC data", file=sys.stderr); sys.exit(1)

    png = build_chart(df.tail(args.bars), args.symbol, args.tf, args.entry, args.exit, args.action)
    ts = int(time.time())
    p = OUTDIR / f"{args.symbol.replace('/','_')}__{args.tf}__{ts}.png"
    p.write_bytes(png)

    pnl_txt = ""
    if args.entry and args.exit and args.action:
        pnl = (args.exit - args.entry) * (1 if args.action=="BUY" else -1)
        pnl_txt = f"\nResult: {pnl:+.5f}"

    cap = f"{args.symbol} {args.tf}\nOpenAI pattern gating: {'ON' if os.getenv('OPENAI_PATTERN_ENABLED','0')=='1' else 'OFF'}\nBars={args.bars}{pnl_txt}"
    ok = _send_telegram_photo(png, cap)
    print(f"[CHART] saved={p} sent={ok}")

if __name__ == "__main__":
    main()
