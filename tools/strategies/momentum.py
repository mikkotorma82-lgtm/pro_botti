import pandas as pd
import numpy as np

def momentum_signal(df: pd.DataFrame, params: dict) -> int:
    """
    Ammattilaistason momentum-strategia, tukee 3-5 indikaattorin yhdistelmää per symboli+TF.
    Indikaattorit: EMA12/26, MACD, RSI, SMA50/200, Stochastic, ADX, ATR, Volume
    Kaikki logiikka on parametrisoitavissa ja laajennettavissa!
    """
    if df is None or len(df) < 60 or "close" not in df or "volume" not in df:
        return 0

    px = df["close"].astype(float).values
    vol = df["volume"].astype(float).values

    # Indikaattorin parametrit
    ema_fast = params.get("ema_fast", 12)
    ema_slow = params.get("ema_slow", 26)
    sma_short = params.get("sma_short", 50)
    sma_long = params.get("sma_long", 200)
    rsi_window = params.get("rsi_window", 14)
    stochastic_k = params.get("stoch_k", 14)
    stochastic_d = params.get("stoch_d", 3)
    adx_window = params.get("adx_window", 14)
    atr_window = params.get("atr_window", 14)
    vol_thresh = params.get("vol_thresh", 0.5)

    # Indikaattorit
    ema12 = pd.Series(px).ewm(span=ema_fast).mean()
    ema26 = pd.Series(px).ewm(span=ema_slow).mean()
    macd = ema12 - ema26
    sma50 = pd.Series(px).rolling(window=sma_short).mean()
    sma200 = pd.Series(px).rolling(window=sma_long).mean()
    rsi = compute_rsi(px, window=rsi_window)
    stoch_k, stoch_d = compute_stochastic(df, k_window=stochastic_k, d_window=stochastic_d)
    adx = compute_adx(df, adx_window)
    atr = compute_atr(df, atr_window)
    last_vol = vol[-1]
    mean_vol = np.mean(vol[-20:])
    vol_ok = last_vol > vol_thresh * mean_vol

    # Valitse käytettävät indikaattorit (params tai BEST_FEATURES)
    use_indicators = params.get("use_indicators", ["EMA", "MACD", "RSI", "ADX", "STOCHASTIC"])
    signals = []

    # EMA/MACD trend
    if "EMA" in use_indicators and ema12.iloc[-1] > ema26.iloc[-1]:
        signals.append(1)
    elif "EMA" in use_indicators and ema12.iloc[-1] < ema26.iloc[-1]:
        signals.append(-1)
    if "MACD" in use_indicators and macd.iloc[-1] > 0:
        signals.append(1)
    elif "MACD" in use_indicators and macd.iloc[-1] < 0:
        signals.append(-1)
    # RSI swing
    if "RSI" in use_indicators and rsi[-1] > 60:
        signals.append(1)
    elif "RSI" in use_indicators and rsi[-1] < 40:
        signals.append(-1)
    # ADX trend strength
    if "ADX" in use_indicators and adx[-1] < 20:
        signals.append(0)
    # Stochastic käänne
    if "STOCHASTIC" in use_indicators and stoch_k[-1] < 20 and stoch_d[-1] < 20:
        signals.append(1)
    elif "STOCHASTIC" in use_indicators and stoch_k[-1] > 80 and stoch_d[-1] > 80:
        signals.append(-1)
    # SMA trend filter
    if "SMA" in use_indicators and px[-1] > sma200.iloc[-1]:
        signals.append(1)
    elif "SMA" in use_indicators and px[-1] < sma200.iloc[-1]:
        signals.append(-1)
    # ATR ja volyymi filtteröinti
    if "ATR" in use_indicators and atr[-1] < 0.5 * np.mean(atr[-20:]):
        signals.append(0)
    if "VOLUME" in use_indicators and not vol_ok:
        signals.append(0)

    # Yhdistä signaalit: majority vote, mutta 0:t suodatetaan pois
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

def compute_stochastic(df: pd.DataFrame, k_window=14, d_window=3):
    low_min = df["low"].rolling(window=k_window).min()
    high_max = df["high"].rolling(window=k_window).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min + 1e-12)
    d = k.rolling(window=d_window).mean()
    k = k.fillna(50)
    d = d.fillna(50)
    return k.values, d.values

def compute_adx(df: pd.DataFrame, window=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    tr = np.maximum.reduce([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ])
    plus_di = 100 * plus_dm.rolling(window).mean() / (tr.rolling(window).mean() + 1e-12)
    minus_di = 100 * minus_dm.rolling(window).mean() / (tr.rolling(window).mean() + 1e-12)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-12)
    adx = dx.rolling(window).mean().fillna(20)
    return adx.values

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
