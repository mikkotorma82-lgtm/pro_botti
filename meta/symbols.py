import re
from typing import List, Tuple, Dict, Any, Optional

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

# Try to import ccxt, but it's optional for capitalcom
try:
    import ccxt
    _ccxt_available = True
except ImportError:
    ccxt = None
    _ccxt_available = False

# Try to import Capital.com tools
try:
    from tools.capital_session import capital_rest_login
    from tools.epic_resolver import resolve_epic
    _capital_available = True
except ImportError:
    capital_rest_login = None
    resolve_epic = None
    _capital_available = False

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

def filter_supported_symbols(exchange: Any, symbols: List[str], exchange_id: str = None) -> Tuple[List[str], Dict[str, str]]:
    """
    Filter symbols by exchange support.
    
    Args:
        exchange: Exchange instance (ccxt or custom)
        symbols: List of symbols to filter
        exchange_id: Exchange identifier (e.g., 'capitalcom', 'kraken')
    
    Returns:
        Tuple of (supported_symbols, rejected_dict)
    """
    supported = []
    rejected: Dict[str, str] = {}
    
    # Special handling for Capital.com (not a ccxt exchange)
    if exchange_id and exchange_id.lower() == "capitalcom":
        # For Capital.com, we assume all symbols are potentially valid
        # Actual validation happens when fetching data
        # But we can still do basic filtering for known invalid formats
        for s in symbols:
            # Capital.com supports forex pairs (e.g., EUR/USD), crypto (BTC/USD), indices (US500), stocks (AAPL)
            # Accept most formats; let data fetch determine actual availability
            supported.append(s)
        return supported, rejected
    
    # For ccxt exchanges
    if hasattr(exchange, 'load_markets'):
        exchange.load_markets()
        ex_syms = set(exchange.symbols or [])
        for s in symbols:
            if s in ex_syms:
                supported.append(s)
            else:
                rejected[s] = "unsupported-by-exchange"
    else:
        # Unknown exchange type, accept all
        supported = symbols[:]
    
    return supported, rejected
