from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import load

DROP_TIME = ["time", "date", "datetime", "timestamp", "open_time", "close_time"]


def load_numeric(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.drop(
        columns=[c for c in DROP_TIME if c in df.columns], inplace=True, errors="ignore"
    )
    return df.select_dtypes(include="number")


def main():
    ap = argparse.ArgumentParser(description="Offline inference SafeLogistic-mallilla")
    ap.add_argument("--model", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--thr", type=float, default=0.5, help="Kynnys binäärille (p(class1) >= thr)"
    )
    args = ap.parse_args()

    obj = load(args.model)
    # Jos joku on joskus tallentanut dictin, poimi 'model'-avain
    if isinstance(obj, dict):
        obj = obj.get("model", obj)
    pipe = obj

    df = load_numeric(args.csv)
    # Jos datassa on label-sarake, älä käytä sitä piirteenä
    for label in ("y", "target", "label", "signal"):
        if label in df.columns:
            df = df.drop(columns=[label])

    X = df
    proba = pipe.predict_proba(X)

    # Rakenna tulos: binääri -> proba1 ja signal; multiluokka -> proba_k sarakkeet + argmax
    if proba.ndim == 2 and proba.shape[1] == 2:
        proba1 = proba[:, 1]
        signal = (proba1 >= args.thr).astype(int)
        out = pd.DataFrame({"proba": proba1, "signal": signal})
    else:
        # Multiluokka
        k = proba.shape[1] if proba.ndim == 2 else 1
        cols = {f"proba_{i}": proba[:, i] for i in range(k)}
        preds = (
            proba.argmax(axis=1) if proba.ndim == 2 else (proba > args.thr).astype(int)
        )
        out = pd.DataFrame(cols)
        out["pred"] = preds

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"Wrote {args.out} with columns: {', '.join(out.columns)}")


if __name__ == "__main__":
    main()
