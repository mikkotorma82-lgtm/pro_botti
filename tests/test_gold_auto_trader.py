"""
Tests for gold_auto_trader.py
"""

import sys
import os
import pytest
import logging
from unittest.mock import Mock, MagicMock, patch
from io import StringIO

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.gold_auto_trader import GoldAutoTrader
from tools.capital_constants import get_display_symbol


class MockCapitalClient:
    """Mock Capital.com client for testing."""
    pass


def test_gold_auto_trader_initialization():
    """Test GoldAutoTrader initialization with XAUUSD symbol."""
    client = MockCapitalClient()
    
    trader = GoldAutoTrader(
        client=client,
        symbol="XAUUSD",
        timeframe="15m"
    )
    
    assert trader.logical_symbol == "XAUUSD"
    assert trader.display_symbol == "GOLD"
    assert trader.timeframe == "15m"


def test_gold_auto_trader_display_symbol_xauusd():
    """Test that XAUUSD displays as GOLD."""
    client = MockCapitalClient()
    
    trader = GoldAutoTrader(
        client=client,
        symbol="XAUUSD"
    )
    
    assert trader.display_symbol == "GOLD", \
        f"Expected display_symbol to be 'GOLD' for 'XAUUSD', got '{trader.display_symbol}'"


def test_gold_auto_trader_display_symbol_lowercase():
    """Test that lowercase xauusd also displays as GOLD."""
    client = MockCapitalClient()
    
    trader = GoldAutoTrader(
        client=client,
        symbol="xauusd"
    )
    
    assert trader.display_symbol == "GOLD", \
        f"Expected display_symbol to be 'GOLD' for 'xauusd', got '{trader.display_symbol}'"


def test_gold_auto_trader_other_symbol():
    """Test that other symbols are not overridden."""
    client = MockCapitalClient()
    
    trader = GoldAutoTrader(
        client=client,
        symbol="BTCUSD"
    )
    
    assert trader.display_symbol == "BTCUSD", \
        f"Expected display_symbol to be 'BTCUSD', got '{trader.display_symbol}'"


def test_header_log_contains_gold_symbol(caplog):
    """Test that header log contains 'Symbol: GOLD' for XAUUSD, not 'Symbol: XAUUSD'."""
    client = MockCapitalClient()
    
    # Capture logs
    with caplog.at_level(logging.INFO):
        trader = GoldAutoTrader(
            client=client,
            symbol="XAUUSD",
            timeframe="15m"
        )
    
    # Check that logs contain the display symbol
    log_text = caplog.text
    
    # Should contain "Symbol: GOLD"
    assert "Symbol: GOLD" in log_text, \
        f"Header log should contain 'Symbol: GOLD', got:\n{log_text}"
    
    # Should NOT contain "Symbol: XAUUSD"
    assert "Symbol: XAUUSD" not in log_text, \
        f"Header log should NOT contain 'Symbol: XAUUSD', got:\n{log_text}"


def test_header_log_format(caplog):
    """Test that header log has proper format."""
    client = MockCapitalClient()
    
    with caplog.at_level(logging.INFO):
        trader = GoldAutoTrader(
            client=client,
            symbol="XAUUSD",
            timeframe="1h",
            risk_pct=0.03,
            stop_loss_atr=2.5,
            take_profit_atr=5.0
        )
    
    log_text = caplog.text
    
    # Check for expected header elements
    assert "AUTOMATED GOLD TRADER INITIALIZED" in log_text
    assert "Symbol: GOLD" in log_text
    assert "Timeframe: 1h" in log_text
    assert "Risk per trade: 3.00%" in log_text
    assert "Stop Loss: 2.5x ATR" in log_text
    assert "Take Profit: 5.0x ATR" in log_text


def test_get_status_returns_display_symbol():
    """Test that get_status returns display_symbol."""
    client = MockCapitalClient()
    
    trader = GoldAutoTrader(
        client=client,
        symbol="XAUUSD",
        timeframe="15m"
    )
    
    status = trader.get_status()
    
    assert status["symbol"] == "GOLD", \
        f"Status should show display symbol 'GOLD', got '{status['symbol']}'"
    assert status["logical_symbol"] == "XAUUSD", \
        f"Status should preserve logical symbol 'XAUUSD', got '{status['logical_symbol']}'"


def test_start_log_uses_display_symbol(caplog):
    """Test that start() method logs use display symbol."""
    client = MockCapitalClient()
    
    trader = GoldAutoTrader(
        client=client,
        symbol="XAUUSD",
        timeframe="15m"
    )
    
    # Mock the model
    trader.model = Mock()
    
    with caplog.at_level(logging.INFO):
        trader.start()
    
    log_text = caplog.text
    
    # Should mention GOLD, not XAUUSD in trading logs
    assert "GOLD" in log_text or "gold" in log_text.lower(), \
        f"Start log should reference display symbol, got:\n{log_text}"


def test_stop_log_uses_display_symbol(caplog):
    """Test that stop() method logs use display symbol."""
    client = MockCapitalClient()
    
    trader = GoldAutoTrader(
        client=client,
        symbol="XAUUSD",
        timeframe="15m"
    )
    
    with caplog.at_level(logging.INFO):
        trader.stop()
    
    log_text = caplog.text
    
    # Should mention GOLD in stop log
    assert "GOLD" in log_text, \
        f"Stop log should reference display symbol 'GOLD', got:\n{log_text}"


def test_capital_constants_get_display_symbol():
    """Test the get_display_symbol helper function."""
    assert get_display_symbol("XAUUSD") == "GOLD"
    assert get_display_symbol("xauusd") == "GOLD"
    assert get_display_symbol("XaUuSd") == "GOLD"
    assert get_display_symbol("BTCUSD") == "BTCUSD"
    assert get_display_symbol("EURUSD") == "EURUSD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
