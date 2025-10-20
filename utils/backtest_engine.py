import pandas as pd
import numpy as np
from loguru import logger

class BacktestEngine:
    def __init__(self, strategy_func, data_loader, symbol, tf="1h", start=None, end=None, params=None, risk_model="default"):
        """
        strategy_func: signaalifunktio (esim. momentum_signal)
        data_loader: DataLoader-instanssi
        symbol: testattava instrumentti
        tf: timeframe
        params: strategian parametrit (dict)
        risk_model: TP/SL-mallin nimi
        """
        self.strategy_func = strategy_func
        self.data_loader = data_loader
        self.symbol = symbol
        self.tf = tf
        self.start = start
        self.end = end
        self.params = params if params else {}
        self.risk_model = risk_model
        self.results = []

    def run(self):
        # Lataa data
        df = self.data_loader.load(self.symbol, self.tf, self.start, self.end)
        if df is None or df.empty:
            logger.error(f"No data for backtest: {self.symbol} {self.tf}")
            return pd.DataFrame()
        df = df.reset_index(drop=True)
        position = None
        entry_px = 0
        pnl = 0
        trades = []
        for i in range(30, len(df)):
            window = df.iloc[i-30:i].copy()
            signal = self.strategy_func(window, self.params)
            price = df.iloc[i]["close"]
            timestamp = df.iloc[i]["timestamp"]
            # Entry
            if position is None and signal != 0:
                position = signal  # 1=long, -1=short
                entry_px = price
                entry_time = timestamp
            # Exit: signaalin vaihto tai riskimallin trigger
            elif position is not None:
                # TP/SL/Trail
                levels = self._compute_levels(position, entry_px, price, df.iloc[max(i-14,0):i+1])
                sl = levels["sl"]
                tp = levels["tp"]
                trail = levels["trail"]
                exit = False
                if (position == 1 and price <= sl) or (position == -1 and price >= sl):
                    exit = True
                    exit_reason = "SL"
                elif (position == 1 and price >= tp) or (position == -1 and price <= tp):
                    exit = True
                    exit_reason = "TP"
                elif signal != position and signal != 0:
                    exit = True
                    exit_reason = "Signal flip"
                elif (position == 1 and price <= trail) or (position == -1 and price >= trail):
                    exit = True
                    exit_reason = "Trail"
                if exit:
                    trade_pnl = (price - entry_px) * position
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": timestamp,
                        "entry_px": entry_px,
                        "exit_px": price,
                        "position": position,
                        "pnl": trade_pnl,
                        "reason": exit_reason
                    })
                    position = None
                    entry_px = 0
        self.results = trades
        return pd.DataFrame(trades)

    def _compute_levels(self, position, entry_px, price, df_window):
        # Dynaaminen TP/SL/Trail
        from tools.tp_sl import compute_levels
        side = "BUY" if position == 1 else "SELL"
        return compute_levels(self.symbol, side, entry_px, risk_model=self.risk_model, df=df_window)

    def summary(self):
        if not self.results:
            return {}
        df = pd.DataFrame(self.results)
        total_pnl = df["pnl"].sum()
        trade_count = len(df)
        win_count = (df["pnl"] > 0).sum()
        loss_count = (df["pnl"] < 0).sum()
        avg_pnl = df["pnl"].mean() if trade_count > 0 else 0
        win_rate = win_count / trade_count if trade_count > 0 else 0
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "trades": trade_count,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "win_rate": win_rate,
        }
