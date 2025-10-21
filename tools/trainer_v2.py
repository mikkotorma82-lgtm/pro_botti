import argparse, json, yaml
from pathlib import Path
import numpy as np, pandas as pd
from joblib import dump
from sklearn.model_selection import StratifiedKFold, cross_val_score, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from tools.lr_safe import SafeLogistic as LogisticRegression
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import make_scorer, f1_score
from core.featselect import auto_select

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "history"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "data" / "reports_v2"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

BASE_FEATS = [
    "ret1",
    "ret5",
    "vol5",
    "ema12",
    "ema26",
    "macd",
    "rsi14",
    "atr14",
    "ema_gap",
]


def load_cfg(p: Path) -> dict:
    with open(p, "r") as f:
        return yaml.safe_load(f)


def load_xy(symbol: str, tf: str, feats: list[str]):
    p = DATA_DIR / symbol / f"{symbol}_{tf}.parquet"
    df = pd.read_parquet(p)
    # label: sign(next_ret) -> {-1,0,1}
    y = df["label"].astype(int)
    X = df[feats].astype(float)
    return df, X, y


def build_candidates():
    lr = Pipeline(
        [
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            (
                "clf",
                LogisticRegression(
                    class_weight="balanced", C=1.0, max_iter=1000, n_jobs=1
                ),
            ),
        ]
    )
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        n_jobs=1,
        random_state=7,
    )
    # Voting (soft) – antaa usein parhaan IS/OOS‑tasapainon
    vote = VotingClassifier(
        estimators=[("lr", lr), ("rf", rf)], voting="soft", n_jobs=None
    )
    return {
        "lr": lr,
        "rf": rf,
        "vote": vote,
    }


def search_best(X, y, cv_splits=5):
    cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=7)
    scoring = make_scorer(f1_score, average="macro")
    cands = build_candidates()

    # Kevyt grid LR:lle ja RF:lle
    grids = [
        ("lr", cands["lr"], {"clf__C": [0.1, 0.5, 1.0, 2.0]}),
        (
            "rf",
            cands["rf"],
            {"n_estimators": [200, 300, 500], "max_features": [None, "sqrt", 0.5]},
        ),
        (
            "vote",
            cands["vote"],
            {
                "lr__clf__C": [0.5, 1.0, 2.0],
                "rf__n_estimators": [200, 300],
                "rf__max_features": [None, "sqrt"],
            },
        ),
    ]

    best_name, best_est, best_score = None, None, -9e9
    for name, est, grid in grids:
        gs = GridSearchCV(est, grid, scoring=scoring, cv=cv, n_jobs=1, verbose=0)
        gs.fit(X, y)
        score = gs.best_score_
        if score > best_score:
            best_name, best_est, best_score = name, gs.best_estimator_, score
    return best_name, best_est, float(best_score)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = load_cfg(Path(args.config))

    symbols = cfg.get("data", {}).get("symbols", [])
    tfs = cfg.get("data", {}).get("tfs", ["1h"])

    reports = []
    for s in symbols:
        for tf in tfs:
            try:
                # 1) lataa kaikki perusfeaturet
                df_all, X_all, y_all = load_xy(s, tf, BASE_FEATS)

                # 2) automaattinen feature‑valinta
                feats = auto_select(df_all, y_all, BASE_FEATS, mi_k=16, corr_thr=0.95)
                X = df_all[feats].astype(float)

                # 3) valitse automaattisesti paras malli + hyperparametrit
                name, best_est, score = search_best(X, y_all, cv_splits=5)

                # 4) fit koko dataan ja tallenna
                best_est.fit(X, y_all)
                job = MODEL_DIR / f"pro_{s}_{tf}.joblib"
                meta = MODEL_DIR / f"pro_{s}_{tf}.json"
                dump(best_est, job)
                with open(meta, "w") as f:
                    json.dump(
                        {
                            "symbol": s,
                            "tf": tf,
                            "feats": feats,
                            "model": name,
                            "cv_f1_macro": score,
                        },
                        f,
                        indent=2,
                    )
                rep = REPORT_DIR / f"train_v2_{s}_{tf}.json"
                with open(rep, "w") as f:
                    json.dump(
                        {
                            "symbol": s,
                            "tf": tf,
                            "feats": feats,
                            "best_model": name,
                            "cv_f1_macro": score,
                        },
                        f,
                        indent=2,
                    )

                print(f"[OK v2] saved pro_{s}_{tf}.joblib + pro_{s}_{tf}.json")
                print(f"[REP v2] {rep}")
            except Exception as e:
                print(f"[FAIL v2] {s} {tf}: {e}")


if __name__ == "__main__":
    main()
