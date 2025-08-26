import argparse, json
import pandas as pd
import numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_csv", required=True)
    ap.add_argument("--preds_csv", required=True)
    ap.add_argument("--fee_bps", type=float, default=0)
    ap.add_argument("--metric", choices=["f1","sharpe","pnl"], default="f1")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = pd.read_csv(args.data_csv)
    preds = pd.read_csv(args.preds_csv)
    y = data["target"].values
    proba = preds["proba"].values

    best_thr, best_score = 0.5, -1e9
    for thr in np.linspace(0.05,0.95,91):
        sig = (proba >= thr).astype(int)
        pnl = (sig==y).mean() - args.fee_bps*1e-4  # simppeli
        f1 = 2*((sig & y).sum())/(sig.sum()+y.sum()) if (sig.sum()+y.sum())>0 else 0
        ret = (sig* (2*y-1))  # +1 long, -1 short idea
        sharpe = ret.mean()/ret.std() if ret.std()>0 else 0

        score = {"f1":f1,"sharpe":sharpe,"pnl":pnl}[args.metric]
        if score > best_score:
            best_score, best_thr = score, thr

    with open(args.out,"w") as f:
        json.dump({"best_thr":best_thr,"best_score":best_score},f)
    print("Best:",args.metric,best_score,"thr",best_thr)

if __name__=="__main__":
    main()
