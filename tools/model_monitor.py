#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot Model Monitor v7.0 Stage 1
Analysoi train_history.json, tunnistaa suorituskyvyn heikkenemisen ja tekee Smart Rotationin.
"""

import os, json, datetime, subprocess
import numpy as np
from telegram import Bot
import asyncio
from pathlib import Path
import telegram

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
STATE = BASE / "state"
HIST = DATA / "train_history.json"

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
