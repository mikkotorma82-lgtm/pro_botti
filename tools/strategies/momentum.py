import pandas as pd
import numpy as np

def momentum_signal(df: pd.DataFrame, params: dict) -> int:
    # Oletetaan että df sisältää "close" hinnat, vähintään 50 datapistettä
    px = df["close"].astype(float).values
    ema12 = pd.Series(px).ewm(span=12).mean()
    ema26 = pd.Series(px).ewm(span=26).mean()
    macd = ema12 - ema26
    rsi = compute_rsi(px, window=14)

    # Signal logic: bullish if EMA12 > EMA26 and MACD > 0 and RSI > 55, bearish if reversed
    if ema12.iloc[-1] > ema26.iloc[-1] and macd.iloc[-1] > 0 and rsi[-1] > 55:
        return 1
    elif ema12.iloc[-1] < ema26.iloc[-1] and macd.iloc[-1] < 0 and rsi[-1] < 45:
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
