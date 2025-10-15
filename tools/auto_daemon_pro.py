#!/usr/bin/env python3
from __future__ import annotations
import os, json, time, traceback
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pandas as pd

from tools.capital_session import capital_rest_login, capital_get_candles_df, capital_get_bid_ask
from tools.consensus_engine import consensus_signal
from tools.signal_executor import execute_action
from tools.frequency_controller import record_trade, calibrate_thresholds

STATE = Path(__file__).resolve().parents[1] / "state"
STATE.mkdir(parents=True, exist_ok=True)
LIVE_STATE = STATE / "live_state.json"  # { sym__tf: { "last_sig": int, "pos": int, "equity": float } }
FEEDBACK = STATE / "live_feedback.json" # { entries: [ {symbol,tf,date,return,config} ] }

def _read_symbols() -> List[str]:
    raw = os.getenv("TRADE_SYMBOLS") or os.getenv("CAPITAL_SYMBOLS") or ""
    syms = [s.strip() for s in raw.split(",") if s.strip()]
    return syms or ["US SPX 500","EUR/USD","GOLD","AAPL","BTC/USD"]

def _load_json(p: Path, default: Any) -> Any:
    if not p.exists(): return default
    try: return json.loads(p.read_text())
    except Exception: return default

def _save_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2))

def _live_cfg_for(symbol: str, tf: str) -> Dict[str, Any]:
    reg = _load_json(STATE / "models_pro.json", {"models":[]})
    rows = [m for m in reg["models"] if m.get("symbol")==symbol and m.get("tf")==tf and m.get("strategy")=="CONSENSUS"]
    if not rows: return {}
    rows.sort(key=lambda r: int(r.get("trained_at", 0)), reverse=True)
    return rows[0].get("config") or {}

def _equity() -> float:
    # yksinkertaistettu; voit korvata broker_capital-tilin saldolla
    try:
        from tools.ledger import current_equity  # jos löytyy
        return float(current_equity())
    except Exception:
        return float(os.getenv("STARTING_EQUITY", "10000"))

def _bar_align(tf: str) -> int:
    # palauta sekunteina TF:n pituus (pollaus)
    return {"15m":900, "1h":3600, "4h":14400}.get(tf, 3600)

def main_loop():
    capital_rest_login()
    syms = _read_symbols()
    tfs = [s.strip() for s in (os.getenv("LIVE_TFS") or "15m,1h").split(",") if s.strip()]
    max_total = int(os.getenv("LIVE_TOTAL_BARS", "600"))
    sleep_min = int(os.getenv("LIVE_MIN_SLEEP", "15"))  # sekuntia minimi
    last_train = 0
    last_backfill = 0
    last_calib = 0
    live_state = _load_json(LIVE_STATE, {})

    while True:
        try:
            now = int(time.time())
            # Päivittäinen backfill (00:05 UTC)
            if now - last_backfill > 3600 and time.gmtime(now).tm_hour == 0 and time.gmtime(now).tm_min >= 5:
                last_backfill = now
                # Hiljainen backfill: ei estä liveä
                pass  # backfill voidaan ajaa erillisessä systemd timerissa

            # Viikkotreeni (su klo 02 UTC)
            if now - last_train > 12*3600 and time.gmtime(now).tm_wday == 6 and time.gmtime(now).tm_hour == 2:
                last_train = now
                os.system("python -m tools.train_wfa_pro >/dev/null 2>&1 &")

            # Päivittäinen kalibrointi kohti trade targetia (esim 10/päivä)
            if now - last_calib > 3600:
                last_calib = now
                calibrate_thresholds(k=0.05)

            # Live-signaalit (poll TF:n tahdissa; min sleep suojaa API:a)
            for sym in syms:
                for tf in tfs:
                    cfg = _live_cfg_for(sym, tf)
                    if not cfg:
                        continue
                    df = capital_get_candles_df(sym, tf, total_limit=max_total)
                    if df.empty or len(df) < 50:
                        continue
                    sig = consensus_signal(df, cfg)
                    last_sig = int(sig[-1]) if len(sig)>0 else 0
                    key = f"{sym}__{tf}"
                    prev = int(live_state.get(key, {}).get("last_sig", 0))

                    # signaalimuutokset -> toimi
                    action = "HOLD"
                    if prev <= 0 and last_sig > 0: action = "BUY"
                    if prev >= 0 and last_sig < 0: action = "SELL" if os.getenv("LIVE_SHORTS","0")=="1" else "HOLD"

                    if action in ("BUY","SELL"):
                        ba = capital_get_bid_ask(sym)
                        px = (ba[1] if action=="BUY" else ba[0]) if ba else float(df["close"].iloc[-1])
                        res = execute_action(sym, tf, action, px, equity=_equity())
                        if res:
                            record_trade(sym, tf)

                    live_state[key] = {"last_sig": last_sig, "pos": 0, "equity": _equity()}

            _save_json(LIVE_STATE, live_state)

        except Exception:
            traceback.print_exc()

        # dynaaminen sleep: pienin TF määrää tahdin
        step = min(_bar_align(tf) for tf in tfs)
        time.sleep(max(sleep_min, step // 5))

if __name__ == "__main__":
    main_loop()
