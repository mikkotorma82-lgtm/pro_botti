from pathlib import Path
import json

ALIASES_PATH = Path(__file__).resolve().parent.parent / "config" / "aliases.json"

def _load_aliases():
    try:
        with open(ALIASES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def resolve(symbol: str) -> str:
    aliases = _load_aliases()
    if symbol in aliases:
        return aliases[symbol]
    if symbol.endswith("USDT"):
        return symbol[:-4] + "USD"
    return symbol
