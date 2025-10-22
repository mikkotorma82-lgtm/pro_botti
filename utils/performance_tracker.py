import pandas as pd
import numpy as np
from loguru import logger

class PerformanceTracker:
    def __init__(self):
        self.history = []  # List of dicts: {"timestamp", "symbol", "tf", "strategy", "pnl", "risk", ...}
        self.current = {}  # symbol+tf+strategy -> latest P&L

    def update(self, symbol, tf, strategy, pnl, risk=None, timestamp=None):
        """
        Päivittää suorituskykytiedot ja tallentaa historiadataa.
        """
        row = {
            "timestamp": timestamp if timestamp else pd.Timestamp.now(),
            "symbol": symbol,
            "tf": tf,
            "strategy": strategy,
            "pnl": float(pnl),
            "risk": float(risk) if risk is not None else None
        }
        self.history.append(row)
        key = f"{symbol}-{tf}-{strategy}"
        self.current[key] = row

    def get_latest(self, symbol, tf, strategy):
        key = f"{symbol}-{tf}-{strategy}"
        return self.current.get(key, None)

    def get_summary(self):
        """
        Palauttaa DataFrame-yhteenvedon kaikista positioista/strategioista.
        """
        df = pd.DataFrame(self.history)
        if df.empty:
            return pd.DataFrame()
        summary = df.groupby(["symbol", "tf", "strategy"]).agg({
            "pnl": ["sum", "mean", "count"],
            "risk": ["mean", "max", "min"]
        }).reset_index()
        return summary

    def report(self, send_func=None):
        """
        Raportoi tulokset tekstimuotoisena tai lähettää ulkoiseen raportointiin.
        """
        summary = self.get_summary()
        if summary.empty:
            logger.info("No performance data available.")
            return
        msg = summary.to_string()
        logger.info(f"PerformanceTracker report:\n{msg}")
        if send_func:
            send_func(msg)
