import joblib
import numpy as np
import pandas as pd

def ml_signal(df: pd.DataFrame, params: dict) -> int:
    # Lataa valmiiksi opetettu malli, esimerkiksi XGBoost/LightGBM/sklearn
    model_path = params.get("model_path", "models/ml_trader.joblib")
    try:
        model = joblib.load(model_path)
    except Exception:
        return 0

    # Oletetaan, että df sisältää tarvittavat featuret, esim. viimeiset 20 riviä
    features = build_features(df)
    if features is None:
        return 0

    # Ennusta signaali: 1 = BUY, -1 = SELL, 0 = HOLD
    pred = model.predict(features.reshape(1, -1))[0]
    # Jos malli antaa todennäköisyyksiä, thresholdaa
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(features.reshape(1, -1))[0]
        if proba[1] > 0.6:
            return 1
        elif proba[0] > 0.6:
            return -1
        else:
            return 0
    return int(np.sign(pred))

def build_features(df: pd.DataFrame) -> np.ndarray:
    # Syvä feature engineering, esim. hintojen muutos, volyymi, trendit jne.
    if len(df) < 20:
        return None
    px = df["close"].astype(float).values[-20:]
    returns = np.diff(px) / (px[:-1] + 1e-12)
    mean_ret = np.mean(returns)
    std_ret = np.std(returns)
    vol = df["volume"].astype(float).values[-20:]
    mean_vol = np.mean(vol)
    rsi = compute_rsi(px, window=14)[-1]
    # Voit lisätä lisää featureja
    return np.array([mean_ret, std_ret, mean_vol, rsi])

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
