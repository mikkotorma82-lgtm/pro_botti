#!/usr/bin/env python3
"""Tests for tools.capital_client"""

import os
import json
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add parent directory to path so we can import tools
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.capital_client import CapitalClient, SYMBOL_EPIC_OVERRIDE


def test_symbol_epic_override_exists():
    """Test that SYMBOL_EPIC_OVERRIDE dictionary exists and contains XAUUSD mapping."""
    assert "XAUUSD" in SYMBOL_EPIC_OVERRIDE
    assert SYMBOL_EPIC_OVERRIDE["XAUUSD"] == "GOLD"


def test_resolve_epic_uses_override_for_xauusd():
    """Test that _resolve_epic uses the override for XAUUSD symbol."""
    # Mock the authentication to avoid actual API calls
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        # Create client instance with mocked auth
        client = CapitalClient()
        
        # Test that XAUUSD resolves to GOLD without making API calls
        epic = client._resolve_epic("XAUUSD")
        assert epic == "GOLD"


def test_resolve_epic_case_insensitive():
    """Test that _resolve_epic is case insensitive for overrides."""
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        client = CapitalClient()
        
        # Test lowercase
        assert client._resolve_epic("xauusd") == "GOLD"
        
        # Test mixed case
        assert client._resolve_epic("XauUsd") == "GOLD"


def test_resolve_epic_auto_discovery():
    """Test that _resolve_epic falls back to auto-discovery for non-override symbols."""
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        client = CapitalClient()
        
        # Mock _search_markets to return test data
        mock_markets = [
            {
                "epic": "TEST.EPIC.123",
                "instrumentName": "Test Instrument",
                "type": "SHARES"
            }
        ]
        
        with patch.object(client, '_search_markets', return_value=mock_markets):
            epic = client._resolve_epic("TEST")
            assert epic == "TEST.EPIC.123"


def test_resolve_epic_prefers_gold_commodities():
    """Test that _resolve_epic prefers GOLD in COMMODITIES category."""
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        client = CapitalClient()
        
        # Mock _search_markets to return test data with multiple matches
        mock_markets = [
            {
                "epic": "SHARES.GOLD.123",
                "instrumentName": "Gold Mining Corp",
                "type": "SHARES"
            },
            {
                "epic": "COMMODITIES.GOLD.456",
                "instrumentName": "Gold Spot",
                "type": "COMMODITIES"
            }
        ]
        
        with patch.object(client, '_search_markets', return_value=mock_markets):
            epic = client._resolve_epic("SOMEGOLD")
            # Should prefer COMMODITIES type with "gold" in name
            assert epic == "COMMODITIES.GOLD.456"


def test_resolve_epic_raises_on_no_markets():
    """Test that _resolve_epic raises ValueError when no markets found."""
    with patch.object(CapitalClient, '_authenticate', return_value=None):
        client = CapitalClient()
        
        # Mock _search_markets to return empty list
        with patch.object(client, '_search_markets', return_value=[]):
            try:
                client._resolve_epic("NONEXISTENT")
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "No markets found for symbol NONEXISTENT" in str(e)


if __name__ == "__main__":
    # Simple test runner
    import traceback
    
    tests = [
        test_symbol_epic_override_exists,
        test_resolve_epic_uses_override_for_xauusd,
        test_resolve_epic_case_insensitive,
        test_resolve_epic_auto_discovery,
        test_resolve_epic_prefers_gold_commodities,
        test_resolve_epic_raises_on_no_markets,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}")
            traceback.print_exc()
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
