import pandas as pd

def add_classic_labels(df: pd.DataFrame, horizon: int = 8):
    df = df.copy()
    future = df["close"].shift(-horizon)
    df["label"] = (future > df["close"]).astype(int) - (future < df["close"]).astype(int)
    # label: 1=up, -1=down, 0=flat
    return df

def add_regression_labels(df: pd.DataFrame, horizon: int = 8):
    df = df.copy()
    future = df["close"].shift(-horizon)
    df["reg_label"] = (future - df["close"]) / df["close"]
    return df
