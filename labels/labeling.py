
import pandas as pd
import numpy as np

def forward_return_labels(df: pd.DataFrame, horizon: int, threshold_bp: float) -> pd.Series:
    fwd = df["close"].pct_change(horizon).shift(-horizon)
    thr = threshold_bp/10000.0
    y = fwd.apply(lambda r: 1 if r>thr else (-1 if r<-thr else 0))
    return y

def barrier_labels(df: pd.DataFrame, tp_bp: float, sl_bp: float, max_horizon: int) -> pd.Series:
    tp = tp_bp/10000.0; sl = sl_bp/10000.0
    close = df["close"].values
    y = pd.Series(index=df.index, dtype="int8")
    for i in range(len(df)-max_horizon):
        entry = close[i]
        up = entry*(1+tp); dn = entry*(1-sl)
        label = 0
        for j in range(1, max_horizon+1):
            px = close[i+j]
            if px >= up: label = 1; break
            if px <= dn: label = -1; break
        y.iloc[i] = label
    return y

def make_labels(df: pd.DataFrame, cfg) -> pd.Series:
    if cfg.scheme == "forward_return":
        return forward_return_labels(df, cfg.forward_horizon, cfg.threshold_bp)
    elif cfg.scheme == "barrier":
        b = cfg.barrier
        return barrier_labels(df, b.get("tp_bp",50), b.get("sl_bp",50), b.get("max_horizon",48))
    else:
        raise ValueError(f"Unknown labels scheme: {cfg.scheme}")
