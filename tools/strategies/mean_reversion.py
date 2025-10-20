import pandas as pd
import numpy as np

def mean_reversion_signal(df: pd.DataFrame, params: dict) -> int:
    # Oletetaan että df sisältää "close" hinnat, vähintään 30 datapistettä
    px = df["close"].astype(float).values
    # Bollinger Bands
    window = params.get("bb_window", 20)
    k = params.get("bb_std", 2)
    sma = pd.Series(px).rolling(window).mean()
    std = pd.Series(px).rolling(window).std(ddof=0)
    upper = sma + k*std
    lower = sma - k*std
    rsi = compute_rsi(px, window=14)

    # Mean reversion logiikka: ostetaan kun hinta < lower band ja RSI < 35, myydään kun hinta > upper band ja RSI > 65
    if px[-1] < lower.iloc[-1] and rsi[-1] < 35:
        return 1
    elif px[-1] > upper.iloc[-1] and rsi[-1] > 65:
        return -1
    else:
        return 0

def compute_rsi(prices, window=14):
    # Ammattitasoinen RSI
    delta = np.diff(prices)
    up = delta.clip(min=0)
    down = -delta.clip(max=0)
    roll_up = pd.Series(up).rolling(window).mean()
    roll_down = pd.Series(down).rolling(window).mean()
    rs = roll_up / (roll_down + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    rsi = np.concatenate([[50]*(window-1), rsi])
    return rsi
