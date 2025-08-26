from __future__ import annotations
import numpy as np, pandas as pd


def ema(s: pd.Series, n: int):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14):
    delta = close.diff()
    up = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    roll_up = up.ewm(alpha=1 / n, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-12)
    return 100 - (100 / (1 + rs))


def stoch(high, low, close, k=14, d=3):
    lowest = low.rolling(k).min()
    highest = high.rolling(k).max()
    kf = 100 * (close - lowest) / (highest - lowest + 1e-12)
    df = kf.rolling(d).mean()
    return kf, df


def macd(close, fast=12, slow=26, signal=9):
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    m = fast_ema - slow_ema
    s = ema(m, signal)
    hist = m - s
    return m, s, hist


def bb(close, n=20, k=2.0):
    ma = close.rolling(n).mean()
    sd = close.rolling(n).std()
    upper = ma + k * sd
    lower = ma - k * sd
    return ma, upper, lower


def atr(high, low, close, n=14):
    prev_close = close.shift(1)
    tr = np.maximum(
        high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs())
    )
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(high, low, close, n=14):
    up = high.diff()
    dn = low.diff() * -1
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = atr(high, low, close, n)
    plus_di = (
        100
        * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean()
        / tr
    )
    minus_di = (
        100
        * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean()
        / tr
    )
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-12)
    adx = dx.ewm(alpha=1 / n, adjust=False).mean()
    return adx, plus_di, minus_di


def obv(close, volume):
    return (np.sign(close.diff().fillna(0)) * volume).fillna(0).cumsum()


def ichimoku(high, low, close):
    conv = (high.rolling(9).max() + low.rolling(9).min()) / 2
    base = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((conv + base) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    lag = close.shift(-26)
    return conv, base, span_a, span_b, lag


def supertrend(high, low, close, n=10, mult=3.0):
    atrv = atr(high, low, close, n)
    hl2 = (high + low) / 2.0
    upper = hl2 + mult * atrv
    lower = hl2 - mult * atrv
    dir = np.ones(len(close))
    st = pd.Series(index=close.index, dtype=float)
    for i in range(len(close)):
        if i == 0:
            st.iloc[i] = upper.iloc[i]
            dir[i] = 1
        else:
            if close.iloc[i] > upper.iloc[i - 1]:
                dir[i] = 1
            elif close.iloc[i] < lower.iloc[i - 1]:
                dir[i] = -1
            else:
                dir[i] = dir[i - 1]
            if dir[i] > 0:
                st.iloc[i] = min(
                    upper.iloc[i],
                    st.iloc[i - 1] if pd.notna(st.iloc[i - 1]) else upper.iloc[i],
                )
            else:
                st.iloc[i] = max(
                    lower.iloc[i],
                    st.iloc[i - 1] if pd.notna(st.iloc[i - 1]) else lower.iloc[i],
                )
    return st, pd.Series(dir, index=close.index)
