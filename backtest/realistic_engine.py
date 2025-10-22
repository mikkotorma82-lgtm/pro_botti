# realistic_engine.py
import numpy as np, pandas as pd

def simulate_trades(df, spread=0.0002, latency=0.3):
    df["slippage"] = np.random.normal(0, spread, len(df))
    df["fill_prob"] = np.clip(1 - np.abs(df["slippage"])/spread, 0, 1)
    df["executed_return"] = df["signal"] * df["close"].pct_change() * df["fill_prob"]
    metrics = {"NetPnL": df["executed_return"].sum(),
               "WinRate": (df["executed_return"]>0).mean(),
               "Sharpe": df["executed_return"].mean()/df["executed_return"].std()}
    print("[BACKTEST]", metrics)
    return metrics
