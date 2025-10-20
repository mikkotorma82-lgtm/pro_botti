import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

def to_timestamp(dt, tz="UTC"):
    # Konvertoi datetime/string -> UTC timestamp
    if isinstance(dt, str):
        try:
            dt = pd.to_datetime(dt)
        except Exception:
            return None
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())

def to_datetime(ts, tz="UTC"):
    # Konvertoi timestamp -> pandas.Timestamp
    try:
        dt = pd.Timestamp(ts, unit="s", tz=tz)
    except Exception:
        dt = pd.Timestamp(ts, unit="s")
    return dt

def round_time(dt, tf="1h"):
    # Pyöristää ajan TF:ään (esim. 15m, 1h, 1d)
    if isinstance(dt, str):
        dt = pd.to_datetime(dt)
    if tf.endswith("m"):
        minutes = int(tf[:-1])
        dt = dt - timedelta(minutes=dt.minute % minutes, seconds=dt.second, microseconds=dt.microsecond)
    elif tf.endswith("h"):
        hours = int(tf[:-1])
        dt = dt.replace(minute=0, second=0, microsecond=0)
        dt = dt - timedelta(hours=dt.hour % hours)
    elif tf == "1d":
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt

def time_range(start, end, tf="1h"):
    # Luo aikavälin listan halutulla TF:llä
    start = pd.to_datetime(start)
    end = pd.to_datetime(end)
    freq = tf if tf in ["15m", "1h", "4h", "1d"] else "1h"
    return pd.date_range(start, end, freq=freq).to_pydatetime().tolist()

def trading_week(dt=None):
    # Palauttaa viikon numeron ja trading-päivän (ma-pe)
    dt = pd.to_datetime(dt) if dt else pd.Timestamp.now(tz="UTC")
    week = dt.isocalendar()[1]
    day = dt.weekday()  # 0=ma, 6=su
    return week, day

def is_trading_day(dt=None):
    # Onko trading-päivä (ma-pe)?
    dt = pd.to_datetime(dt) if dt else pd.Timestamp.now(tz="UTC")
    return dt.weekday() < 5

def utc_now():
    return datetime.utcnow().replace(tzinfo=timezone.utc)
