
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import pandas as pd

@dataclass
class PaperState:
    cash: float
    positions: Dict[str, float]

class PaperBroker:
    def __init__(self, cash: float=100000.0):
        self.state = PaperState(cash=cash, positions={})
    def get_account_summary(self) -> Dict:
        return {"equity": self.state.cash, "cash": self.state.cash}
    def get_positions(self) -> Dict[str, float]:
        return dict(self.state.positions)
    def place_order(self, symbol: str, side: str, qty: float, price: float):
        notional = qty*price
        if side == "buy":
            self.state.cash -= notional
            self.state.positions[symbol] = self.state.positions.get(symbol, 0.0) + qty
        else:
            self.state.cash += notional
            self.state.positions[symbol] = self.state.positions.get(symbol, 0.0) - qty
    def close_position(self, symbol: str, price: float):
        qty = self.state.positions.get(symbol, 0.0)
        if qty != 0:
            side = "sell" if qty>0 else "buy"
            self.place_order(symbol, side, abs(qty), price)
            self.state.positions[symbol] = 0.0
