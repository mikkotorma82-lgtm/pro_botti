#!/usr/bin/env python3
from __future__ import annotations
import os, json, time, traceback, threading, subprocess, shlex
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

from tools.capital_session import capital_rest_login, capital_get_candles_df, capital_get_bid_ask
from tools.consensus_engine import consensus_signal
from tools.signal_executor import execute_action
from tools.frequency_controller import record_trade, calibrate_thresholds
from tools.symbol_resolver import read_symbols
from tools.capital_client import connect_and_prepare
# UUSI: meta-suodatin
from tools.meta_filter import should_take_trade

STATE = Path(__file__).resolve().parents[1] / "state"
STATE.mkdir(parents=True, exist_ok=True)
LIVE_STATE = STATE / "live_state.json"

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
        from tools.ledger import current_equity
        return float(current_equity())
    except Exception:
        return float(os.getenv("STARTING_EQUITY", "10000"))

def _bar_align(tf: str) -> int:
    return {"15m": 900, "1h": 3600, "4h": 14400}.get(tf, 3600)

def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key, str(default))
    try:
        cleaned = str(raw).split("#", 1)[0].strip()
        return int(cleaned)
    except Exception:
        print(f"[WARN] invalid int env {key}={raw!r} -> default {default}", flush=True)
        return default

# ----------------- Taustatreeni omassa säikeessä -----------------

_TRAIN_BG_LOCK = threading.Lock()
def _trainer_once() -> None:
    try:
        cwd = str(Path(__file__).resolve().parents[1])
        py = os.path.join(cwd, "venv", "bin", "python")
        cmd = f"{shlex.quote(py)} -m tools.train_wfa_pro && {shlex.quote(py)} -m tools.train_meta"
        print(f"[TRAIN_BG] start: {cmd}", flush=True)
        p = subprocess.run(cmd, cwd=cwd, shell=True)
        print(f"[TRAIN_BG] done: rc={p.returncode}", flush=True)
    except Exception as e:
        print(f"[TRAIN_BG][ERROR] {e}", flush=True)

def _trainer_loop() -> None:
    interval_min = _int_env("TRAIN_BG_INTERVAL_MIN", 360)
    sleep_s = max(60, interval_min * 60)
    print(f"[TRAIN_BG] loop start (interval={interval_min} min)", flush=True)
    time.sleep(10)
    while True:
        try:
            if _TRAIN_BG_LOCK.acquire(blocking=False):
                try:
                    _trainer_once()
                finally:
                    _TRAIN_BG_LOCK.release()
            else:
                print("[TRAIN_BG] previous run still active, skip", flush=True)
        except Exception as e:
            print(f"[TRAIN_BG][LOOP][ERROR] {e}", flush=True)
        time.sleep(sleep_s)

def main_loop():
    print("[AUTO] starting auto_daemon_pro loop…", flush=True)

    # Login + adoption/management
    sess_try = 0
    while True:
        try:
            capital_rest_login()
            connect_and_prepare()
            break
        except Exception as e:
            sess_try += 1
            wait = min(300, 5 * sess_try)
            print(f"[AUTO] capital_rest_login failed: {e} -> retry in {wait}s", flush=True)
            time.sleep(wait)

    if os.getenv("TRAIN_BG", "1") == "1":
        t = threading.Thread(target=_trainer_loop, name="trainer-bg", daemon=True)
        t.start()

    symbols = read_symbols()
    tfs = [s.strip() for s in (os.getenv("LIVE_TFS") or "15m,1h").split(",") if s.strip()]
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
                        # Meta-suodatin
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

            _save_json(LIVE_STATE, live_state)

        except Exception as e:
            print("[AUTO] loop error:", e, flush=True)
            traceback.print_exc()

        step = min(_bar_align(tf) for tf in tfs) if tfs else 60
        time.sleep(max(sleep_min, step // 5))

if __name__ == "__main__":
    main_loop()
