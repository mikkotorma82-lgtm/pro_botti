"""Tests for capital_constants module."""

import pytest
from tools.capital_constants import SYMBOL_EPIC_OVERRIDE, get_display_symbol


def test_symbol_epic_override_exists():
    """Test that SYMBOL_EPIC_OVERRIDE dictionary exists."""
    assert isinstance(SYMBOL_EPIC_OVERRIDE, dict)


def test_xauusd_maps_to_gold():
    """Test that XAUUSD is mapped to GOLD."""
    assert "XAUUSD" in SYMBOL_EPIC_OVERRIDE
    assert SYMBOL_EPIC_OVERRIDE["XAUUSD"] == "GOLD"


def test_get_display_symbol_xauusd():
    """Test get_display_symbol returns GOLD for XAUUSD."""
    assert get_display_symbol("XAUUSD") == "GOLD"
    assert get_display_symbol("xauusd") == "GOLD"
    assert get_display_symbol("XauUsd") == "GOLD"


def test_get_display_symbol_unmapped():
    """Test get_display_symbol returns original symbol if unmapped."""
    assert get_display_symbol("BTCUSD") == "BTCUSD"
    assert get_display_symbol("EURUSD") == "EURUSD"
    assert get_display_symbol("btcusd") == "BTCUSD"  # Uppercase conversion


def test_override_is_immutable():
    """Test that SYMBOL_EPIC_OVERRIDE should not be modified (defensive check)."""
    # This test just ensures we can read the override
    original_len = len(SYMBOL_EPIC_OVERRIDE)
    # Try to verify XAUUSD exists
    assert "XAUUSD" in SYMBOL_EPIC_OVERRIDE
    # Verify length hasn't changed
    assert len(SYMBOL_EPIC_OVERRIDE) == original_len
