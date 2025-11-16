"""
Tests for tools/capital_client.py
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.capital_client import CapitalClient


def test_resolve_epic_xauusd():
    """Test that _resolve_epic resolves XAUUSD to GOLD."""
    # Mock the authentication to avoid actual API calls
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        client = CapitalClient()
    
    assert client._resolve_epic("XAUUSD") == "GOLD"
    assert client._resolve_epic("xauusd") == "GOLD"
    assert client._resolve_epic("XaUuSd") == "GOLD"


def test_resolve_epic_other_symbols():
    """Test that _resolve_epic returns other symbols as-is (uppercase)."""
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        client = CapitalClient()
    
    assert client._resolve_epic("BTCUSD") == "BTCUSD"
    assert client._resolve_epic("btcusd") == "BTCUSD"
    assert client._resolve_epic("EURUSD") == "EURUSD"
    assert client._resolve_epic("US500") == "US500"


def test_resolve_epic_preserves_override():
    """Test that _resolve_epic uses SYMBOL_EPIC_OVERRIDE correctly."""
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        client = CapitalClient()
    
    # XAUUSD should map to GOLD via SYMBOL_EPIC_OVERRIDE
    resolved = client._resolve_epic("XAUUSD")
    assert resolved == "GOLD", f"Expected 'GOLD', got '{resolved}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
