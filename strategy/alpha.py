
import pandas as pd
import numpy as np

def signals_from_proba(proba: pd.Series, up_th: float=0.55, dn_th: float=0.45) -> pd.Series:
    # long if p>up_th, short if p<dn_th, else flat
    sig = proba.copy()*0
    sig[proba>up_th] = 1
    sig[proba<dn_th] = -1
    sig[(proba<=up_th)&(proba>=dn_th)] = 0
    return sig.astype("int8")
