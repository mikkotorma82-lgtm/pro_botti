#!/usr/bin/env python3
"""
Ammattilaistason daemon, kaikki tärkeät ominaisuudet mukana:
- Laaja symbolilista (indeksit, forex, raaka-aineet, kryptot, osakkeet)
- Strategiat: momentum, mean reversion, ml_agent, stat_arb
- PositionWatcher: TP/SL/Trail ja riskit, valvoo kaikki positioita
- Telegram-raportointi ja chart snapshot
- Konfiguroitavuus ja laajennettavuus (portfolio, riskit, dashboard)
"""
from __future__ import annotations
import os, time, traceback
import pandas as pd
from typing import List
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
from loguru import logger

# Ammattilais-symbolilista
SYMBOLS_ALL = [
    "US500", "NAS100", "GER40", "UK100", "FRA40", "EU50", "JPN225",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY", "GBPJPY",
    "XAUUSD", "XAGUSD", "XTIUSD", "XBRUSD", "XNGUSD",
    "BTCUSD", "ETHUSD", "XRPUSD",
    "AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN"
]

def select_strategy(df: pd.DataFrame, params: dict) -> tuple[int, str]:
    sigs = {
        "momentum": momentum_signal(df, params),
        "mean_rev": mean_reversion_signal(df, params),
        "ml": ml_signal(df, params),
        "stat_arb": stat_arb_signal(df, params),
    }
    best = max(sigs, key=lambda k: abs(sigs[k]))
    return sigs[best], best

def log(s: str):
    logger.info(s)

def main():
    # Symbolit konfiguroitavissa, fallbackina kattava lista
    symbols_env = os.getenv("SYMBOLS")
    SYMBOLS: List[str] = symbols_env.split(",") if symbols_env else SYMBOLS_ALL
    TFS = os.getenv("TFS", "15m,1h,4h").split(",")
    POLL = int(os.getenv("POLL_SECS", "60"))
    GUARD_CONFIG = {"risk_model": "default", "telegram": True}

    broker = ... # Luo oikea broker-instanssi! (esim. CapitalClient, BinanceClient)
    position_watcher = create_position_watcher(broker, check_interval=30, guard_config=GUARD_CONFIG)
    log(f"[START] SYMBOLS={SYMBOLS} TFS={TFS} POLL={POLL}")

    while True:
        try:
            for s in SYMBOLS:
                for tf in TFS:
                    df = fetch_ohlcv(s, tf, lookback_days=365)
                    if df is None or df.empty:
                        log(f"[DATA] {s} {tf}: Ei dataa")
                        continue
                    params = {"symbol": s, "tf": tf}
                    signal, strat = select_strategy(df, params)
                    entry_px = float(df["close"].iloc[-1])

                    if signal == 1:
                        log(f"[TRADE] {s} {tf}: BUY ({strat}) @ {entry_px}")
                        levels = compute_levels(s, "BUY", entry_px)
                        # broker.create_order(symbol=s, side="BUY", qty=..., sl=levels["sl"], tp=levels["tp"])
                        chart = build_chart(df, s, tf, signal, entry_px)
                        send_telegram(f"BUY {s} {tf} @ {entry_px} strat={strat}")
                        send_telegram_photo(chart)
                    elif signal == -1:
                        log(f"[TRADE] {s} {tf}: SELL ({strat}) @ {entry_px}")
                        levels = compute_levels(s, "SELL", entry_px)
                        # broker.create_order(symbol=s, side="SELL", qty=..., sl=levels["sl"], tp=levels["tp"])
                        chart = build_chart(df, s, tf, signal, entry_px)
                        send_telegram(f"SELL {s} {tf} @ {entry_px} strat={strat}")
                        send_telegram_photo(chart)
                    else:
                        log(f"[HOLD] {s} {tf}: HOLD ({strat})")

            # PositionWatcher hoitaa kaikki positioiden TP/SL/Trail + telegram
            if position_watcher.should_check():
                results = position_watcher.check_and_manage_positions(SYMBOLS)
                log(f"[POSWATCH] {results}")

        except Exception as e:
            log(f"[ERROR] loop: {e}\n{traceback.format_exc()}")
        time.sleep(POLL)

if __name__ == "__main__":
    main()
