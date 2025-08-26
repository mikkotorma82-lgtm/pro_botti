import pandas as pd

DROP_TIME = ["time", "date", "datetime", "timestamp", "open_time", "close_time"]


def load_numeric_csv(path: str) -> pd.DataFrame:
    """Lataa CSV, pudottaa aikaleimakentät jos niitä on ja palauttaa numeeriset sarakkeet."""
    df = pd.read_csv(path)
    df.drop(
        columns=[c for c in DROP_TIME if c in df.columns], inplace=True, errors="ignore"
    )
    return df.select_dtypes(include="number")


if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Sisääntulo-CSV")
    ap.add_argument("--out", required=False, help="Kirjoita puhdistettu CSV tähän")
    args = ap.parse_args()

    df = load_numeric_csv(args.csv)
    if args.out:
        df.to_csv(args.out, index=False)
        print(f"Wrote {args.out} with shape {df.shape}")
    else:
        print(df.head().to_string())
        print(f"\nShape: {df.shape}", file=sys.stderr)
