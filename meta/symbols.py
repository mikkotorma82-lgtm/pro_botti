import re
from typing import List, Tuple, Dict
import ccxt

KRAKEN_TICKER_MAP = {
    # Kraken käyttää XBT/USD eikä BTC/USD
    r"\bBTC/USD\b": "XBT/USD",
    # Lisää tarvittaessa muita poikkeuksia
}

def load_symbols_file(path: str) -> List[str]:
    syms = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            syms.append(s)
    # duplikaatit pois, säilytä järjestys
    seen = set()
    out = []
    for s in syms:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out

def normalize_for_kraken(symbol: str) -> str:
    for pat, repl in KRAKEN_TICKER_MAP.items():
        if re.search(pat, symbol):
            return re.sub(pat, repl, symbol)
    return symbol

def normalize_symbols(exchange_id: str, symbols: List[str]) -> List[str]:
    if exchange_id == "kraken":
        return [normalize_for_kraken(s) for s in symbols]
    return symbols

def filter_supported_symbols(exchange, symbols: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """
    Palauttaa (supported, rejected_reasons)
    """
    supported = []
    rejected = {}
    markets = exchange.load_markets()
    ex_syms = set(exchange.symbols or [])
    for s in symbols:
        if s in ex_syms:
            supported.append(s)
        else:
            rejected[s] = "unsupported-by-exchange"
    return supported, rejected
