#!/usr/bin/env python3
from __future__ import annotations
import os, sys, time, json, traceback
from pathlib import Path
import pandas as pd
import numpy as np

from tools.strategies.momentum import momentum_signal
from tools.strategies.mean_reversion import mean_reversion_signal
from tools.strategies.ml_agents import ml_signal
from tools.strategies.stat_arb import stat_arb_signal
from utils.position_watcher import create_position_watcher
from tools.position_guard import guard_positions
from tools.tele import send as send_telegram, send_photo as send_telegram_photo
from tools.send_trade_chart import build_chart
from tools.tp_sl import compute_levels
# Lisää myöhemmin portfolio_manager, dashboard, backtest_engine jne.

# --- Strategioiden yhdistäjä ---
def select_strategy(df, params):
    sigs = {
        "momentum": momentum_signal(df, params),
        "mean_rev": mean_reversion_signal(df, params),
        "ml": ml_signal(df, params),
        "stat_arb": stat_arb_signal(df, params),
    }
    # Voit tehdä enemmän meta-oppijaa/ensembleä jatkossa
    best = max(sigs, key=lambda k: abs(sigs[k]))
    return sigs[best], best

def log(s: str):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    print(f"[{ts}] {s}", flush=True)

def main():
    SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT").split(",")
    TFS = os.getenv("TFS", "15m,1h,4h").split(",")
    POLL = int(os.getenv("POLL_SECS","60"))

    broker = ... # Luo oikea broker-instanssi
    position_watcher = create_position_watcher(broker, check_interval=30)
    log(f"[INFO] Start: SYMBOLS={SYMBOLS} TFS={TFS} POLL={POLL}")

    while True:
        try:
            for s in SYMBOLS:
                for tf in TFS:
                    # --- Hae data ---
                    df = fetch_ohlcv(s, tf, lookback_days=365)
                    if df is None or df.empty: continue
                    params = {} # Voit laajentaa strategioiden parametrit
                    signal, strat = select_strategy(df, params)
                    # --- Kauppa ---
                    if signal == 1:
                        log(f"[TRADE] {s} {tf}: BUY ({strat})")
                        # Luo kauppa, kirjaa kauppa, riskienhallinta, TP/SL
                        entry_px = float(df["close"].iloc[-1])
                        levels = compute_levels(s, "BUY", entry_px)
                        # ... broker.create_order jne ...
                    elif signal == -1:
                        log(f"[TRADE] {s} {tf}: SELL ({strat})")
                        entry_px = float(df["close"].iloc[-1])
                        levels = compute_levels(s, "SELL", entry_px)
                        # ... broker.create_order jne ...
                    else:
                        log(f"[HOLD] {s} {tf}: HOLD ({strat})")

            # --- PositionWatcher: TP/SL/Trail + Telegram + chart ---
            if position_watcher.should_check():
                position_watcher.check_and_manage_positions(SYMBOLS)

        except Exception as e:
            log(f"[ERROR] loop: {e}\n{traceback.format_exc()}")
        time.sleep(POLL)

if __name__ == "__main__":
    main()
