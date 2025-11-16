"""Tests for capital_client module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from tools.capital_client import CapitalClient


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for CapitalClient."""
    monkeypatch.setenv("CAPITAL_API_BASE", "https://test-api.capital.com")
    monkeypatch.setenv("CAPITAL_API_KEY", "test_key")
    monkeypatch.setenv("CAPITAL_USERNAME", "test_user")
    monkeypatch.setenv("CAPITAL_PASSWORD", "test_pass")


@pytest.fixture
def mock_session():
    """Mock requests.Session for CapitalClient."""
    with patch("tools.capital_client.requests.Session") as mock:
        session_instance = MagicMock()
        mock.return_value = session_instance

        # Mock successful authentication
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "CST": "test_cst",
            "securityToken": "test_token",
        }
        auth_response.headers.get.side_effect = lambda k: {
            "CST": "test_cst",
            "X-SECURITY-TOKEN": "test_token",
        }.get(k)
        session_instance.post.return_value = auth_response

        yield session_instance


def test_resolve_epic_xauusd_to_gold(mock_env, mock_session):
    """Test that _resolve_epic maps XAUUSD to GOLD."""
    client = CapitalClient()

    epic = client._resolve_epic("XAUUSD")
    assert epic == "GOLD"

    epic = client._resolve_epic("xauusd")
    assert epic == "GOLD"


def test_resolve_epic_unmapped_symbol(mock_env, mock_session):
    """Test that _resolve_epic returns symbol as-is if not in override."""
    client = CapitalClient()

    epic = client._resolve_epic("BTCUSD")
    assert epic == "BTCUSD"

    epic = client._resolve_epic("EURUSD")
    assert epic == "EURUSD"


def test_get_candles_uses_epic_override(mock_env, mock_session):
    """Test that get_candles uses epic override for API calls."""
    client = CapitalClient()

    # Mock the GET request for get_candles
    candles_response = Mock()
    candles_response.status_code = 200
    candles_response.json.return_value = {
        "prices": [{"time": "2023-01-01", "price": 1800}]
    }
    mock_session.get.return_value = candles_response

    # Call get_candles with XAUUSD
    result = client.get_candles("XAUUSD", resolution="HOUR", max=100)

    # Verify that the API was called with GOLD epic, not XAUUSD
    mock_session.get.assert_called_once()
    call_args = mock_session.get.call_args
    url = call_args[0][0]

    # URL should contain GOLD, not XAUUSD
    assert "GOLD" in url
    assert "XAUUSD" not in url
    assert result == [{"time": "2023-01-01", "price": 1800}]


def test_get_candles_unmapped_symbol(mock_env, mock_session):
    """Test that get_candles uses symbol as-is if not in override."""
    client = CapitalClient()

    # Mock the GET request
    candles_response = Mock()
    candles_response.status_code = 200
    candles_response.json.return_value = {"prices": []}
    mock_session.get.return_value = candles_response

    # Call get_candles with unmapped symbol
    result = client.get_candles("BTCUSD", resolution="HOUR")

    # Verify that the API was called with BTCUSD
    mock_session.get.assert_called_once()
    call_args = mock_session.get.call_args
    url = call_args[0][0]

    assert "BTCUSD" in url


def test_get_candles_error_handling(mock_env, mock_session):
    """Test that get_candles handles API errors gracefully."""
    client = CapitalClient()

    # Mock failed request
    candles_response = Mock()
    candles_response.status_code = 404
    candles_response.json.return_value = {}
    mock_session.get.return_value = candles_response

    # Call get_candles
    result = client.get_candles("XAUUSD")

    # Should return empty list on error
    assert result == []
