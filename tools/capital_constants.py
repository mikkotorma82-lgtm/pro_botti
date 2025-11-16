"""
Shared constants for Capital.com API clients.

This module contains configuration constants used across different
Capital.com client implementations to ensure consistency.
"""

from tools.symbol_resolver import _MAP as SYMBOL_NORMALIZATION_MAP

# Symbol to epic override mapping for Capital.com API
# Reuses existing symbol normalization mappings for consistency
# When a symbol matches a key, the corresponding epic is used instead of market discovery
SYMBOL_EPIC_OVERRIDE: dict[str, str] = SYMBOL_NORMALIZATION_MAP.copy()
