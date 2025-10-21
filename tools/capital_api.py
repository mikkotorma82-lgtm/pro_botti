#!/usr/bin/env python3
from __future__ import annotations
import os, time
from typing import Dict, Any, List, Optional
import requests
import pandas as pd

CAPITAL_API_BASE = os.getenv("CAPITAL_API_BASE", "").rstrip("/")
CAPITAL_API_KEY  = os.getenv("CAPITAL_API_KEY", "")
CAPITAL_USERNAME = os.getenv("CAPITAL_USERNAME", "")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD", "")
CAPITAL_TOTP     = os.getenv("CAPITAL_TOTP", "")  # ei käytetä ellei asetettu

RES_MAP = {"1m":"M1","5m":"M5","15m":"M15","30m":"M30","1h":"H1","4h":"H4","1d":"D1","1w":"W1"}

class CapitalError(RuntimeError): pass

class CapitalClient:
    def __init__(self, base_url=None, api_key=None, username=None, password=None, timeout=20):
        self.base = (base_url or CAPITAL_API_BASE).rstrip("/")
        self.api_key = api_key or CAPITAL_API_KEY
        self.username = username or CAPITAL_USERNAME
        self.password = password or CAPITAL_PASSWORD
        self.timeout = timeout
        self.session = requests.Session()
        # ystävällinen UA, jotkut WAF:it nirsoilevat
        self.session.headers.update({"User-Agent": "pro-botti/1.0 (+https://github.com/mikkotorma82-lgtm/pro_botti)"})
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
        Minimi-login: ei TOTP:ia, ellei CAPITAL_TOTP ole asetettu.
        Ensisijaisesti /api/v1/session; fallback /session.
        """
        body = {"identifier": self.username, "password": self.password, "encryptedPassword": False}
        headers: Dict[str,str] = {}
        # TOTP vain jos erikseen annettu (ei oletuksena vaadita)
        if CAPITAL_TOTP:
            headers["X-TOTP"] = CAPITAL_TOTP
            body["totp"] = CAPITAL_TOTP

        errs: List[str] = []
        paths = ["/api/v1/session", "/session"]
        for i, path in enumerate(paths):
            url = f"{self.base}{path}"
            try:
                r = self.session.post(url, headers=self._headers(headers), json=body, timeout=self.timeout)
                if r.status_code == 429:
                    # liian monta yritystä – odota ja yritä fallbackkia/uutta kierrosta
                    time.sleep(65)
                    continue
                if r.status_code // 100 == 2:
                    self.cst = r.headers.get("CST")
                    self.sec = r.headers.get("X-SECURITY-TOKEN")
                    if not self.cst or not self.sec:
                        raise CapitalError(f"Login ok but missing CST/X-SECURITY-TOKEN (status={r.status_code})")
                    return
                errs.append(f"{path}: {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                errs.append(f"{path}: {e}")
            # pikku tauko ennen seuraavaa polkua
            time.sleep(1.2)
        raise CapitalError("Login failed: " + " | ".join(errs))

    def _map_resolution(self, tf: str) -> str:
        t = str(tf).lower().strip()
        if t in RES_MAP: return RES_MAP[t]
        if t.endswith("m"): return f"M{t[:-1]}"
        if t.endswith("h"): return f"H{t[:-1]}"
        if t.endswith("d"): return f"D{t[:-1]}"
        return t.upper()

    def candles(self, symbol: str, resolution: str, from_iso: str | None = None, to_iso: str | None = None, limit: int | None = None) -> pd.DataFrame:
        res = self._map_resolution(resolution)
        params: Dict[str, Any] = {"symbol": symbol, "resolution": res}
        if from_iso: params["from"] = from_iso
        if to_iso:   params["to"] = to_iso
        if limit:    params["max"] = int(limit)

        # virallinen endpoint
        paths = ["/api/v1/history/candles", "/history/candles"]
        errors: List[str] = []
        for path in paths:
            url = f"{self.base}{path}"
            try:
                r = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
                if r.status_code // 100 == 2:
                    return self._parse_candles_json(r.json())
                errors.append(f"{path}: {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                errors.append(f"{path}: {e}")
            time.sleep(0.5)

        # fallback: polkumuodot
        alt_paths = [f"/api/v1/candles/{symbol}/{res}", f"/candles/{symbol}/{res}"]
        qp: Dict[str, Any] = {}
        if from_iso: qp["from"] = from_iso
        if to_iso:   qp["to"] = to_iso
        if limit:    qp["max"] = int(limit)
        for path in alt_paths:
            url = f"{self.base}{path}"
            try:
                r = self.session.get(url, headers=self._headers(), params=qp, timeout=self.timeout)
                if r.status_code // 100 == 2:
                    return self._parse_candles_json(r.json())
                errors.append(f"{path}: {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                errors.append(f"{path}: {e}")
            time.sleep(0.5)

        raise CapitalError("candles failed: " + " | ".join(errors))

    def _parse_candles_json(self, payload: Any) -> pd.DataFrame:
        if payload is None: return pd.DataFrame()
        if isinstance(payload, dict):
            if isinstance(payload.get("candles"), list):
                df = pd.DataFrame(payload["candles"]).rename(columns={
                    "date":"time","timestamp":"time","ts":"time",
                    "o":"open","h":"high","l":"low","c":"close","v":"volume"
                })
                if "time" in df:
                    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
                for k in ("open","high","low","close","volume"):
                    if k not in df: df[k] = None
                return df[["time","open","high","low","close","volume"]].dropna(subset=["time"]).reset_index(drop=True)

            if isinstance(payload.get("data"), list):
                arr = payload["data"]
                if not arr: return pd.DataFrame()
                cols = ["ts","open","high","low","close","volume"][:len(arr[0])]
                df = pd.DataFrame(arr, columns=cols)
                if "ts" in df:
                    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True, errors="coerce")
                for k in ("open","high","low","close","volume"):
                    if k not in df: df[k] = None
                return df[["time","open","high","low","close","volume"]].dropna(subset=["time"]).reset_index(drop=True)

        try:
            df = pd.json_normalize(payload)
            if "time" in df:
                df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
            return df
        except Exception:
            return pd.DataFrame()
