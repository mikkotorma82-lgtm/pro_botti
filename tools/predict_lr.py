import argparse, joblib, pandas as pd, numpy as np

DROP_TIME = ["time", "date", "datetime", "timestamp", "open_time", "close_time"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thr", type=float, default=0.5)
    args = ap.parse_args()

    m = joblib.load("models/EURUSD_15m_lr.joblib")
    clf, feats = m["model"], m["features"]

    df = pd.read_csv(args.csv).copy()
    drop = [c for c in DROP_TIME if c in df.columns]
    if drop:
        df.drop(columns=drop, inplace=True)
    X = df.drop(columns=[c for c in ["target"] if c in df.columns]).select_dtypes(
        include="number"
    )
    X = X[feats]  # varmista sama featurejärjestys

    proba = clf.predict_proba(X)[:, 1]
    signal = (proba >= args.thr).astype(int)

    out = pd.DataFrame({"proba": proba, "signal": signal})
    out.to_csv(args.out, index=False)
    print(f"Wrote {args.out} with columns: proba, signal")


if __name__ == "__main__":
    main()
