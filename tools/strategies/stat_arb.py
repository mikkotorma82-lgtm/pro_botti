import numpy as np
import pandas as pd

def stat_arb_signal(df1: pd.DataFrame, df2: pd.DataFrame, params: dict) -> int:
    """
    Statistinen arbitraasi-strategia kahdelle symbolille.
    Indikaattorit: z-score (spread), rolling mean/std, ATR, SMA.
    Palauttaa signaalin: 1 (long spread), -1 (short spread), 0 (ei treidiä)
    """
    if df1 is None or df2 is None or len(df1) < 60 or len(df2) < 60:
        return 0

    px1 = df1["close"].astype(float).values
    px2 = df2["close"].astype(float).values

    window = params.get("window", 30)
    z_entry = params.get("z_entry", 2.0)
    z_exit = params.get("z_exit", 0.5)
    use_indicators = params.get("use_indicators", ["Z", "SMA", "ATR"])

    # Spread ja sen normalisointi (z-score)
    spread = px1 - px2
    mean = pd.Series(spread).rolling(window).mean()
    std = pd.Series(spread).rolling(window).std(ddof=0)
    zscore = (spread - mean) / (std + 1e-12)

    # SMA/ATR indikaattorit
    sma1 = pd.Series(px1).rolling(window).mean()
    sma2 = pd.Series(px2).rolling(window).mean()
    atr1 = compute_atr(df1, 14)[-1]
    atr2 = compute_atr(df2, 14)[-1]

    signals = []

    # Z-score spread mean reversion
    if "Z" in use_indicators and zscore[-1] > z_entry:
        signals.append(-1)  # short spread: myy px1, osta px2
    elif "Z" in use_indicators and zscore[-1] < -z_entry:
        signals.append(1)   # long spread: osta px1, myy px2
    elif abs(zscore[-1]) < z_exit:
        signals.append(0)   # ei treidiä, spread "normalisoitunut"

    # SMA trend filter
    if "SMA" in use_indicators and px1[-1] < sma1.iloc[-1] and px2[-1] > sma2.iloc[-1]:
        signals.append(-1)
    elif "SMA" in use_indicators and px1[-1] > sma1.iloc[-1] and px2[-1] < sma2.iloc[-1]:
        signals.append(1)

    # ATR volatiliteettifiltteri
    if "ATR" in use_indicators and (atr1 < 0.001 or atr2 < 0.001):
        signals.append(0)

    # Yhdistetään signaalit majority-votella, suodatetaan nollat
    signals = [s for s in signals if s != 0]
    if not signals:
        return 0
    vote = np.sign(np.sum(signals))
    return int(vote)

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
