
import pandas as pd

def to_period_seconds(tf: str) -> int:
    # pandas offset alias to seconds
    return int(pd.Timedelta(tf).total_seconds())
