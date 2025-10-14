#!/usr/bin/env python3
from __future__ import annotations
import os, time, json
from typing import Dict, Any, List, Optional, Tuple
import requests
import pandas as pd

# Capital.com LIVE base, esimerkki: https://api-capital.backend-capital.com
CAPITAL_API_BASE = os.getenv("CAPITAL_API_BASE", "").rstrip("/")
CAPITAL_API_KEY  = os.getenv("CAPITAL_API_KEY", "")
CAPITAL_USERNAME = os.getenv("CAPITAL_USERNAME", "")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD", "")

# Yleiset resoluutiot; mapataan 15m/1h/4h -> Capital-tyyli
RES_MAP = {
    "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
    "1h": "H1", "4h": "H4",
    "1d": "D1", "1w": "W1"
}

class CapitalError(RuntimeError):
    pass

class CapitalClient:
    def __init__(self,
                 base_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 timeout: int = 20):
        self.base = (base_url or CAPITAL_API_BASE).rstrip("/")
        self.api_key = api_key or CAPITAL_API_KEY
        self.username = username or CAPITAL_USERNAME
        self.password = password or CAPITAL_PASSWORD
        self.timeout = timeout
        self.session = requests.Session()
        self.cst = None
        self.sec = None

        if not self.base or not self.api_key or not self.username or not self.password:
            raise CapitalError("Missing CAPITAL_API_* envs (BASE, KEY, USERNAME, PASSWORD)")

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "X-CAP-API-KEY": self.api_key,
        }
        if self.cst: h["CST"] = self.cst
        if self.sec: h["X-SECURITY-TOKEN"] = self.sec
        if extra: h.update(extra)
        return h

    def login(self) -> None:
        """
        Luo istunto: Postataan tunnukset ja API-key.
        Header-vastauksesta tallennetaan CST ja X-SECURITY-TOKEN.
        Yritetään kahta polkua: /session ja /api/v1/session.
        """
        body = {
            "identifier": self.username,
            "password": self.password,
            "encryptedPassword": False
        }
        errs: List[str] = []
        for path in ("/session", "/api/v1/session"):
            url = f"{self.base}{path}"
            try:
                r = self.session.post(url, headers=self._headers(), json=body, timeout=self.timeout)
                if r.status_code // 100 == 2:
                    self.cst = r.headers.get("CST")
                    self.sec = r.headers.get("X-SECURITY-TOKEN")
                    if not self.cst or not self.sec:
                        raise CapitalError(f"Login ok but missing tokens CST/X-SECURITY-TOKEN (status={r.status_code})")
                    return
                else:
                    errs.append(f"{path}: {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                errs.append(f"{path}: {e}")
        raise CapitalError("Login failed: " + " | ".join(errs))

    def whoami(self) -> Dict[str, Any]:
        # Yritetään pari reittiä, jos dokumentaatio vaihtelee
        for path in ("/users/current", "/api/v1/users/current"):
            url = f"{self.base}{path}"
            r = self.session.get(url, headers=self._headers(), timeout=self.timeout)
            if r.status_code // 100 == 2:
                try: return r.json()
                except Exception: return {"raw": r.text}
        return {}

    def _map_resolution(self, tf: str) -> str:
        t = str(tf).lower().strip()
        if t in RES_MAP: return RES_MAP[t]
        # yritä arvata: 15m -> M15, 1h -> H1
        if t.endswith("m"):
            return f"M{t[:-1]}"
        if t.endswith("h"):
            return f"H{t[:-1]}"
        if t.endswith("d"):
            return f"D{t[:-1]}"
        return t.upper()

    def candles(self, symbol: str,
                resolution: str,
                from_iso: Optional[str] = None,
                to_iso: Optional[str] = None,
                limit: Optional[int] = None) -> pd.DataFrame:
        """
        Hakee OHLCV-kynttilät. Yritetään useampaa virallista reittiä:
        - /history/candles?symbol=...&resolution=...&from=...&to=...&max=...
        - /api/v1/history/candles (fallback)
        - /api/v1/candles/{symbol}/{resolution}?from=...&to=...&max=...
        Palauttaa DataFramen sarakkeilla: time, open, high, low, close, volume (UTC).
        """
        res = self._map_resolution(resolution)
        params: Dict[str, Any] = {"symbol": symbol, "resolution": res}
        if from_iso: params["from"] = from_iso
        if to_iso:   params["to"] = to_iso
        if limit:    params["max"] = int(limit)

        paths = [
            "/history/candles",
            "/api/v1/history/candles",
        ]
        errors: List[str] = []

        # Yritä kyselyparametreilla
        for path in paths:
            url = f"{self.base}{path}"
            try:
                r = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
                if r.status_code // 100 == 2:
                    return self._parse_candles_json(r.json())
                else:
                    errors.append(f"{path}: {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                errors.append(f"{path}: {e}")

        # Fallback: polku muodossa /api/v1/candles/<symbol>/<resolution>
        alt_paths = [
            f"/api/v1/candles/{symbol}/{res}",
            f"/candles/{symbol}/{res}",
        ]
        qp = {}
        if from_iso: qp["from"] = from_iso
        if to_iso:   qp["to"] = to_iso
        if limit:    qp["max"] = int(limit)

        for path in alt_paths:
            url = f"{self.base}{path}"
            try:
                r = self.session.get(url, headers=self._headers(), params=qp, timeout=self.timeout)
                if r.status_code // 100 == 2:
                    return self._parse_candles_json(r.json())
                else:
                    errors.append(f"{path}: {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                errors.append(f"{path}: {e}")

        raise CapitalError("candles failed: " + " | ".join(errors))

    def _parse_candles_json(self, payload: Any) -> pd.DataFrame:
        """
        Tuetaan kahta tyyppistä rakennetta:
        - {"candles":[{"date":"2025-10-13T10:00:00Z","open":...,"high":...,"low":...,"close":...,"volume":...}, ...]}
        - {"data":[[ts_ms,open,high,low,close,volume], ...]} tms.
        """
        if payload is None:
            return pd.DataFrame()

        if isinstance(payload, dict):
            if "candles" in payload and isinstance(payload["candles"], list):
                rows = payload["candles"]
                df = pd.DataFrame(rows)
                # normalisoi sarakkeet
                colmap = {
                    "date": "time", "timestamp": "time", "ts": "time",
                    "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
                }
                df = df.rename(columns=colmap)
                if "time" in df.columns:
                    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
                elif "epoch" in df.columns:
                    df["time"] = pd.to_datetime(df["epoch"], unit="ms", utc=True, errors="coerce")
                keep = ["time","open","high","low","close","volume"]
                for k in keep:
                    if k not in df.columns:
                        df[k] = None
                df = df[keep].dropna(subset=["time"]).reset_index(drop=True)
                return df

            if "data" in payload and isinstance(payload["data"], list):
                # odotetaan listaa listoja: [ts_ms, o, h, l, c, v]
                import numpy as np
                arr = payload["data"]
                if len(arr) == 0:
                    return pd.DataFrame()
                cols = ["ts","open","high","low","close","volume"]
                df = pd.DataFrame(arr, columns=cols[:len(arr[0])])
                if "ts" in df.columns:
                    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True, errors="coerce")
                else:
                    df["time"] = pd.NaT
                keep = ["time","open","high","low","close","volume"]
                for k in keep:
                    if k not in df.columns:
                        df[k] = None
                df = df[keep].dropna(subset=["time"]).reset_index(drop=True)
                return df

        # tuntematon muoto – yritetään DataFrameksi
        try:
            df = pd.json_normalize(payload)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
            return df
        except Exception:
            pass
        return pd.DataFrame()
