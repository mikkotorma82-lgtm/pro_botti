CAPITAL_MAP = {
    "BTCUSDT": "BTCUSD",
    "ETHUSDT": "ETHUSD",
    "ADAUSDT": "ADAUSD",
    "SOLUSDT": "SOLUSD",
    "XRPUSDT": "XRPUSD",
    "US100": "US_Tech100",
    "US500": "US_500",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "AAPL": "AAPL",
    "NVDA": "NVDA",
    "TSLA": "TSLA",
}

def map_symbol(sym, broker):
    if broker == "capitalcom":
        return CAPITAL_MAP.get(sym, sym)
    return sym
