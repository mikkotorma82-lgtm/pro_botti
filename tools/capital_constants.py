"""
Shared constants for Capital.com API clients.

This module contains configuration constants used across different
Capital.com client implementations to ensure consistency.
"""

# Symbol to epic override mapping
# When a symbol matches a key, the corresponding epic is used instead of market discovery
SYMBOL_EPIC_OVERRIDE: dict[str, str] = {
    "XAUUSD": "GOLD",  # always use GOLD epic when symbol is XAUUSD
}
