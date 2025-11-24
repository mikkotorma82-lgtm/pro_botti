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
    with patch.object(CapitalClient, '_get_or_create_session') as mock_session:
        mock_session.return_value = MagicMock()
        # Create client instance with mocked auth
        client = CapitalClient()
        
        # Test that XAUUSD resolves to GOLD without making API calls
        epic = client._resolve_epic("XAUUSD")
        assert epic == "GOLD"


def test_resolve_epic_case_insensitive():
    """Test that _resolve_epic is case insensitive for overrides."""
    with patch.object(CapitalClient, '_get_or_create_session') as mock_session:
        mock_session.return_value = MagicMock()
        client = CapitalClient()
        
        # Test lowercase
        assert client._resolve_epic("xauusd") == "GOLD"
        
        # Test mixed case
        assert client._resolve_epic("XauUsd") == "GOLD"


def test_resolve_epic_auto_discovery():
    """Test that _resolve_epic falls back to auto-discovery for non-override symbols."""
    with patch.object(CapitalClient, '_get_or_create_session') as mock_session:
        mock_session.return_value = MagicMock()
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
    with patch.object(CapitalClient, '_get_or_create_session') as mock_session:
        mock_session.return_value = MagicMock()
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
    with patch.object(CapitalClient, '_get_or_create_session') as mock_session:
        mock_session.return_value = MagicMock()
        client = CapitalClient()
        
        # Mock _search_markets to return empty list
        with patch.object(client, '_search_markets', return_value=[]):
            try:
                client._resolve_epic("NONEXISTENT")
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "No markets found for symbol NONEXISTENT" in str(e)


def test_session_reuse_across_instances():
    """Test that multiple CapitalClient instances reuse the same session."""
    import tools.capital_client as cc_module
    
    # Reset module-level session cache
    cc_module._SHARED_SESSION = None
    cc_module._SESSION_LAST_LOGIN = 0.0
    
    # Mock the authentication
    with patch('requests.Session') as mock_session_class:
        mock_session_instance = MagicMock()
        mock_session_class.return_value = mock_session_instance
        
        # Mock successful authentication response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"CST": "test-cst", "securityToken": "test-token"}
        mock_response.headers.get.side_effect = lambda x: {"CST": "test-cst", "X-SECURITY-TOKEN": "test-token"}.get(x)
        mock_session_instance.post.return_value = mock_response
        
        # Create first client - should authenticate
        client1 = CapitalClient()
        assert mock_session_class.call_count == 1
        assert mock_session_instance.post.call_count == 1
        
        # Create second client - should reuse session
        client2 = CapitalClient()
        # Session should still be created only once
        assert mock_session_class.call_count == 1
        # Post (authentication) should still be called only once
        assert mock_session_instance.post.call_count == 1
        
        # Both clients should have the same session
        assert client1.session is client2.session


def test_session_refresh_after_ttl():
    """Test that session is refreshed after TTL expires."""
    import tools.capital_client as cc_module
    import time
    
    # Set a very short TTL for testing
    original_ttl = cc_module._SESSION_TTL
    cc_module._SESSION_TTL = 1  # 1 second
    
    try:
        # Reset module-level session cache
        cc_module._SHARED_SESSION = None
        cc_module._SESSION_LAST_LOGIN = 0.0
        
        # Mock the authentication
        with patch('requests.Session') as mock_session_class:
            mock_session_instance = MagicMock()
            mock_session_class.return_value = mock_session_instance
            
            # Mock successful authentication response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"CST": "test-cst", "securityToken": "test-token"}
            mock_response.headers.get.side_effect = lambda x: {"CST": "test-cst", "X-SECURITY-TOKEN": "test-token"}.get(x)
            mock_session_instance.post.return_value = mock_response
            
            # Create first client
            client1 = CapitalClient()
            assert mock_session_class.call_count == 1
            
            # Wait for TTL to expire
            time.sleep(1.5)
            
            # Create second client - should create new session
            client2 = CapitalClient()
            assert mock_session_class.call_count == 2
            
    finally:
        # Restore original TTL
        cc_module._SESSION_TTL = original_ttl
        cc_module._SHARED_SESSION = None
        cc_module._SESSION_LAST_LOGIN = 0.0


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
        test_session_reuse_across_instances,
        test_session_refresh_after_ttl,
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
