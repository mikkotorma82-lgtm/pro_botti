#!/usr/bin/env python3
from __future__ import annotations
import os, json, time, traceback, threading, subprocess, shlex
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
from tools.capital_session import capital_rest_login, capital_get_candles_df, capital_get_bid_ask
from tools.consensus_engine import consensus_signal
from tools.signal_executor import execute_action
from tools.frequency_controller import record_trade, calibrate_thresholds
from tools.symbol_resolver import read_symbols
from tools.capital_client import connect_and_prepare
from tools.meta_filter import should_take_trade

STATE = Path(__file__).resolve().parents[1] / "state"
LIVE_STATE = STATE / "live_state.json"
SELECTED = STATE / "selected_universe.json"
PRO_AGG = STATE / "agg_models_pro.json"  # uusi: preferoi aggregaattia

def _load_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text())
    except Exception:
        return default

def _equity() -> float:
    try:
        from tools.ledger import current_equity
        return float(current_equity())
    except Exception:
        return float(os.getenv("STARTING_EQUITY", "10000"))

def _bar_align(tf: str) -> int:
    return {"15m": 900, "1h": 3600, "4h": 14400}.get(tf, 3600)

def _selected_universe() -> Dict[str, List[str]]:
    if not SELECTED.exists():
        return {}
    try:
        obj = json.loads(SELECTED.read_text())
        combos = obj.get("combos", [])
        m: Dict[str, List[str]] = {}
        for c in combos:
            m.setdefault(c["symbol"], [])
            if c["tf"] not in m[c["symbol"]]:
                m[c["symbol"]].append(c["tf"])
        return m
    except Exception as e:
        print(f"[WARN] failed parsing selected_universe: {e}", flush=True)
        return {}

def _pro_registry() -> Dict[str, Any]:
    path = PRO_AGG if PRO_AGG.exists() else (STATE / "models_pro.json")
    return _load_json(path, {"models": []})

def main_loop():
    print("[AUTO] starting auto_daemon_pro loop…", flush=True)

    # Login
    while True:
        try:
            capital_rest_login()
            connect_and_prepare()
            break
        except Exception as e:
            wait = 15
            print(f"[AUTO] capital_rest_login failed: {e} -> retry in {wait}s", flush=True)
            time.sleep(wait)

    if os.getenv("TRAIN_BG", "0") == "1":
        t = threading.Thread(target=lambda: None, daemon=True)
        t.start()
        print("[TRAIN_BG] disabled by config", flush=True)

    mapping = _selected_universe()
    if mapping:
        symbols = list(mapping.keys()); tf_map = mapping
        print(f"[AUTO] using selected_universe.json (symbols={len(symbols)})", flush=True)
    else:
        symbols = read_symbols()
        tfs = [s.strip() for s in (os.getenv("LIVE_TFS") or "15m,1h").split(",") if s.strip()]
        tf_map = {sym: tfs for sym in symbols}
        print(f"[AUTO] using env universe (symbols={len(symbols)})", flush=True)

    max_total = int(os.getenv("LIVE_TOTAL_BARS", "600"))
    sleep_min = int(os.getenv("LIVE_MIN_SLEEP", "15"))
    live_state = _load_json(LIVE_STATE, {})
    last_calib = 0

    while True:
        try:
            now = int(time.time())
            if now - last_calib > 3600:
                last_calib = now
                changed = calibrate_thresholds(k=0.05)
                if changed:
                    print(f"[AUTO] frequency controller adjusted thresholds on {changed} model(s)", flush=True)

            pro_reg = _pro_registry()

            for sym in symbols:
                for tf in tf_map.get(sym, []):
                    rows = [m for m in pro_reg.get("models", [])
                            if m.get("symbol") == sym and m.get("tf") == tf and m.get("strategy") == "CONSENSUS"]
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
                    if prev <= 0 and last_sig > 0: action = "BUY"
                    if prev >= 0 and last_sig < 0 and os.getenv("LIVE_SHORTS", "0") == "1": action = "SELL"

                    if action in ("BUY", "SELL"):
                        ok, p = should_take_trade(sym, tf, action, df)
                        if not ok:
                            print(f"[META] {sym} {tf} {action} filtered p={p:.2f}", flush=True)
                        else:
                            ba = capital_get_bid_ask(sym)
                            px = (ba[1] if action == "BUY" else ba[0]) if ba else float(df["close"].iloc[-1])
                            res = execute_action(sym, tf, action, px, equity=_equity())
                            if res:
                                record_trade(sym, tf)
                                print(f"[AUTO] {sym} {tf}: {action} executed (p_meta={p:.2f})", flush=True)
                            else:
                                print(f"[AUTO] {sym} {tf}: {action} skipped (risk/guard/router)", flush=True)

                    live_state[key] = {"last_sig": last_sig, "pos": 0, "equity": _equity()}

            (STATE / "live_state.json").write_text(json.dumps(live_state, ensure_ascii=False, indent=2))

        except Exception as e:
            print("[AUTO] loop error:", e, flush=True)
            traceback.print_exc()

        min_step = min({"15m":900, "1h":3600, "4h":14400}[tf] for tfs in tf_map.values() for tf in tfs) if tf_map else 60
        time.sleep(max(sleep_min, min_step // 5))

if __name__ == "__main__":
    main_loop()
