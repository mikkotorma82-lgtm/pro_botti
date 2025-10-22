#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot v7.0 – Portfolio Risk v2
Laskee portfoliotason korrelaatiot, volatiliteetin, VaR:n ja Expected Shortfallin.
"""

import os, json, datetime
import numpy as np, pandas as pd
from pathlib import Path
from telegram import Bot
import asyncio

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
HIST = DATA / "train_history.json"
RISK = DATA / "risk_state.json"

TG_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","")
TG_CHAT=os.getenv("TELEGRAM_CHAT_ID","")

async def _send(msg):
    try:
        bot=Bot(token=TG_TOKEN)
        await bot.send_message(chat_id=TG_CHAT,text=msg)
    except Exception as e:
        print(f"[tgsend error] {e}")
def tgsend(msg:str):
    if TG_TOKEN and TG_CHAT:
        asyncio.run(_send(msg))

def load_train_history():
    try:
        data=json.load(open(HIST))
        if isinstance(data,dict) and "entries" in data:
            data=data["entries"]
        df=pd.DataFrame(data)
        df=df.dropna(subset=["symbol","tf","sharpe"])
        return df
    except Exception as e:
        print("[risk] failed to read history:",e)
        return pd.DataFrame()

def compute_portfolio_risk(df:pd.DataFrame):
    """Laskee portfolion korrelaatiot, VaR ja ES."""
    out={}
    try:
        # Korrelaatiot Sharpe-matriisista
        pivot=df.pivot_table(values="sharpe",index="timestamp",columns="symbol",aggfunc="mean")
        corr=pivot.corr().fillna(0)
        out["corr_matrix"]=corr.round(3).to_dict()

        # Per-symbol volatility & VaR/ES (simuloitu)
        risk_list=[]
        for sym in df["symbol"].unique():
            sub=df[df["symbol"]==sym]["sharpe"].tail(50)
            if len(sub)<5: continue
            vals=sub.values
            vol=np.std(vals)
            var=np.percentile(vals,5)
            es=np.mean(vals[vals<=var])
            risk_list.append({"symbol":sym,"vol":round(vol,3),"VaR95":round(var,3),"ES95":round(es,3)})
        out["symbols"]=risk_list

        # Portfolio metrics
        all_sharpe=df["sharpe"].tail(200)
        port_vol=np.std(all_sharpe)
        port_sharpe=np.mean(all_sharpe)/max(1e-9,port_vol)
        sortino=np.mean(all_sharpe)/max(1e-9,np.std([x for x in all_sharpe if x<0]))
        out["portfolio"]={
            "Sharpe":round(port_sharpe,3),
            "Sortino":round(sortino,3),
            "Volatility":round(port_vol,3),
            "Updated":datetime.datetime.utcnow().isoformat()+"Z"
        }
    except Exception as e:
        print("[risk] error computing:",e)
    return out

def save_risk_state(data):
    try:
        json.dump(data,open(RISK,"w"),indent=2)
    except Exception as e:
        print("[risk] save failed:",e)

def main():
    df=load_train_history()
    if df.empty:
        print("[risk] no data")
        return
    res=compute_portfolio_risk(df)
    save_risk_state(res)
    port=res.get("portfolio",{})
    msg=(f"📊 *Portfolio Risk Summary*\n"
         f"Sharpe: {port.get('Sharpe','?')} | Sortino: {port.get('Sortino','?')}\n"
         f"Volatility: {port.get('Volatility','?')}\n"
         f"Updated: {port.get('Updated','')}")
    print(msg)
    tgsend(msg)

if __name__=="__main__":
    main()
