import argparse, os
from pathlib import Path
import joblib
from sklearn.dummy import DummyClassifier

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--tfs", nargs="+", required=True)
    args = ap.parse_args()

    Path("models").mkdir(parents=True, exist_ok=True)

    # Tyhjä "treeni": DummyClassifier vain että live ei kaadu
    X = [[0],[1]]
    y = [0,1]
    for sym in args.symbols:
        for tf in args.tfs:
            out = Path("models") / f"pro_{sym}_{tf}.joblib"
            m = DummyClassifier(strategy="most_frequent")
            m.fit(X,y)
            joblib.dump(m, out)
            print("Wrote", out)

if __name__ == "__main__":
    main()
