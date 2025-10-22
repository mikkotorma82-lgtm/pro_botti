#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot Full AI Trainer v2
Kouluttaa XGBoost, RandomForest ja CNN-LSTM kaikille symboleille.
Valitsee parhaiten tuottavat mallit automaattisesti live-käyttöön.
"""

import os, json, datetime, time, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import r2_score
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
from telegram import Bot
import asyncio, joblib

# --- Paths ---
BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
MODELS = BASE / "models"
STATE = BASE / "state"
HIST = DATA / "train_history.json"
MODELS.mkdir(exist_ok=True, parents=True)
STATE.mkdir(exist_ok=True, parents=True)

SYMBOLS = [
    "BTCUSD","ETHUSD","XRPUSD","ADAUSD","SOLUSD",
    "US500","US100","DE40","JP225",
    "AAPL","NVDA","TSLA","AMZN","MSFT","META","GOOGL",
    "EURUSD","GBPUSD"
]
TIMEFRAMES = ["1h","4h"]

# --- Telegram setup ---
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN","")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID","")
bot = telegram.Bot(TG_TOKEN) if TG_TOKEN and TG_CHAT else None


TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN","")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID","")

async def _send(msg):
    try:
        bot = Bot(token=TG_TOKEN)
        await bot.send_message(chat_id=TG_CHAT, text=msg)
    except Exception as e:
        print(f"[tgsend error] {e}")

def tgsend(msg:str):
    if TG_TOKEN and TG_CHAT:
        asyncio.run(_send(msg))
