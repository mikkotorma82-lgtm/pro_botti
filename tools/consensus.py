import numpy as np
import pandas as pd

def calc_atr(df:pd.DataFrame, n:int=20):
    hi_lo = (df["high"]-df["low"]).abs()
    hi_pc = (df["high"]-df["close"].shift()).abs()
    lo_pc = (df["low"] -df["close"].shift()).abs()
    tr = pd.concat([hi_lo,hi_pc,lo_pc], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()

def regime_ok(df:pd.DataFrame, min_vol:float=0.002, trend_len:int=50):
    atr = calc_atr(df, n=20)
    vol = float((atr/df["close"]).iloc[-1])
    sma_fast = float(df["close"].rolling(20).mean().iloc[-1])
    sma_slow = float(df["close"].rolling(trend_len).mean().iloc[-1])
    trend_up = sma_fast > sma_slow
    return (vol >= min_vol), trend_up

def tf_consensus(p15:float,p1h:float,p4h:float, w=(1.0,1.5,2.0), on=0.5):
    score = (p15-0.5)*w[0] + (p1h-0.5)*w[1] + (p4h-0.5)*w[2]
    if score >= 0:
        return "BUY" if max(p15,p1h,p4h)>=on else "HOLD"
    else:
        return "SELL" if min(p15,p1h,p4h)<=1-on else "HOLD"
