import pandas as pd

DROP_TIME = ["time", "date", "datetime", "timestamp", "open_time", "close_time"]


def fetch_local_csv(path: str) -> pd.DataFrame:
    """Yksinkertainen 'history fetch' paikallisesta CSV:stä (puhdistaa sarakkeet)."""
    df = pd.read_csv(path)
    df.drop(
        columns=[c for c in DROP_TIME if c in df.columns], inplace=True, errors="ignore"
    )
    return df


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="Polku CSV:hen")
    ap.add_argument("--out", required=False, help="Kirjoita puhdistettu CSV tähän")
    args = ap.parse_args()

    df = fetch_local_csv(args.path)
    if args.out:
        df.to_csv(args.out, index=False)
        print(f"Wrote {args.out} shape={df.shape}")
    else:
        print(df.head())
