import pandas as pd
import numpy as np

def mean_reversion_signal(df: pd.DataFrame, params: dict) -> int:
    """
    Mean reversion -strategia, tukee useita indikaattoreita ja parametrisoitu logiikka.
    Indikaattorit: Bollinger Bands, RSI, SMA, ATR, laajennettavissa!
    """
    if df is None or len(df) < 30 or "close" not in df:
        return 0

    px = df["close"].astype(float).values

    # Parametrit
    bb_window = params.get("bb_window", 20)
    bb_std = params.get("bb_std", 2)
    sma_window = params.get("sma_window", 20)
    rsi_window = params.get("rsi_window", 14)
    rsi_buy = params.get("rsi_buy", 35)
    rsi_sell = params.get("rsi_sell", 65)
    atr_window = params.get("atr_window", 14)
    atr_min = params.get("atr_min", 0.001)
    use_indicators = params.get("use_indicators", ["BOLLINGER", "RSI", "SMA", "ATR"])

    # Indikaattorit
    sma = pd.Series(px).rolling(sma_window).mean()
    std = pd.Series(px).rolling(bb_window).std(ddof=0)
    upper = sma + bb_std * std
    lower = sma - bb_std * std
    rsi = compute_rsi(px, window=rsi_window)
    atr = compute_atr(df, atr_window)

    signals = []

    # Bollinger Bands - mean reversion
    if "BOLLINGER" in use_indicators and px[-1] < lower.iloc[-1]:
        signals.append(1)
    elif "BOLLINGER" in use_indicators and px[-1] > upper.iloc[-1]:
        signals.append(-1)
    # RSI swing
    if "RSI" in use_indicators and rsi[-1] < rsi_buy:
        signals.append(1)
    elif "RSI" in use_indicators and rsi[-1] > rsi_sell:
        signals.append(-1)
    # SMA revert
    if "SMA" in use_indicators and px[-1] < sma.iloc[-1]:
        signals.append(1)
    elif "SMA" in use_indicators and px[-1] > sma.iloc[-1]:
        signals.append(-1)
    # ATR volatiliteettifiltteri
    if "ATR" in use_indicators and atr[-1] < atr_min:
        signals.append(0)

    # Yhdistä signaalit: majority vote, suodata nollat
    signals = [s for s in signals if s != 0]
    if not signals:
        return 0
    vote = np.sign(np.sum(signals))
    return int(vote)

def compute_rsi(prices, window=14):
    delta = np.diff(prices)
    up = delta.clip(min=0)
    down = -delta.clip(max=0)
    roll_up = pd.Series(up).rolling(window).mean()
    roll_down = pd.Series(down).rolling(window).mean()
    rs = roll_up / (roll_down + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    rsi = np.concatenate([[50]*(window-1), rsi])
    return rsi

def compute_atr(df: pd.DataFrame, window=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    tr = np.maximum.reduce([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ])
    atr = tr.rolling(window).mean().fillna(np.mean(tr[:window]))
    return atr.values
