"""
Capital.com constants and helper functions for symbol display overrides.
"""

# Symbol to Epic Override Mapping
# Maps logical symbols to their display names
SYMBOL_EPIC_OVERRIDE: dict[str, str] = {
    "XAUUSD": "GOLD",
}


def get_display_symbol(symbol: str) -> str:
    """
    Return the user-facing symbol for a logical input symbol.
    
    Args:
        symbol: The logical symbol (e.g., "XAUUSD", "xauusd")
    
    Returns:
        The display symbol (e.g., "GOLD" for "XAUUSD")
    
    Examples:
        >>> get_display_symbol("XAUUSD")
        'GOLD'
        >>> get_display_symbol("xauusd")
        'GOLD'
        >>> get_display_symbol("BTCUSD")
        'BTCUSD'
    """
    symbol_u = symbol.upper()
    return SYMBOL_EPIC_OVERRIDE.get(symbol_u, symbol_u)
