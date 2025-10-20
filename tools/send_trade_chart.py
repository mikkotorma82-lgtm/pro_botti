#!/usr/bin/env python3
from __future__ import annotations
import os, io, sys, argparse, json, time, urllib.request, math
from pathlib import Path
from typing import Optional, Tuple
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
    if isinstance(d.index, pd.DatetimeIndex):
        return d
    for col in ("time","timestamp","ts","date"):
        if col in d.columns:
            s = d[col]
            try:
                if np.issubdtype(s.dtype, np.number):
                    unit = "ms" if float(s.iloc[-1]) > 1e12 else "s"
                    dt = pd.to_datetime(s, unit=unit, utc=True)
                else:
                    dt = pd.to_datetime(s, utc=True, errors="coerce")
                d = d.set_index(dt); d.index.name = None
                return d
            except Exception:
                pass
    try:
        d.index = pd.to_datetime(d.index, utc=True, errors="coerce")
    except Exception:
        pass
    return d

def _tf_seconds(tf: str) -> int:
    return {"15m":900, "1h":3600, "4h":14400}.get(tf, 3600)

def _parse_ts(val: Optional[str]) -> Optional[int]:
    if not val: return None
    val = str(val).strip()
    # epoch seconds
    if val.isdigit():
        try: return int(val)
        except Exception: return None
    # ISO8601
    try:
        return int(pd.Timestamp(val).tz_convert("UTC").timestamp())
    except Exception:
        try:
            return int(pd.Timestamp(val, tz="UTC").timestamp())
        except Exception:
            return None

def _slice_window(d: pd.DataFrame, entry_ts: int, exit_ts: int, pad_bars: int = 6) -> pd.DataFrame:
    # d index on UTC DatetimeIndex
    t = d.index.view("int64") // 10**9
    # lähin bar >= ts
    start_idx = int(np.searchsorted(t.values, entry_ts, side="left"))
    end_idx   = int(np.searchsorted(t.values, exit_ts, side="left"))
    start = max(0, start_idx - pad_bars)
    end   = min(len(d)-1, max(end_idx, start_idx) + pad_bars)
    return d.iloc[start:end+1].copy()

def build_chart(symbol: str, tf: str,
                entry_px: Optional[float], exit_px: Optional[float],
                entry_ts: Optional[int], exit_ts: Optional[int]) -> Tuple[bytes, str]:
    # Päätä hakumäärä ajanjakson mukaan
    bars = 200
    if entry_ts and exit_ts:
        dur = max(0, exit_ts - entry_ts)
        bars = int(math.ceil(dur / _tf_seconds(tf))) + 20  # +puskuri

    df = capital_get_candles_df(symbol, tf, total_limit=bars if bars>0 else 200)
    if df.empty or not all(c in df.columns for c in ("open","high","low","close")):
        raise RuntimeError("empty or missing OHLC data")

    d = _ensure_dtindex(df)
    if entry_ts and exit_ts:
        d = _slice_window(d, entry_ts, exit_ts, pad_bars=6)

    addplots = []
    title = f"{symbol} {tf}  bars={len(d)}"
    if entry_px:
        addplots.append(mpf.make_addplot([entry_px]*len(d), type='line', color="g"))
        title += f"  entry={entry_px:.5f}"
    if exit_px:
        addplots.append(mpf.make_addplot([exit_px]*len(d), type='line', color="r"))
        title += f"  exit={exit_px:.5f}"

    fig, _ = mpf.plot(
        d, type='candle', style='charles',
        addplot=addplots, volume=False,
        datetime_format='%Y-%m-%d %H:%M',
        returnfig=True, figscale=1.1, figratio=(16,9)
    )
    fig.suptitle(title)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    # caption + tulos
    pnl_txt = ""
    if entry_px and exit_px and (entry_ts and exit_ts):
        # suunta päätellään hinnoista; voidaan laajentaa jos tarjoat action
        pnl = exit_px - entry_px
        pnl_txt = f"\nResult: {pnl:+.5f}"
    cap = f"{symbol} {tf}\nWindow: " \
          f"{(pd.to_datetime(entry_ts, unit='s', utc=True).strftime('%Y-%m-%d %H:%M') if entry_ts else '?')} → " \
          f"{(pd.to_datetime(exit_ts,  unit='s', utc=True).strftime('%Y-%m-%d %H:%M') if exit_ts else '?')}" \
          f"{pnl_txt}"
    return buf.getvalue(), cap

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--tf", required=True, choices=["15m","1h","4h"])
    ap.add_argument("--entry", type=float, default=None, help="Entry price (for horizontal guide)")
    ap.add_argument("--exit",  type=float, default=None, help="Exit price (for horizontal guide)")
    ap.add_argument("--entry_ts", type=str, default=None, help="Entry time (epoch seconds or ISO8601)")
    ap.add_argument("--exit_ts",  type=str, default=None, help="Exit time (epoch seconds or ISO8601)")
    args = ap.parse_args()

    ent_ts = _parse_ts(args.entry_ts)
    exi_ts = _parse_ts(args.exit_ts)

    png, caption = build_chart(args.symbol, args.tf, args.entry, args.exit, ent_ts, exi_ts)
    ts = int(time.time())
    p = OUTDIR / f"{args.symbol.replace('/','_')}__{args.tf}__{ts}.png"
    p.write_bytes(png)
    ok = _send_telegram_photo(png, caption)
    print(f"[CHART] saved={p} sent={ok}")

if __name__ == "__main__":
    main()
