#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot – Full AI Trainer v3 (Capital.com only)
Kouluttaa mallit kaikille symboleille ja aikaväleille feature-tiedostoista.
"""
import os, json, time, joblib
import pandas as pd, numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split
from telegram import Bot
import asyncio

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
FEATURES = DATA / "features"
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True, parents=True)
HIST = DATA / "train_history.json"

TG_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","")
TG_CHAT=os.getenv("TELEGRAM_CHAT_ID","")

async def _send(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            bot=Bot(token=TG_TOKEN)
            await bot.send_message(chat_id=TG_CHAT, text=msg)
        except Exception as e:
            print("[tg error]", e)
def tgsend(m): asyncio.run(_send(m))

SYMBOLS = [
    "BTCUSD","ETHUSD","XRPUSD","ADAUSD","SOLUSD",
    "US500","US100","DE40","JP225",
    "AAPL","NVDA","TSLA","AMZN","MSFT","META","GOOGL",
    "EURUSD","GBPUSD"
]
TFS = ["1h","4h"]

def train_symbol_tf(symbol, tf):
    path = FEATURES / f"{symbol}_{tf}.csv"
    if not path.exists():
        print(f"[skip] {path} missing")
        return None
    df=pd.read_csv(path)
    if len(df)<500:
        print(f"[skip] {symbol}_{tf} too small")
        return None

    # Features
    feats=[c for c in df.columns if c not in ["time","return","open","high","low","close","volume"]]
    X=df[feats].fillna(0)
    y=df["return"].shift(-1).fillna(0)
    X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=0.2,shuffle=False)

    model=XGBRegressor(n_estimators=300,learning_rate=0.05,max_depth=6,n_jobs=-1)
    model.fit(X_train,y_train)
    y_pred=model.predict(X_test)
    r2=r2_score(y_test,y_pred)
    pnl=np.sign(y_pred)*y_test
    sharpe=np.mean(pnl)/max(np.std(pnl),1e-9)

    model_path = MODELS/f"{symbol}_{tf}_xgb.pkl"
    joblib.dump(model, model_path)
    print(f"[ok] {symbol}_{tf} -> Sharpe={sharpe:.3f} R2={r2:.3f}")

    return {
        "symbol":symbol,
        "tf":tf,
        "sharpe":round(sharpe,3),
        "r2":round(r2,3),
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S")
    }

def append_hist(entry):
    try:
        h=[]
        if HIST.exists():
            h=json.load(open(HIST))
        h.append(entry)
        json.dump(h,open(HIST,"w"),indent=2)
    except Exception as e:
        print("[hist save error]",e)

def main():
    tgsend("🚀 Training started (v3)")
    results=[]
    for s in SYMBOLS:
        for tf in TFS:
            e=train_symbol_tf(s,tf)
            if e:
                append_hist(e)
                results.append(e)
                tgsend(f"{s}_{tf} Sharpe={e['sharpe']:.2f} R2={e['r2']:.2f}")
    tgsend("✅ All training complete.")
    print("[done] training finished")
if __name__=="__main__":
    main()
