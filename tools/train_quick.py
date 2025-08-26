import argparse, os, joblib, numpy as np, pandas as pd
from sklearn.model_selection import StratifiedKFold, cross_val_score, cross_val_predict
from sklearn.metrics import roc_auc_score
from tools.lr_safe import SafeLogistic as LogisticRegression

DROP_TIME = ["time", "date", "datetime", "timestamp", "open_time", "close_time"]


def clean_xy(df, target="target"):
    df = df.copy()
    drop = [c for c in DROP_TIME if c in df.columns]
    if drop:
        df.drop(columns=drop, inplace=True)
    y = df[target].astype(int)
    X = df.drop(columns=[target]).select_dtypes(include="number")
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cv", type=int, default=3)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    X, y = clean_xy(df)

    skf = StratifiedKFold(n_splits=args.cv, shuffle=True, random_state=42)
    clf = LogisticRegression()

    # Acc/F1 suoraan
    acc = cross_val_score(clf, X, y, cv=skf, scoring="accuracy").mean()
    f1 = cross_val_score(clf, X, y, cv=skf, scoring="f1").mean()

    # AUC: päätetään proba cross_val_predictillä
    proba = cross_val_predict(clf, X, y, cv=skf, method="predict_proba")[:, 1]
    auc = roc_auc_score(y, proba)

    metrics = {"acc": float(acc), "f1": float(f1), "auc": float(auc)}
    print("CV metrics:", metrics)

    # Fitataan koko dataan ja talletetaan malli
    clf.fit(X, y)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    joblib.dump({"model": clf, "features": list(X.columns)}, args.out)
    print(f"Saved model -> {args.out}")


if __name__ == "__main__":
    main()
