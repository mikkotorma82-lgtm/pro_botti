from __future__ import annotations
import numpy as np
import pandas as pd

def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    nunique = df.nunique()
    zero_var_cols = nunique[nunique <= 1].index.tolist()
    if zero_var_cols:
        df = df.drop(columns=zero_var_cols, errors="ignore")
    return df
