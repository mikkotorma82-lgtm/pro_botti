import os
import json
import logging
import requests
from tools.capital_constants import SYMBOL_EPIC_OVERRIDE

logger = logging.getLogger(__name__)


class CapitalClient:
    def __init__(self):
        self.base = os.getenv(
            "CAPITAL_API_BASE", "https://api-capital.backend-capital.com"
        )
        self.api_key = os.getenv("CAPITAL_API_KEY")
        self.username = os.getenv("CAPITAL_USERNAME")
        self.password = os.getenv("CAPITAL_PASSWORD")
        self.session = requests.Session()
        self._authenticate()

    def _authenticate(self):
        url = f"{self.base}/api/v1/session"
        headers = {"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"}
        payload = {"identifier": self.username, "password": self.password}
        r = self.session.post(url, headers=headers, data=json.dumps(payload))
        if r.status_code != 200:
            raise Exception(f"Capital.com auth failed: {r.text}")
        data = r.json()
        cst = data.get("CST") or r.headers.get("CST")
        sec = data.get("securityToken") or r.headers.get("X-SECURITY-TOKEN")
        if not cst or not sec:
            raise Exception(f"Capital.com auth missing tokens: {r.text}")
        self.session.headers.update({"CST": cst, "X-SECURITY-TOKEN": sec})

    def _resolve_epic(self, symbol: str) -> str:
        """
        Resolve symbol to epic using SYMBOL_EPIC_OVERRIDE.

        Args:
            symbol: The input symbol (e.g., "XAUUSD")

        Returns:
            The epic to use for API calls (e.g., "GOLD")
        """
        symbol_u = symbol.upper()
        if symbol_u in SYMBOL_EPIC_OVERRIDE:
            epic = SYMBOL_EPIC_OVERRIDE[symbol_u]
            logger.info("Using epic override for symbol %s -> %s", symbol_u, epic)
            return epic
        return symbol

    def get_candles(self, symbol, resolution="HOUR", max=200, from_ts=None, to_ts=None):
        """
        Get candles for a symbol (auto-resolves to epic).

        Args:
            symbol: The symbol (e.g., "XAUUSD") - will be resolved to epic
            resolution: Time resolution
            max: Maximum number of candles
            from_ts: Start timestamp
            to_ts: End timestamp

        Returns:
            List of candle data
        """
        epic = self._resolve_epic(symbol)
        url = f"{self.base}/api/v1/prices/{epic}"
        params = {"resolution": resolution, "max": max}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts
        r = self.session.get(url, params=params)
        if r.status_code != 200:
            logger.warning("get_candles %s (epic: %s): %s", symbol, epic, r.status_code)
            return []
        return r.json().get("prices", [])

    def get_positions(self):
        url = f"{self.base}/api/v1/positions"
        r = self.session.get(url)
        if r.status_code != 200:
            logger.warning("get_positions: %s", r.status_code)
            return []
        return r.json().get("positions", [])
