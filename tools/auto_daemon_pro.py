#!/usr/bin/env python3
from __future__ import annotations
import os, json, time, traceback
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

from tools.capital_session import capital_rest_login, capital_get_candles_df, capital_get_bid_ask
from tools.consensus_engine import consensus_signal
from tools.signal_executor import execute_action
from tools.frequency_controller import record_trade, calibrate_thresholds
from tools.symbol_resolver import read_symbols

STATE = Path(__file__).resolve().parents[1] / "state"
STATE.mkdir(parents=True, exist_ok=True)
LIVE_STATE = STATE / "live_state.json"   # { key: { "last_sig": int, "pos": int, "equity": float } }

def _load_json(p: Path, default: Any) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:
        return default

def _save_json(p: Path, obj: Any) -> None:
    try:
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception:
        pass

def _equity() -> float:
    try:
        from tools.ledger import current_equity  # optional
        return float(current_equity())
    except Exception:
        return float(os.getenv("STARTING_EQUITY", "10000"))

def _bar_align(tf: str) -> int:
    return {"15m": 900, "1h": 3600, "4h": 14400}.get(tf, 3600)

def main_loop():
    print("[AUTO] starting auto_daemon_pro loop…", flush=True)

    # Login retry (ei kaadu jos hetkellinen virhe)
    sess_try = 0
    while True:
        try:
            capital_rest_login()
            break
        except Exception as e:
            sess_try += 1
            wait = min(300, 5 * sess_try)
            print(f"[AUTO] capital_rest_login failed: {e} -> retry in {wait}s", flush=True)
            time.sleep(wait)

    symbols = read_symbols()
    tfs = [s.strip() for s in (os.getenv("LIVE_TFS") or "15m,1h").split(",") if s.strip()]
    max_total = int(os.getenv("LIVE_TOTAL_BARS", "600"))
    sleep_min = int(os.getenv("LIVE_MIN_SLEEP", "15"))

    live_state = _load_json(LIVE_STATE, {})
    last_train = 0
    last_calib = 0

    while True:
        try:
            now = int(time.time())

            # Viikkotreeni (taustalle, ei blokkaa loopkia)
            if now - last_train > 12 * 3600 and time.gmtime(now).tm_wday == 6 and time.gmtime(now).tm_hour == 2:
                last_train = now
                os.system("python -m tools.train_wfa_pro >/dev/null 2>&1 &")

            # Päivittäinen kynnyskalibrointi kohti freq-targetia
            if now - last_calib > 3600:
                last_calib = now
                changed = calibrate_thresholds(k=0.05)
                if changed:
                    print(f"[AUTO] frequency controller adjusted thresholds on {changed} model(s)", flush=True)

            # Live-signaalit + toimeksiannot
            for sym in symbols:
                for tf in tfs:
                    reg = _load_json(STATE / "models_pro.json", {"models": []})
                    rows = [m for m in reg.get("models", []) if m.get("symbol") == sym and m.get("tf") == tf and m.get("strategy") == "CONSENSUS"]
                    if not rows:
                        continue
                    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
                    cfg = rows[0].get("config") or {}

                    df = capital_get_candles_df(sym, tf, total_limit=max_total)
                    if df.empty or len(df) < 50:
                        continue

                    sig = consensus_signal(df, cfg)
                    last_sig = int(sig[-1]) if len(sig) else 0
                    key = f"{sym}__{tf}"
                    prev = int(live_state.get(key, {}).get("last_sig", 0))

                    action = "HOLD"
                    if prev <= 0 and last_sig > 0:
                        action = "BUY"
                    if prev >= 0 and last_sig < 0:
                        action = "SELL" if os.getenv("LIVE_SHORTS", "0") == "1" else "HOLD"

                    if action in ("BUY", "SELL"):
                        ba = capital_get_bid_ask(sym)
                        px = (ba[1] if action == "BUY" else ba[0]) if ba else float(df["close"].iloc[-1])
                        res = execute_action(sym, tf, action, px, equity=_equity())
                        if res:
                            record_trade(sym, tf)
                            print(f"[AUTO] {sym} {tf}: {action} executed", flush=True)
                        else:
                            print(f"[AUTO] {sym} {tf}: {action} skipped (risk/guard/router)", flush=True)

                    live_state[key] = {"last_sig": last_sig, "pos": 0, "equity": _equity()}

            _save_json(LIVE_STATE, live_state)

        except Exception as e:
            print("[AUTO] loop error:", e, flush=True)
            traceback.print_exc()

        step = min(_bar_align(tf) for tf in tfs) if tfs else 60
        time.sleep(max(sleep_min, step // 5))

if __name__ == "__main__":
    main_loop()
