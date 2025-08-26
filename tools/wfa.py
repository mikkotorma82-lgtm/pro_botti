import argparse, json
import pandas as pd
import numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    y = df["target"].values
    n = len(y)
    fold_size = n//args.folds

    results=[]
    for i in range(args.folds):
        train_idx = np.arange(0, fold_size*i)
        test_idx  = np.arange(fold_size*i, fold_size*(i+1))
        if len(test_idx)==0: continue
        results.append({"fold":i,"train":len(train_idx),"test":len(test_idx)})

    with open(args.out,"w") as f:
        json.dump({"folds":results},f,indent=2)
    print("WFA summary written",args.out)

if __name__=="__main__":
    main()
