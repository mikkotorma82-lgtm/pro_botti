#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Capital.com API Client (final stable)
✅ Login kerran, token keep-alive automaattisesti
✅ Estää liialliset login-yritykset (min 10s väli)
✅ Käyttää environment-arvoja tai .env-tiedostoa automaattisesti
"""

import os, time, json, requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

class CapitalClient:
    def __init__(self):
        self.env = os.getenv("CAPITAL_ENV", "live").lower()
        self.api_key = os.getenv("CAPITAL_API_KEY")
        self.username = os.getenv("CAPITAL_USERNAME")
        self.password = os.getenv("CAPITAL_PASSWORD")
        self.base = (
            "https://api-capital.backend-capital.com"
            if self.env == "live"
            else "https://demo-api-capital.backend-capital.com"
        )
        self.session = requests.Session()
        self.session.headers.update({
            "X-CAP-API-KEY": self.api_key,
            "Content-Type": "application/json"
        })
        self.cst = None
        self.xst = None
        self.last_login = 0

    # -----------------------------------------------------
    def login(self) -> bool:
        """Perform login with rate limit protection"""
        if time.time() - self.last_login < 10:
            print("[login] Skipped (too frequent)")
            return True
        payload = {"identifier": self.username, "password": self.password}
        url = self.base.rstrip("/") + "/api/v1/session"
        print(f"[debug] POST {url} payload={payload}")
        try:
            r = self.session.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                self.cst = r.headers.get("CST")
                self.xst = r.headers.get("X-SECURITY-TOKEN")
                self.session.headers.update({
                    "CST": self.cst,
                    "X-SECURITY-TOKEN": self.xst
                })
                self.last_login = time.time()
                print(f"[login] OK {self.env.upper()} CST={self.cst[:8]}...")
                return True
            else:
                print(f"[login] FAIL {r.status_code} {r.text}")
                return False
        except Exception as e:
            print(f"[login] Exception: {e}")
            return False

    # -----------------------------------------------------
    def keep_alive(self):
        """Ping or relog if needed"""
        if not self.cst or not self.xst:
            self.login()
            return
        url = self.base.rstrip("/") + "/api/v1/ping"
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 401:
                print("[keep_alive] session expired, re-login")
                self.login()
        except Exception as e:
            print(f"[keep_alive] exception: {e}")
            self.login()

    # -----------------------------------------------------
    def get_account_info(self):
        self.keep_alive()
        url = self.base.rstrip("/") + "/api/v1/accounts"
        r = self.session.get(url)
        return r.json() if r.status_code == 200 else {"error": r.text}

    # -----------------------------------------------------
    def place_market_order(self, epic: str, side: str, size: float,
                           stop: float = None, limit: float = None):
        self.keep_alive()
        url = self.base.rstrip("/") + "/api/v1/positions"
        payload = {
            "epic": epic,
            "direction": "BUY" if side.upper().startswith("L") else "SELL",
            "size": size
        }
        if stop is not None: payload["stopLevel"] = stop
        if limit is not None: payload["limitLevel"] = limit
        try:
            r = self.session.post(url, json=payload, timeout=20)
            if r.status_code // 100 == 2:
                print(f"[order] OK {epic} {side} size={size}")
                return {"ok": True, "resp": r.json()}
            else:
                print(f"[order] FAIL {r.status_code} {r.text}")
                return {"ok": False, "resp": r.text}
        except Exception as e:
            print(f"[order] Exception: {e}")
            return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    c = CapitalClient()
    if c.login():
        print(json.dumps(c.get_account_info(), indent=2))
