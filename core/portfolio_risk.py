#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot – Portfolio Risk (yhtenäinen)
- Lukee train_history.json
- Laskee corr-matriisin, portfolion volatiliteetin, Sharpen ja Sortinon
- Kirjoittaa data/risk_state.json
- Lähettää Telegram-yhteenvedon (valinnainen)
"""
import os, json, numpy as np, pandas as pd, datetime as dt, asyncio
from pathlib import Path

# env
try:
    from dotenv import load_dotenv
    load_dotenv("/root/pro_botti/secrets.env")
except Exception:
    pass

try:
    from telegram import Bot
except Exception:
    Bot = None

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
HIST = DATA / "train_history.json"
RISK = DATA / "risk_state.json"

TG_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","")
TG_CHAT=os.getenv("TELEGRAM_CHAT_ID","")

def tgsend(msg:str):
    if not (TG_TOKEN and TG_CHAT and Bot):
        return
    async def _send():
        try:
            bot = Bot(token=TG_TOKEN)
            await bot.send_message(chat_id=TG_CHAT, text=msg)
        except Exception as e:
            print("[tg error]", e)
    asyncio.run(_send())

def load_history()->pd.DataFrame:
    try:
        data=json.load(open(HIST))
        if isinstance(data,dict) and "entries" in data:
            data=data["entries"]
        df=pd.DataFrame(data)
        df=df.dropna(subset=["symbol","tf","sharpe"])
        return df
    except Exception as e:
        print("[risk] history read fail:", e)
        return pd.DataFrame()

def compute(df: pd.DataFrame)->dict:
    out={}
    try:
        # corr-matriisi symbolien viimeisistä Sharpe-arvoista aikajanan yli
        pv = df.pivot_table(values="sharpe",index="timestamp",columns="symbol",aggfunc="mean")
        corr = pv.corr().fillna(0)
        out["corr_matrix"] = corr.round(3).to_dict()

        # symbolikohtaiset perus-riskit (vol/VaR/ES) Sharpe-sarjasta (proxy)
        sym_list=[]
        for sym in df["symbol"].unique():
            s = df[df["symbol"]==sym]["sharpe"].tail(50).astype(float)
            if len(s) < 5: 
                continue
            vol = np.std(s)
            var = np.percentile(s, 5)
            es  = np.mean(s[s <= var]) if np.any(s <= var) else var
            sym_list.append({"symbol":sym,"vol":round(vol,3),"VaR95":round(var,3),"ES95":round(es,3)})
        out["symbols"] = sym_list

        all_s=df["sharpe"].tail(200).astype(float)
        port_vol = float(np.std(all_s)) if len(all_s)>1 else 0.0
        neg = all_s[all_s<0]
        sortino = float(np.mean(all_s)/max(np.std(neg),1e-9)) if len(neg)>1 else 0.0
        port_sharpe = float(np.mean(all_s)/max(port_vol,1e-9)) if port_vol>0 else 0.0

        out["portfolio"] = {
            "Sharpe": round(port_sharpe,3),
            "Sortino": round(sortino,3),
            "Volatility": round(port_vol,3),
            "Updated": dt.datetime.utcnow().isoformat()+"Z"
        }
    except Exception as e:
        print("[risk] compute fail:", e)
    return out

def main():
    df = load_history()
    if df.empty:
        print("[risk] no data")
        return
    res = compute(df)
    try:
        json.dump(res, open(RISK,"w"), indent=2)
    except Exception as e:
        print("[risk] save fail:", e)
    port = res.get("portfolio",{})
    msg = (f"📊 Portfolio Risk\n"
           f"Sharpe: {port.get('Sharpe','?')} | Sortino: {port.get('Sortino','?')}\n"
           f"Volatility: {port.get('Volatility','?')}\n"
           f"Updated: {port.get('Updated','')}")
    print(msg)
    tgsend(msg)

if __name__ == "__main__":
    main()
