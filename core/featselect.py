from __future__ import annotations
import numpy as np, pandas as pd

def drop_constant(df: pd.DataFrame, cols: list[str]) -> list[str]:
    keep = [c for c in cols if df[c].nunique(dropna=False) > 1]
    return keep

def drop_high_corr(df: pd.DataFrame, cols: list[str], thr: float=0.95) -> list[str]:
    if not cols: return cols
    corr = df[cols].corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    drop = {col for col in cols if any(upper[col] >= thr)}
    return [c for c in cols if c not in drop]

def top_k_by_mi(X: pd.DataFrame, y: pd.Series, cols: list[str], k: int=16) -> list[str]:
    try:
        from sklearn.feature_selection import mutual_info_classif
    except Exception:
        return cols
    mi = mutual_info_classif(X[cols].fillna(0.0), y, discrete_features=False, random_state=7)
    order = np.argsort(mi)[::-1]
    k = min(k, len(cols))
    return [cols[i] for i in order[:k]]

def auto_select(df: pd.DataFrame, y: pd.Series, base_cols: list[str], mi_k: int=16, corr_thr: float=0.95) -> list[str]:
    cols = drop_constant(df, base_cols)
    cols = drop_high_corr(df, cols, thr=corr_thr)
    cols = top_k_by_mi(df, y, cols, k=mi_k)
    return cols
