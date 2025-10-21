import os
import json
import time
import itertools
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Tuple
from joblib import dump
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
import openai

# Asetukset
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"; STATE.mkdir(parents=True, exist_ok=True)
MODEL_DIR = STATE / "models_ai"; MODEL_DIR.mkdir(exist_ok=True)
REG_PATH = STATE / "models_ai.json"

# Indikaattorit (voit säätää)
ALL_INDICS = ["sma", "ema", "rsi", "macd", "adx", "atr", "vola", "obv"]
INDIC_PARAMS = {
    "sma": {"sma_n": [10, 20, 50]},
    "ema": {"ema_n": [21, 50]},
    "rsi": {"rsi_n": [14], "rsi_low": [30.0], "rsi_high": [70.0]},
    "macd": {"macd_fast": [12], "macd_slow": [26], "macd_sig": [9]},
}
ML_MODELS = {
    "lr": lambda: LogisticRegression(max_iter=200, solver="lbfgs"),
    "gbdt": lambda: GradientBoostingClassifier(n_estimators=100),
    # Lisää xgboost/lightgbm jos haluat (muista pip install xgboost lightgbm)
}

# OpenAI API setup
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

def fetch_data(symbol, tf, limit=1000):
    # Placeholder – Tuo oikea datanhakufunktio (esim. capital_get_candles_df)
    # Palauttaa pd.DataFrame jossa sarakkeet: open, high, low, close, volume, time
    # Esimerkki: return capital_get_candles_df(symbol, tf, total_limit=limit)
    raise NotImplementedError("Toteuta datan haku")

def compute_features(df: pd.DataFrame, indic_combo: List[str], params: Dict[str, Any]) -> pd.DataFrame:
    feats = pd.DataFrame(index=df.index)
    if "sma" in indic_combo:
        n = params.get("sma_n", 20)
        feats["sma"] = df["close"].rolling(n).mean()
    if "ema" in indic_combo:
        n = params.get("ema_n", 21)
        feats["ema"] = df["close"].ewm(span=n).mean()
    if "rsi" in indic_combo:
        n = params.get("rsi_n", 14)
        delta = df["close"].diff()
        up = delta.clip(lower=0).rolling(n).mean()
        down = -delta.clip(upper=0).rolling(n).mean()
        rs = up / (down + 1e-12)
        feats["rsi"] = 100 - 100 / (1 + rs)
    if "macd" in indic_combo:
        fast = params.get("macd_fast", 12)
        slow = params.get("macd_slow", 26)
        sig = params.get("macd_sig", 9)
        ema_fast = df["close"].ewm(span=fast).mean()
        ema_slow = df["close"].ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=sig).mean()
        feats["macd"] = macd - signal
    # Lisää muut indikaattorit...
    return feats.dropna()

def generate_grid(indics: List[str]) -> List[Dict[str, Any]]:
    grids = []
    for combo in itertools.combinations(indics, r=3):
        param_sets = []
        for name in combo:
            param_sets.append(list(itertools.product(*INDIC_PARAMS.get(name, {}).values())))
        for params_combo in itertools.product(*param_sets):
            cfg = {"indicators": combo, "params": {}, "weights": {}, "threshold": 0.5}
            for i, name in enumerate(combo):
                keys = list(INDIC_PARAMS[name].keys())
                for k, v in zip(keys, params_combo[i]):
                    cfg["params"][k] = v
                cfg["weights"][name] = 1.0
            for thr in [0.3, 0.5, 0.7]:
                cfg_copy = dict(cfg)
                cfg_copy["threshold"] = thr
                grids.append(cfg_copy)
    return grids

def train_and_evaluate(X, y, model_factory):
    model = model_factory()
    model.fit(X, y)
    score = model.score(X, y)
    # Voit laskea lisää metriikoita
    return model, score

def openai_suggest(features, metrics, prev_models, symbol, tf):
    if not OPENAI_KEY:
        return None
    prompt = (
        f"Analysoi seuraavat featuret ja mallien metriikat symbolille {symbol} TF:lle {tf} ja ehdota optimaalinen uusi feature-yhdistelmä ja hyperparametrit. "
        f"Featuret: {features}\nMetriikat: {metrics}\nAiemmat mallit: {prev_models}\n"
        "Perustele ehdotuksesi lyhyesti."
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Toimit pörssibotin AI-optimointiapuna."},
                      {"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.7,
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print("OpenAI virhe:", e)
        return None

def main():
    symbols = os.getenv("SYMBOLS", "EURUSD,BTCUSD,ETHUSD").split(",")
    tfs = os.getenv("TRAIN_TFS", "1h,4h,15m").split(",")
    registry = []
    for sym in symbols:
        for tf in tfs:
            print(f"\n=== {sym} {tf} ===")
            try:
                df = fetch_data(sym, tf)
                if df is None or len(df) < 500:
                    print(f"[WARN] No data for {sym} {tf}")
                    continue
                best_score = -np.inf
                best_model = None
                best_cfg = None
                best_features = None
                # 1. Gridsearch omilla ML-malleilla
                for cfg in generate_grid(ALL_INDICS):
                    feats = compute_features(df, cfg["indicators"], cfg["params"])
                    # Simppeli label – voit käyttää parempaa
                    y = (df["close"].shift(-1).iloc[feats.index] > df["close"].iloc[feats.index]).astype(int)
                    for name, factory in ML_MODELS.items():
                        try:
                            model, score = train_and_evaluate(feats, y, factory)
                            if score > best_score:
                                best_score = score
                                best_model = model
                                best_cfg = dict(cfg)
                                best_features = feats.columns.tolist()
                        except Exception as ee:
                            continue
                # 2. Pyydä OpenAI:lta parannusehdotus ja testaa se
                suggestion = openai_suggest(best_features, {"score": best_score}, registry, sym, tf)
                print(f"[OpenAI suositus]: {suggestion}")
                # (Voit parsia suggestionin halutessasi ja ajaa uuden testin)
                # 3. Tallenna paras malli ja metadata
                reg_entry = {"symbol": sym, "tf": tf, "config": best_cfg, "features": best_features, "score": best_score, "ai_suggestion": suggestion, "trained_at": int(time.time())}
                registry.append(reg_entry)
                fname = f"{sym.replace('/', '').replace(' ', '')}__{tf}.joblib"
                dump(best_model, MODEL_DIR / fname)
                print(f"[OK] {sym} {tf}: Paras score={best_score:.4f}, features={best_features}")
            except Exception as e:
                print(f"[ERROR] {sym} {tf}: {e}")
    with open(REG_PATH, "w") as f:
        json.dump({"models": registry}, f, ensure_ascii=False, indent=2)
    print(f"[DONE] Kaikki mallit tallennettu {REG_PATH}")

if __name__ == "__main__":
    main()
