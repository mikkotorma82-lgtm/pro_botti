import pandas as pd
import numpy as np

def stat_arb_signal(df: pd.DataFrame, params: dict) -> int:
    # df: DataFrame jossa "spread" (esim. asset1 - beta*asset2), vähintään 200 datapistettä
    spread = df["spread"].astype(float).values
    lookback = params.get("z_lookback", 100)
    if len(spread) < lookback + 5:
        return 0
    mu = pd.Series(spread).rolling(lookback).mean()
    std = pd.Series(spread).rolling(lookback).std(ddof=0)
    z = (spread - mu) / (std + 1e-12)

    entry_z = params.get("entry_z", 2.0)
    exit_z = params.get("exit_z", 0.5)

    # Long spread (asset1 yliarvostettu) jos z < -entry_z, short spread jos z > entry_z
    if z[-1] < -entry_z:
        return 1
    elif z[-1] > entry_z:
        return -1
    # Sulje positio kun z normalisoituu
    elif abs(z[-1]) < exit_z:
        return 0
    else:
        return 0
