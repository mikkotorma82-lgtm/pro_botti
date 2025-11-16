"""
Capital.com constants and symbol→epic override mappings.

This module provides the single source of truth for symbol→epic mappings
used across the pro_botti codebase when interacting with Capital.com API.
"""

from typing import Dict

# Symbol→Epic override mapping
# When a symbol like "XAUUSD" should be mapped to a specific epic like "GOLD",
# define it here. This ensures consistent epic resolution across all modules.
SYMBOL_EPIC_OVERRIDE: Dict[str, str] = {
    "XAUUSD": "GOLD",
}


def get_display_symbol(input_symbol: str) -> str:
    """
    Get the display symbol for user-facing output.

    Args:
        input_symbol: The input symbol (e.g., "XAUUSD")

    Returns:
        The display symbol (e.g., "GOLD" if XAUUSD is overridden)
    """
    symbol_upper = input_symbol.upper()
    return SYMBOL_EPIC_OVERRIDE.get(symbol_upper, symbol_upper)
