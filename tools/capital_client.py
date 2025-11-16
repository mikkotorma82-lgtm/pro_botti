import os
import json
import requests
from tools.capital_constants import SYMBOL_EPIC_OVERRIDE

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
        Resolve a symbol to its Capital.com epic identifier.
        
        Uses SYMBOL_EPIC_OVERRIDE to map logical symbols (e.g., "XAUUSD")
        to their Capital.com epic codes (e.g., "GOLD").
        
        Args:
            symbol: The logical symbol (e.g., "XAUUSD", "BTCUSD")
        
        Returns:
            The Capital.com epic identifier
        
        Examples:
            >>> client._resolve_epic("XAUUSD")
            'GOLD'
            >>> client._resolve_epic("BTCUSD")
            'BTCUSD'
        """
        symbol_u = symbol.upper()
        return SYMBOL_EPIC_OVERRIDE.get(symbol_u, symbol_u)

    def get_candles(self, epic, resolution="HOUR", max=200, from_ts=None, to_ts=None):
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
