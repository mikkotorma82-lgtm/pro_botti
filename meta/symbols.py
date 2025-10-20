import re
from typing import List, Tuple, Dict
import ccxt

# Tunnetut koodit pari-normalisointia varten (BTCUSD -> BTC/USD, ETHUSDT -> ETH/USDT)
CODES = {
    # fiat
    "USD","EUR","GBP","JPY","CHF","AUD","CAD","NZD","SEK","NOK","DKK","TRY","ZAR","PLN","CZK","HUF",
    # stables
    "USDT","USDC","BUSD","DAI","TUSD","FDUSD","PYUSD",
    # major crypto
    "BTC","XBT","ETH","XRP","LTC","BCH","BNB","ADA","SOL","DOT","DOGE","TRX","AVAX","ATOM","MATIC","LINK",
}

# Kraken-aliakset (jos käytät krakenia – capitalcom ei tarvitse tätä)
KRAKEN_TICKER_ALIASES = {
    ("BTC",): "XBT",
}

def _maybe_pair(symbol: str) -> str:
    """
    Muunna 'BTCUSD' -> 'BTC/USD', 'ETHUSDT' -> 'ETH/USDT' jos mahdollista.
    Jätä indeksit/osakkeet/erikoistunnukset koskematta.
    """
    s = symbol.strip().upper().replace(" ", "").replace("-", "").replace("_", "")
    if "/" in s:
        return s
    if len(s) < 6:
        return symbol
    for i in range(3, min(5, len(s)-2)+1):
        base, quote = s[:i], s[i:]
        if base in CODES and quote in CODES:
            return f"{base}/{quote}"
    return symbol

def _apply_exchange_aliases(exchange_id: str, pair: str) -> str:
    if "/" not in pair:
        return pair
    base, quote = pair.split("/", 1)
    if exchange_id == "kraken":
        for keys, repl in KRAKEN_TICKER_ALIASES.items():
            if base in keys:
                base = repl
                break
    return f"{base}/{quote}"

def load_symbols_file(path: str) -> List[str]:
    syms = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            syms.append(s)
    seen = set(); out = []
    for s in syms:
        if s not in seen:
            out.append(s); seen.add(s)
    return out

def normalize_symbols(exchange_id: str, symbols: List[str]) -> List[str]:
    out = []
    for s in symbols:
        p = _maybe_pair(s)
        p = _apply_exchange_aliases(exchange_id, p)
        out.append(p)
    return out

def filter_supported_symbols(exchange, symbols: List[str]) -> Tuple[List[str], Dict[str, str]]:
    supported = []
    rejected: Dict[str, str] = {}
    exchange.load_markets()
    ex_syms = set(exchange.symbols or [])
    for s in symbols:
        if s in ex_syms:
            supported.append(s)
        else:
            rejected[s] = "unsupported-by-exchange"
    return supported, rejected
