import pandas as pd
import numpy as np

def add_features(df: pd.DataFrame):
    df = df.copy()
    df["log_return"] = np.log(df["close"] / df["close"].shift())
    df["ATR"] = (np.maximum(
        df["high"] - df["low"],
        np.abs(df["high"] - df["close"].shift()),
        np.abs(df["low"] - df["close"].shift())
    )).rolling(window=14).mean()
    df["EMA_20"] = df["close"].ewm(span=20).mean()
    df["RSI_14"] = compute_rsi(df["close"], 14)
    df["MACD"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    # Lisää muita featureja tarpeen mukaan
    return df

def compute_rsi(series, window):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))
