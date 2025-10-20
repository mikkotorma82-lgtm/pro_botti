import numpy as np
import pandas as pd
import joblib

# Esimerkki feature-yhdistelmistä per symboli+TF
BEST_FEATURES = {
    ("BTCUSD", "15m"): ["RSI", "MACD", "ADX"],
    ("BTCUSD", "4h"):  ["SMA50", "ATR", "Stochastic"],
    ("EURUSD", "1h"):  ["EMA12", "RSI", "Volume"],
    # Lisää tarvittaessa
}

def ml_signal(df: pd.DataFrame, params: dict) -> int:
    """
    ML-agentti, joka käyttää parasta 3–5 indikaattorin yhdistelmää per symboli+TF.
    Ennustaa signaalin ML-mallilla (esim. sklearn, xgboost).
    """
    symbol = params.get("symbol")
    tf = params.get("tf")
    model_path = params.get("model_path", "models/ml_model.joblib")
    features = build_features(df, symbol, tf)
    if features is None or len(features) == 0:
        return 0

    try:
        model = joblib.load(model_path)
        pred = model.predict([features])  # esim. [BUY, SELL, HOLD] = [1, -1, 0]
        return int(np.sign(pred[0]))
    except Exception:
        return 0

def build_features(df: pd.DataFrame, symbol: str, tf: str):
    """
    Laskee kaikki indikaattorit ja palauttaa vain koulutuksessa valitut.
    Laajennettavissa helposti!
    """
    if df is None or len(df) < 30 or "close" not in df:
        return None

    px = df["close"].astype(float).values
    vol = df.get("volume", pd.Series([0]*len(df))).astype(float).values
    high = df.get("high", pd.Series(px)).astype(float).values
    low = df.get("low", pd.Series(px)).astype(float).values

    # Kaikki indikaattorit
    ema12 = pd.Series(px).ewm(span=12).mean().iloc[-1]
    ema26 = pd.Series(px).ewm(span=26).mean().iloc[-1]
    sma50 = pd.Series(px).rolling(window=50).mean().iloc[-1]
    sma200 = pd.Series(px).rolling(window=200).mean().iloc[-1]
    macd = ema12 - ema26
    rsi = compute_rsi(px, window=14)[-1]
    adx = compute_adx(df, 14)[-1]
    atr = compute_atr(df, 14)[-1]
    stoch_k, _ = compute_stochastic(df, 14, 3)
    boll_up, boll_lo = compute_bollinger(px, 20, 2)
    cci = compute_cci(df, 20)[-1]
    willr = compute_williams_r(df, 14)[-1]
    last_vol = vol[-1]

    # Valitse koulutuksessa parhaaksi löydetyt featuret
    selected = BEST_FEATURES.get((symbol, tf), ["RSI", "MACD", "ATR"])
    all_feats = {
        "EMA12": ema12,
        "EMA26": ema26,
        "SMA50": sma50,
        "SMA200": sma200,
        "MACD": macd,
        "RSI": rsi,
        "ADX": adx,
        "ATR": atr,
        "Stochastic": stoch_k[-1],
        "BollingerUp": boll_up,
        "BollingerLow": boll_lo,
        "CCI": cci,
        "WilliamsR": willr,
        "Volume": last_vol,
    }
    # Palauta valitut featuret
    return [all_feats[name] for name in selected if name in all_feats]

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

def compute_bollinger(prices, window=20, std=2):
    sma = pd.Series(prices).rolling(window).mean().iloc[-1]
    sigma = pd.Series(prices).rolling(window).std(ddof=0).iloc[-1]
    upper = sma + std * sigma
    lower = sma - std * sigma
    return upper, lower

def compute_cci(df: pd.DataFrame, window=20):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(window).mean()
    mad = tp.rolling(window).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    cci = (tp - sma) / (0.015 * mad + 1e-12)
    cci = cci.fillna(0)
    return cci.values

def compute_williams_r(df: pd.DataFrame, window=14):
    high = df["high"].rolling(window).max()
    low = df["low"].rolling(window).min()
    willr = -100 * (high - df["close"]) / (high - low + 1e-12)
    willr = willr.fillna(0)
    return willr.values
