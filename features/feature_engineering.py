
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.trend import SMAIndicator, EMAIndicator
from ta.volatility import BollingerBands
from ta.volatility import AverageTrueRange as ATR

def build_features(df: pd.DataFrame, cfg) -> pd.DataFrame:
    x = pd.DataFrame(index=df.index)
    for f in cfg.ta_features:
        name = f.get("name")
        if name == "rsi":
            w = int(f.get("window",14))
            x[f"rsi_{w}"] = RSIIndicator(df["close"], window=w).rsi()
        elif name == "stoch_k":
            w = int(f.get("window",14)); smooth_k = int(f.get("smooth_k",3))
            stk = StochasticOscillator(df["high"], df["low"], df["close"], window=w, smooth_window=smooth_k)
            x[f"stoch_k_{w}_{smooth_k}"] = stk.stoch()
        elif name == "willr":
            w = int(f.get("window",14))
            x[f"willr_{w}"] = WilliamsRIndicator(df["high"], df["low"], df["close"], lbp=w).williams_r()
        elif name == "sma":
            w = int(f.get("window",20))
            x[f"sma_{w}"] = SMAIndicator(df["close"], window=w).sma_indicator()
        elif name == "ema":
            w = int(f.get("window",50))
            x[f"ema_{w}"] = EMAIndicator(df["close"], window=w).ema_indicator()
        elif name == "bbands":
            w = int(f.get("window",20)); ndev = float(f.get("ndev",2.0))
            bb = BollingerBands(df["close"], window=w, window_dev=ndev)
            x[f"bb_mid_{w}"] = bb.bollinger_mavg()
            x[f"bb_up_{w}"]  = bb.bollinger_hband()
            x[f"bb_dn_{w}"]  = bb.bollinger_lband()
            x[f"bb_w_{w}"]   = (x[f"bb_up_{w}"] - x[f"bb_dn_{w}"]) / df["close"]
        elif name == "atr":
            w = int(f.get("window",14))
            atr = ATR(df["high"], df["low"], df["close"], window=w).average_true_range()
            x[f"atr_{w}"] = atr
        else:
            raise ValueError(f"Unknown feature name: {name}")
    # price relatives / returns
    x["ret_1"] = df["close"].pct_change()
    x["ret_5"] = df["close"].pct_change(5)
    x["vol_20"] = x["ret_1"].rolling(20).std() * (20 ** 0.5)
    return x.dropna()
