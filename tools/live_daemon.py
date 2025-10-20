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
from tools.data_sources import fetch_ohlcv

# Ammattilaistason symbolilista – kattaa kaikki markkinat
SYMBOLS_ALL = [
    "US500", "NAS100", "GER40", "UK100", "FRA40", "EU50", "JPN225",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY", "GBPJPY",
    "XAUUSD", "XAGUSD", "XTIUSD", "XBRUSD", "XNGUSD",
    "BTCUSD", "ETHUSD", "XRPUSD",
    "AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN"
]

def select_strategy(df, params):
    sigs = {
        "momentum": momentum_signal(df, params),
        "mean_rev": mean_reversion_signal(df, params),
        "ml": ml_signal(df, params),
        "stat_arb": stat_arb_signal(df, params),
    }
    best = max(sigs, key=lambda k: abs(sigs[k]))
    return sigs[best], best

def log(s: str):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    print(f"[{ts}] {s}", flush=True)

def main():
    # Käytä joko ympäristömuuttujaa (SYMBOLS), tiedostoa, tai fallbackina yllä olevaa listaa
    symbols_env = os.getenv("SYMBOLS")
    if symbols_env:
        SYMBOLS = symbols_env.split(",")
    else:
        SYMBOLS = SYMBOLS_ALL
    TFS = os.getenv("TFS", "15m,1h,4h").split(",")
    POLL = int(os.getenv("POLL_SECS","60"))

    broker = ... # Luo oikea broker-instanssi
    position_watcher = create_position_watcher(broker, check_interval=30)
    log(f"[INFO] Start: SYMBOLS={SYMBOLS} TFS={TFS} POLL={POLL}")

    while True:
        try:
            for s in SYMBOLS:
                for tf in TFS:
                    df = fetch_ohlcv(s, tf, lookback_days=365)
                    if df is None or df.empty: continue
                    params = {}
                    signal, strat = select_strategy(df, params)
                    entry_px = float(df["close"].iloc[-1])

                    if signal == 1:
                        log(f"[TRADE] {s} {tf}: BUY ({strat})")
                        levels = compute_levels(s, "BUY", entry_px)
                        chart = build_chart(df, s, tf, signal, entry_px)
                        send_telegram(f"BUY {s} {tf} @ {entry_px} strat={strat}")
                        send_telegram_photo(chart)
                    elif signal == -1:
                        log(f"[TRADE] {s} {tf}: SELL ({strat})")
                        levels = compute_levels(s, "SELL", entry_px)
                        chart = build_chart(df, s, tf, signal, entry_px)
                        send_telegram(f"SELL {s} {tf} @ {entry_px} strat={strat}")
                        send_telegram_photo(chart)
                    else:
                        log(f"[HOLD] {s} {tf}: HOLD ({strat})")

            if position_watcher.should_check():
                position_watcher.check_and_manage_positions(SYMBOLS)

        except Exception as e:
            log(f"[ERROR] loop: {e}\n{traceback.format_exc()}")
        time.sleep(POLL)

if __name__ == "__main__":
    main()
