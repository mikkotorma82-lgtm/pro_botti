"""Tests for capital_session module epic resolution."""

import pytest
from unittest.mock import patch, MagicMock
from tools.capital_session import _resolve_epic


def test_resolve_epic_uses_symbol_override():
    """Test that _resolve_epic prioritizes SYMBOL_EPIC_OVERRIDE."""
    # XAUUSD should resolve to GOLD via SYMBOL_EPIC_OVERRIDE
    epic = _resolve_epic("XAUUSD")
    assert epic == "GOLD"

    epic = _resolve_epic("xauusd")
    assert epic == "GOLD"


def test_resolve_epic_already_epic():
    """Test that _resolve_epic returns EPIC-like strings as-is."""
    # EPIC-like strings have dots and no spaces
    epic = _resolve_epic("IX.D.SPTRD.IFM")
    assert epic == "IX.D.SPTRD.IFM"


def test_resolve_epic_override_before_env(monkeypatch):
    """Test that SYMBOL_EPIC_OVERRIDE takes precedence over env vars."""
    # Set an environment variable that conflicts with override
    monkeypatch.setenv("CAPITAL_EPIC_XAUUSD", "WRONGEPIC")

    # SYMBOL_EPIC_OVERRIDE should take precedence
    epic = _resolve_epic("XAUUSD")
    assert epic == "GOLD"
    assert epic != "WRONGEPIC"


@patch("tools.capital_session.capital_market_search")
def test_resolve_epic_unmapped_symbol(mock_search):
    """Test that unmapped symbols fall through to market search."""
    # Mock market search to return a result
    mock_search.return_value = [
        {"epic": "BTC.USD.IP", "instrumentName": "Bitcoin", "symbol": "BTCUSD"}
    ]

    # BTCUSD is not in SYMBOL_EPIC_OVERRIDE, should use market search
    with patch("tools.capital_session._epic_cache_load", return_value={}):
        with patch("tools.capital_session._epic_cache_save"):
            epic = _resolve_epic("BTCUSD")

            # Should have called market search
            mock_search.assert_called_once_with("BTCUSD")
            # Should return the epic from search result
            assert epic == "BTC.USD.IP"
