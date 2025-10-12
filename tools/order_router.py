from __future__ import annotations
import os
from tools import capital_client as cap

def to_cap_epic(symbol: str) -> str:
    return symbol.replace("/", "")

def create_market_order(symbol: str, side: str, qty: float, dry_run: bool|None=None):
    if dry_run is None:
        dry_run = (os.environ.get("DRY_RUN","1") != "0")
    epic = to_cap_epic(symbol)
    if dry_run:
        return {"dry_run": True, "exchange": "capital", "symbol": epic,
                "side": side, "qty": qty, "type": "market"}
    res = cap.market_order(epic=epic, direction=side, size=qty)
    return {"dry_run": False, "exchange": "capital", "symbol": epic,
            "side": side, "qty": qty, "type": "market", "result": res}
