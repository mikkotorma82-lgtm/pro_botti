#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot – Historical Data Fetcher (Capital.com only, full pagination)
Hakee historian Capital.com API:sta 200 datapisteen erissä, jatkaa taaksepäin kunnes aikaraja saavutetaan.
Tallentaa tiedostot kansioon /root/pro_botti/data/history/
"""

import os
import time
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from capital_api import CapitalClient

# -------------------------------------------------------------------
# Ladataan API-avaimet secrets.env -tiedostosta
# -------------------------------------------------------------------
load_dotenv("/root/pro_botti/secrets.env")

# -------------------------------------------------------------------
# Polut ja asetukset
# -------------------------------------------------------------------
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "history"
OUT.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "BTCUSD","ETHUSD","XRPUSD","ADAUSD","SOLUSD",
    "US500","US100","DE40","JP225",
    "AAPL","NVDA","TSLA","AMZN","MSFT","META","GOOGL",
    "EURUSD","GBPUSD"
]

TIMEFRAMES = ["15m","1h","4h"]

# Kuinka pitkältä ajalta haetaan
DAYS_BACK = {"15m": 730, "1h": 1460, "4h": 3650}
SEC_PER = {"15m":900, "1h":3600, "4h":14400}


# -------------------------------------------------------------------
# Apufunktiot
# -------------------------------------------------------------------
def ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Varmistaa, että sarakenimet ovat oikein ja vain olennaiset mukana"""
    df.columns = [c.lower() for c in df.columns]
    required = ["time","open","high","low","close","volume"]
    return df[required]


def fetch_symbol_tf(client: CapitalClient, symbol: str, tf: str):
    """Hakee annetulle symbolille ja timeframe:lle historian useassa erässä"""
    limit = 200
    seconds = SEC_PER[tf]
    end_ts = int(time.time())
    cutoff = end_ts - DAYS_BACK[tf]*24*3600
    all_chunks = []
    request_count = 0

    while True:
        request_count += 1
        try:
            data = client.request(
                "GET", "/pricehistory",
                params={"symbol": symbol, "timeframe": tf, "max": limit, "end": end_ts}
            )
        except Exception as e:
            print(f"[{symbol}_{tf}] API request error: {e}")
            break

        if not data:
            break

        df = pd.DataFrame(data)
        if df.empty:
            break

        df = ensure_cols(df)

        # epoch -> sekunnit jos tarvitaan
        if df["time"].max() > 1e12:
            df["time"] = (df["time"] // 1000).astype(int)

        df["time_iso"] = pd.to_datetime(df["time"], unit="s")
        all_chunks.append(df)

        oldest = int(df["time"].min())
        if oldest <= cutoff or len(df) < limit:
            break

        end_ts = oldest - 1
        time.sleep(0.15)

    if not all_chunks:
        print(f"[skip] {symbol}_{tf} no data")
        return

    hist = pd.concat(all_chunks).drop_duplicates(subset=["time"]).sort_values("time")
    hist.rename(columns={"time_iso":"time"}, inplace=True)

    out_path = OUT / f"{symbol}_{tf}.csv"
    hist.to_csv(out_path, index=False)
    print(f"[ok] {symbol}_{tf} -> {out_path} ({len(hist)} rows, {request_count} requests)")


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main():
    client = CapitalClient()
    if not client.login():
        print("[login] failed")
        return

    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                fetch_symbol_tf(client, sym, tf)
            except Exception as e:
                print(f"[fail] {sym}_{tf}: {e}")

    print("[done] full history fetch complete")


# -------------------------------------------------------------------
# Käynnistys
# -------------------------------------------------------------------
if __name__ == "__main__":
    main()
