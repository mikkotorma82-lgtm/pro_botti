import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

# Symbol to epic override mapping
# When a symbol matches a key, the corresponding epic is used instead of market discovery
SYMBOL_EPIC_OVERRIDE: dict[str, str] = {
    "XAUUSD": "GOLD",  # always use GOLD epic when symbol is XAUUSD
}


class CapitalClient:
    def __init__(self):
        self.base = os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com")
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
        Resolve the epic for a given trading symbol.
        
        If the symbol has an override mapping, use the override epic.
        Otherwise, return the symbol as-is (assumes symbol == epic).
        
        Args:
            symbol: The trading symbol (e.g., "XAUUSD")
            
        Returns:
            The epic to use for API calls (e.g., "GOLD")
        """
        symbol_u = symbol.upper()
        if symbol_u in SYMBOL_EPIC_OVERRIDE:
            epic = SYMBOL_EPIC_OVERRIDE[symbol_u]
            logger.info("Using epic override for symbol %s -> %s", symbol_u, epic)
            return epic
        return symbol

    def get_candles(self, epic, resolution="HOUR", max=200, from_ts=None, to_ts=None):
        # Resolve epic override (e.g., XAUUSD -> GOLD)
        epic = self._resolve_epic(epic)
        
        url = f"{self.base}/api/v1/prices/{epic}"
        params = {"resolution": resolution, "max": max}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts
        r = self.session.get(url, params=params)
        if r.status_code != 200:
            print(f"[WARN] get_candles {epic}: {r.status_code}")
            return []
        return r.json().get("prices", [])

    def get_positions(self):
        url = f"{self.base}/api/v1/positions"
        r = self.session.get(url)
        if r.status_code != 200:
            print(f"[WARN] get_positions: {r.status_code}")
            return []
        return r.json().get("positions", [])
