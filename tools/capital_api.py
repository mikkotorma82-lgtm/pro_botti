#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapitalBot – Capital.com API Client (v3 endpoint fixed)
Käyttää /api/v3/prices/{epic} hinnan hakuun (ei enää /pricehistory)
"""

import os, json, time, requests
from pathlib import Path

# --- Pakotettu secrets.env lataus ---
ENV_PATH = "/root/pro_botti/secrets.env"
if Path(ENV_PATH).exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()
else:
    print(f"[warn] secrets.env ei löytynyt {ENV_PATH}")

CAPITAL_API_BASE = os.getenv("CAPITAL_API_BASE")
CAPITAL_API_KEY = os.getenv("CAPITAL_API_KEY")
CAPITAL_USERNAME = os.getenv("CAPITAL_USERNAME")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD")

if not all([CAPITAL_API_BASE, CAPITAL_API_KEY, CAPITAL_USERNAME, CAPITAL_PASSWORD]):
    raise Exception("Missing CAPITAL_* envs (BASE, KEY, USERNAME, PASSWORD)")


class CapitalError(Exception):
    pass


class CapitalClient:
    def __init__(self):
        self.base = CAPITAL_API_BASE
        self.key = CAPITAL_API_KEY
        self.username = CAPITAL_USERNAME
        self.password = CAPITAL_PASSWORD
        self.session = requests.Session()
        self.cst = None
        self.xst = None

    # -----------------------------------------------------------
    def login(self):
        """Kirjautuu ja tallentaa tokenit"""
        url = f"{self.base}/api/v1/session"
        headers = {"X-CAP-API-KEY": self.key, "Content-Type": "application/json"}
        data = {"identifier": self.username, "password": self.password}
        r = self.session.post(url, headers=headers, data=json.dumps(data))
        if r.status_code != 200:
            print(f"[login fail] {r.status_code}: {r.text}")
            return False
        self.cst = r.headers.get("CST")
        self.xst = r.headers.get("X-SECURITY-TOKEN")
        print(f"[login ok] user={self.username} CST={self.cst[:8]}...")
        return True

    # -----------------------------------------------------------
    def _auth_headers(self):
        h = {
            "X-CAP-API-KEY": self.key,
            "Content-Type": "application/json",
        }
        if self.cst:
            h["CST"] = self.cst
        if self.xst:
            h["X-SECURITY-TOKEN"] = self.xst
        return h

    # -----------------------------------------------------------
    def request(self, method, endpoint, params=None):
        url = f"{self.base}{endpoint}" if endpoint.startswith("/api") else f"{self.base}/api{endpoint}"
        headers = self._auth_headers()
        r = self.session.get(url, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            raise CapitalError(f"HTTP {r.status_code}: {r.text}")
        return r.json()

    # -----------------------------------------------------------
    def get_price_history(self, epic: str, resolution: str = "HOUR", limit: int = 10):
        """Hakee hinnat /api/v3/prices/{epic}?resolution=HOUR&max=10"""
        endpoint = f"/api/v3/prices/{epic}"
        params = {"resolution": resolution, "max": limit}
        data = self.request("GET", endpoint, params=params)
        if not data or "prices" not in data:
            return []
        candles = []
        for c in data["prices"]:
            candles.append({
                "time": c.get("snapshotTimeUTC"),
                "open": c.get("openPrice", {}).get("bid"),
                "high": c.get("highPrice", {}).get("bid"),
                "low": c.get("lowPrice", {}).get("bid"),
                "close": c.get("closePrice", {}).get("bid"),
                "volume": c.get("lastTradedVolume")
            })
        return candles
