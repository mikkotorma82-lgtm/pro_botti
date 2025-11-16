import os
import json
import requests
from loguru import logger

SYMBOL_EPIC_OVERRIDE: dict[str, str] = {
    "XAUUSD": "GOLD",  # Käytä aina GOLD-epiciä kun symboli on XAUUSD
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

    def _search_markets(self, symbol: str) -> list:
        """Search for markets matching the given symbol."""
        url = f"{self.base}/api/v1/markets"
        params = {"searchTerm": symbol}
        r = self.session.get(url, params=params)
        if r.status_code != 200:
            logger.warning(f"Market search failed for {symbol}: {r.status_code}")
            return []
        return r.json().get("markets", [])

    def _resolve_epic(self, symbol: str) -> str:
        """Resolve Capital.com epic for given symbol.
        
        This applies hard-coded overrides first (e.g. XAUUSD -> GOLD),
        then falls back to market search auto-discovery.
        """
        symbol_u = symbol.upper()

        # 1) Hard override for known symbols
        if symbol_u in SYMBOL_EPIC_OVERRIDE:
            epic = SYMBOL_EPIC_OVERRIDE[symbol_u]
            logger.info(f"Using epic override for symbol {symbol_u} -> {epic}")
            return epic

        # 2) Auto-discovery via /api/v1/markets search
        markets = self._search_markets(symbol_u)
        if not markets:
            logger.warning(f"No markets found for symbol {symbol_u}")
            raise ValueError(f"No markets found for symbol {symbol_u}")

        # Prefer GOLD in COMMODITIES, otherwise first match
        gold_commodities = [
            m for m in markets
            if m.get("type", "").upper() == "COMMODITIES"
            and "gold" in m.get("instrumentName", "").lower()
        ]
        if gold_commodities:
            epic = gold_commodities[0].get("epic")
        else:
            epic = markets[0].get("epic")

        logger.info(f"Resolved epic for symbol {symbol_u} -> {epic} (auto-discovery)")
        return epic

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
