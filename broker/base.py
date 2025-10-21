
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class Order:
    symbol: str
    side: str     # buy/sell
    qty: float
    price: float

class Broker:
    def get_account_summary(self) -> Dict: ...
    def get_positions(self) -> Dict[str, float]: ...
    def place_order(self, order: Order) -> str: ...
    def close_position(self, symbol: str) -> None: ...
