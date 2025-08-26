
import pandas as pd
import numpy as np
from utils.misc import bp_to_float

def run_backtest(df: pd.DataFrame, signals: pd.Series, fees_bp: float=1.0, slippage_bp: float=1.0):
    df = df.loc[signals.index]
    px = df["close"]
    # naive execution at next bar close with fees+slippage
    ret = px.pct_change().fillna(0)
    fees = bp_to_float(fees_bp + slippage_bp)
    strat_ret = (signals.shift().fillna(0) * ret) - fees*abs(signals.diff().fillna(0))
    equity = (1 + strat_ret).cumprod()
    return pd.DataFrame({"ret": strat_ret, "equity": equity})
