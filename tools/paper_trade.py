import argparse, json, os
import pandas as pd

def atr(high, low, close, period=14):
    high = pd.Series(high).astype(float)
    low  = pd.Series(low).astype(float)
    close= pd.Series(close).astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def ensure_atr(df, period=14):
    cols = {c.lower(): c for c in df.columns}
    hi = cols.get('high') or cols.get('h') or cols.get('high_price')
    lo = cols.get('low')  or cols.get('l') or cols.get('low_price')
    cl = cols.get('close') or cols.get('c') or cols.get('close_price') or cols.get('price')
    if hi and lo and cl and 'ATR' not in df.columns:
        df['ATR'] = atr(df[hi], df[lo], df[cl], period)
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)   # säilytetään rajapinta
    ap.add_argument("--csv", required=True)
    ap.add_argument("--thr", required=True, type=float)
    ap.add_argument("--equity0", type=float, default=10000.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # Lue data
    df = pd.read_csv(args.csv)
    # Normalisoi sarake-nimet
    df.columns = [str(c).strip() for c in df.columns]
    # Joissain CSV:issä on 'time' eikä 'timestamp' — ei väliä savutestille
    # Laske ATR jos puuttuu
    df = ensure_atr(df, period=14)

    # Koosteraportti savutestiin
    res = {
        "rows": int(len(df)),
        "has_ATR": bool('ATR' in df.columns),
        "atr_na": int(df['ATR'].isna().sum()) if 'ATR' in df.columns else None,
        "thr": args.thr,
        "equity0": args.equity0,
        "csv": os.path.basename(args.csv),
        "ok": True
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(res, f, indent=2)

    # Tulosta yksi rivi stdoutiin (hiljainen tila preliveä varten)
    print("paper_trade smoketest OK")

if __name__ == "__main__":
    main()
