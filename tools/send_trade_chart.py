#!/usr/bin/env python3
from __future__ import annotations
import os, io, sys, argparse, json, time, urllib.request
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
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
            data.append(v)
            data.append(b"\r\n")
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

def build_chart(df: pd.DataFrame, symbol: str, tf: str, entry: Optional[float], exit_: Optional[float], action: Optional[str]) -> bytes:
    d = df.copy()
    d = d.rename(columns=str.title)
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
    fig = mpf.figure(figsize=(10,6), dpi=160)
    ax = fig.add_subplot(1,1,1)
    mpf.plot(d, type='candle', style='charles', addplot=addplots, ax=ax, volume=False, datetime_format='%Y-%m-%d %H:%M')
    ax.set_title(title)
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
    if df.empty:
        print("[ERR] empty candles", file=sys.stderr); sys.exit(1)

    png = build_chart(df.tail(args.bars), args.symbol, args.tf, args.entry, args.exit, args.action)
    ts = int(time.time())
    p = OUTDIR / f"{args.symbol.replace('/','_')}__{args.tf}__{ts}.png"
    p.write_bytes(png)
    cap = f"{args.symbol} {args.tf}\nOpenAI pattern gating: ON\nBars={args.bars}"
    ok = _send_telegram_photo(png, cap)
    print(f"[CHART] saved={p} sent={ok}")

if __name__ == "__main__":
    main()
