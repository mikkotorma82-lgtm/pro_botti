#!/usr/bin/env python3
import os, time, requests, pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

# === Lataa ympäristömuuttujat ===
try:
    from dotenv import load_dotenv
    load_dotenv("/root/pro_botti/secrets.env", override=True)
except Exception:
    pass

CAPITAL_API_BASE = os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com")
CAPITAL_API_KEY  = os.getenv("CAPITAL_API_KEY")
CAPITAL_USERNAME = os.getenv("CAPITAL_USERNAME")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD")

if not all([CAPITAL_API_KEY, CAPITAL_USERNAME, CAPITAL_PASSWORD]):
    raise SystemExit("[FATAL] CAPITAL_* env puuttuu (/root/pro_botti/secrets.env)")

SESSION_HEADERS = {
    "X-CAP-API-KEY": CAPITAL_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

UNIVERSE = [
  "US500","NAS100","GER40","UK100","FRA40","EU50","JPN225",
  "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD",
  "EURJPY","GBPJPY","XAUUSD","XAGUSD","XTIUSD","XBRUSD","XNGUSD",
  "BTCUSD","ETHUSD","XRPUSD","AAPL","MSFT","NVDA","TSLA","META","AMZN"
]

# EPIC = symbol, mutta korjaa nimet jos Capital käyttää eri nimeä
EPIC_OVERRIDE = {

    "NAS100": "US100",

    "GER40": "DE40",

    "FRA40": "FR40",

    "JPN225": "JP225",

    "XAUUSD": "GOLD",

    "XAGUSD": "SILVER",

    "XTIUSD": "OIL WTI",

    "XBRUSD": "OIL BRENT",

    "XNGUSD": "NATURAL GAS"

}

