#!/usr/bin/env python3
from __future__ import annotations
import os
from typing import Literal
import numpy as np
import pandas as pd

def _heuristic_pattern(df: pd.DataFrame, action: Literal["BUY","SELL"]) -> float:
    # Erittäin kevyt heuristiikka: bullish/bearish engulfing, RSI, lähipivot
    d = df.iloc[-5:].copy()
    close = d["close"]; open_ = d.get("open", close.shift(1).fillna(close))
    rsi = (close.pct_change().rolling(14, min_periods=5).apply(lambda x: (x[x>0].mean() / (abs(x[x<0]).mean()+1e-9)), raw=False)).iloc[-1]
    rsi = float(np.clip(50 + 10*(rsi-1), 0, 100)) if np.isfinite(rsi) else 50.0
    c1, o1 = close.iloc[-1], open_.iloc[-1]; c2, o2 = close.iloc[-2], open_.iloc[-2]
    engulf_bull = (c1>o1) and (o1<=c2) and (c1>=o2)
    engulf_bear = (c1<o1) and (o1>=c2) and (c1<=o2)
    score = 0.5
    if action=="BUY":
        if engulf_bull: score += 0.2
        score += 0.003*(rsi-50)
    else:
        if engulf_bear: score += 0.2
        score += 0.003*(50-rsi)
    return float(np.clip(score, 0.0, 1.0))

def pattern_score(df: pd.DataFrame, action: Literal["BUY","SELL"]) -> float:
    if os.getenv("OPENAI_PATTERN_ENABLED","0") != "1":
        return _heuristic_pattern(df, action)
    # OpenAI-kutsu valinnainen (vaatii OPENAI_API_KEY). Palataan heuristiikkaan fallbackissa.
    try:
        import openai
        key = os.getenv("OPENAI_API_KEY")
        if not key: 
            return _heuristic_pattern(df, action)
        client = openai.OpenAI(api_key=key)
        d = df.iloc[-40:][["open","high","low","close"]]
        prompt = f"""You are a trading pattern expert. Given last 40 OHLC bars and desired action '{action}', 
score the confidence (0..1) that taking the action now is favorable within next few bars. 
Return ONLY a float between 0 and 1.

OHLC (most recent last):
{d.to_string(index=False)}
"""
        resp = client.chat.completions.create(model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
                                              messages=[{"role":"user","content":prompt}],
                                              temperature=0.0, max_tokens=10)
        txt = resp.choices[0].message.content.strip()
        val = float(txt.split()[0])
        return float(np.clip(val, 0.0, 1.0))
    except Exception:
        return _heuristic_pattern(df, action)
