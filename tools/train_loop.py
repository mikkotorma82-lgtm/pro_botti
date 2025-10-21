from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from tools.lr_safe import SafeLogistic as LogisticRegression

DROP_TIME = ["time", "date", "datetime", "timestamp", "open_time", "close_time"]


def load_numeric(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.drop(
        columns=[c for c in DROP_TIME if c in df.columns], inplace=True, errors="ignore"
    )
    return df.select_dtypes(include="number")


def split_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    # Etsi label-sarake tavallisilla nimillä
    for label in ("y", "target", "label", "signal"):
        if label in df.columns:
            y = df[label].to_numpy()
            X = df.drop(columns=[label])
            return X, y
    raise ValueError("Label-saraketta ei löytynyt (etsi: y/target/label/signal).")


def auc_auto(y: np.ndarray, proba: np.ndarray) -> float:
    classes = np.unique(y)
    if len(classes) == 2:
        # Binääri: proba toisen luokan sarake
        p1 = proba[:, 1] if proba.ndim == 2 and proba.shape[1] >= 2 else proba.ravel()
        return float(roc_auc_score(y, p1))
    # Multiluokka: ovr + weighted
    return float(roc_auc_score(y, proba, multi_class="ovr", average="weighted"))


def f1_auto(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    avg = "binary" if len(np.unique(y_true)) == 2 else "weighted"
    return float(f1_score(y_true, y_pred, average=avg))


def train_on_csv(csv_path: str, out_model: Path, cv: int = 3) -> Pipeline:
    df = load_numeric(csv_path)
    X, y = split_xy(df)

    pipe = Pipeline(
        [
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000, C=1.0, tol=1e-3, class_weight="balanced"
                ),
            ),
        ]
    )

    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)
    proba = cross_val_predict(pipe, X, y, cv=skf, method="predict_proba")
    # Ennusteet: binääri -> round p1, multiluokka -> argmax
    if len(np.unique(y)) == 2:
        p1 = proba[:, 1] if proba.shape[1] >= 2 else proba.ravel()
        y_pred = (p1 >= 0.5).astype(int)
    else:
        y_pred = proba.argmax(axis=1)

    metrics = {
        "acc": float(accuracy_score(y, y_pred)),
        "f1": f1_auto(y, y_pred),
        "auc": auc_auto(y, proba),
        "classes": int(len(np.unique(y))),
    }

    # Fit koko datalla ja tallenna vain malli-objekti (ei dictiä)
    pipe.fit(X, y)
    out_model.parent.mkdir(parents=True, exist_ok=True)
    dump(pipe, out_model)

    # Kirjoita myös metrit viereen
    stats_path = out_model.with_suffix(".json")
    stats_path.write_text(json.dumps(metrics, indent=2))
    print(f"Saved model -> {out_model}")
    print(f"CV metrics: {metrics}")
    return pipe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--cv", type=int, default=3)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(args.csv).stem
    out_model = out_dir / f"{base}_lr.joblib"
    train_on_csv(args.csv, out_model, cv=args.cv)


if __name__ == "__main__":
    main()
