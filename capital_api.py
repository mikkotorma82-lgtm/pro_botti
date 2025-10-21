from __future__ import annotations
import json
import logging
from pathlib import Path
# === AUTO-INSERT: SIZE CLAMP ===
import json as _json
from pathlib import Path as _P
def _load_specs():
    try:
        d=_json.load(open("data/broker_specs.json"))
        return {r["symbol"]: r for r in d if isinstance(r,dict) and "error" not in r}
    except Exception:
        return {}
def clamp_size(symbol: str, qty: float) -> float:
    s=_load_specs().get(symbol) or {}
    try:
        mn=float(s.get("min_size",0) or 0)
        st=float(s.get("step",1) or 1)
    except Exception:
        mn,st=0.0,1.0
    q=float(qty)
    if mn and q<mn: q=mn
    if st: q=round(q/st)*st
    if mn: q=max(q,mn)
    return float(q)
# === /AUTO-INSERT ===

from typing import Dict, Optional
import requests

log = logging.getLogger(__name__)

class CapitalError(RuntimeError):
    pass

class CapitalClient:
    BASES = {
        "demo": "https://demo-api-capital.backend-capital.com",
        "live": "https://api-capital.backend-capital.com",
    }

    def create_position(
        self,
        direction: str = None,
        epic_or_symbol: str | None = None,
        size: float | None = None,
        currency: str | None = None,
        **kwargs,
    ) -> Dict:
        """
        Yhtenäistetty create_position:
          - hyväksyy epic/symbol/epic_or_symbol
          - sallii extra kwargsit
          - palauttaa AINA dictin eikä nosta TypeErroria turhasta
        """
        # suunta
        direction = (direction or kwargs.pop("direction", None) or "").upper()
        if direction not in ("BUY", "SELL"):
            return { "ok": False, "error": "invalid direction", "direction": direction }
    
        # epic/symbol
        epic  = kwargs.pop("epic", None)
        symbol = kwargs.pop("symbol", None)
        key = epic or symbol or epic_or_symbol or kwargs.get("instrument")
        if not key:
            return { "ok": False, "error": "missing epic/symbol" }
    
        epic_resolved = self._resolve_epic(key)
    
        # size (klampataan broker_specs.jsonin mukaan jos löytyy)
        if size is None:
            size = kwargs.pop("size", None)
        try:
            size = float(size) if size is not None else 1.0
        except Exception:
            return { "ok": False, "error": "invalid size" }
    
        try:
            size = clamp_size(str(key), size)
        except Exception:
            pass
    
        currency = currency or kwargs.pop("currency", None) or kwargs.pop("currencyCode", None)
    
        payload = {
            "epic": epic_resolved,
            "direction": direction,
            "size": size,
            "orderType": "MARKET",
            "guaranteedStop": False,
        }
        if currency:
            payload["currency"] = currency
        # salli muut vapaat kentät
        for k, v in list(kwargs.items()):
            if k not in payload:
                payload[k] = v
    
        # kutsu mahdollisia alempia toteutuksia
        low = None
        for name in ("_create_position","create_position_raw","create_position_inner","_post_position"):
            low = getattr(self, name, None)
            if callable(low):
                break
    
        resp = None
        try:
            if callable(low):
                try:
                    resp = low(payload)
                except TypeError:
                    resp = low(**payload)
            else:
                # suora API-kutsu
                url = self._url("/api/v1/positions")
                r = self.session.post(url, data=json.dumps(payload))
                if r.status_code // 100 != 2:
                    return { "ok": False, "status_code": r.status_code, "text": r.text, "payload": payload }
                try:
                    resp = r.json()
                except Exception:
                    resp = {}
        except Exception as e:
            return { "ok": False, "error": repr(e), "payload": payload, "raw": resp }
    
        deal_ref = resp.get("dealReference") if isinstance(resp, dict) else None
        return { "ok": True, "dealReference": deal_ref, "payload": payload, "raw": resp }

    def __init__(self, api_key: str, identifier: str, password: str, env: str = "demo"):
        self.api_key = api_key
        self.identifier = identifier
        self.password = password
        self.env = env.lower().strip()
        self.base = self.BASES.get(self.env, self.BASES["demo"])
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json; charset=UTF-8",
            "Content-Type": "application/json; charset=UTF-8",
            "X-CAP-API-KEY": self.api_key,
        })
        self._cst = None
        self._sec = None

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base + path

    def login(self):
        payload = {"identifier": self.identifier, "password": self.password}
        r = self.session.post(self._url("/api/v1/session"), data=json.dumps(payload))
        if r.status_code // 100 != 2:
            raise CapitalError(f"login failed {r.status_code}: {r.text}")
        cst = r.headers.get("CST") or r.headers.get("cst")
        sec = r.headers.get("X-SECURITY-TOKEN") or r.headers.get("x-security-token")
        if not cst or not sec:
            raise CapitalError("login ok mutta puuttuu CST/X-SECURITY-TOKEN")
        self._cst, self._sec = cst, sec
        self.session.headers.update({"CST": cst, "X-SECURITY-TOKEN": sec})
        log.info("Capital login OK (env=%s)", self.env)
        return True

    def _resolve_epic(self, epic_or_symbol: str) -> str:
        try:
            aliases_path = Path(__file__).resolve().parent / "config" / "aliases.json"
            if aliases_path.exists():
                aliases: Dict[str, str] = json.loads(aliases_path.read_text())
                return aliases.get(epic_or_symbol, epic_or_symbol)
        except Exception:
            pass
        return epic_or_symbol

    # daemon tarvitsee tätä nimeä
    def resolve_epic(self, symbol: str) -> str:
        return self._resolve_epic(symbol)

    def account_info(self) -> Dict:
        url = self._url("/api/v1/accounts")
        r = self.session.get(url)
        if r.status_code // 100 != 2:
            raise CapitalError(f"account_info {r.status_code}: {r.text}")
        try:
            return r.json()
        except Exception:
            return {}

    def list_open_positions(self) -> Dict:
        url = self._url("/api/v1/positions")
        r = self.session.get(url)
        if r.status_code // 100 != 2:
            raise CapitalError(f"positions {r.status_code}: {r.text}")
        try:
            data = r.json()
        except Exception as e:
            raise CapitalError(f"positions invalid json: {e}")
        if isinstance(data, dict) and "positions" in data:
            return data
        if isinstance(data, list):
            return {"positions": data}
        return {"positions": []}

    def create_position(
        self,
        direction: str = None,
        epic_or_symbol: Optional[str] = None,
        size: Optional[float] = None,
        currency: Optional[str] = None,
        **kwargs,
    ) -> Dict:
#         """
#         Hyväksyy kutsut muodossa:
#           - create_position(direction="BUY", epic="IX.D.US500.CFD.IP", size=(lambda _s: (__import__("logging").getLogger(__name__).info(f"[SIZECHK] {symbol} used={_s}"), _s))(clamp_size(symbol, 1)))
#           - create_position(direction="SELL", symbol="BTCUSD", size=clamp_size(symbol, 0.5), currency="USD")
#           - create_position("BUY", "ETHUSD", 1.0)
#         Sekä alias 'currencyCode'.
#         """
        # Poimi mahdolliset nimiparametrit, joita daemon käyttää
        if direction is None:
            direction = kwargs.get("direction")
        if size is None:
            size = clamp_size(symbol, kwargs.get("size"))
        epic = kwargs.get("epic")
        symbol = kwargs.get("symbol")

        # Yhteensopivuus: jos toinen positionaali annettu "epic_or_symbol"
        # ja nimettyjä ei ollut, käytetään sitä
        if not epic and not symbol and epic_or_symbol:
            symbol = epic_or_symbol

        # Valitse EPIC: alias-resoluutio symbolille
        key = epic or symbol
        if not key:
            raise CapitalError("create_position: epic/symbol puuttuu")
        epic_resolved = self._resolve_epic(key)

        # Valuutta-aliakset
        if not currency:
            currency = kwargs.get("currencyCode") or kwargs.get("currency")

        # Muut optiot, jos joskus välitetään:
        order_type = kwargs.get("orderType", "MARKET")
        guaranteed_stop = bool(kwargs.get("guaranteedStop", False))
        stop_distance = kwargs.get("stopDistance")
        limit_distance = kwargs.get("limitDistance")

        payload = {
            "epic": epic_resolved,
            "direction": (direction or "").upper(),
            "size": float(size),
            "orderType": order_type,
            "guaranteedStop": guaranteed_stop,
        }
        if currency:
            payload["currency"] = currency
        if stop_distance is not None:
            payload["stopDistance"] = float(stop_distance)
        if limit_distance is not None:
            payload["limitDistance"] = float(limit_distance)

        url = self._url("/api/v1/positions")
        r = self.session.post(url, data=json.dumps(payload))
        if r.status_code // 100 != 2:
            return {
                "error": True,
                "status_code": r.status_code,
                "text": r.text,
                "payload": payload,
            }
        try:
            return r.json()
        except Exception:
            return {"ok": True, "payload": payload}

        # Hyväksyy kutsut muodossa:
        #   - create_position(direction="BUY", epic="IX.D.US500.CFD.IP", size=clamp_size(symbol, 1))
        #   - create_position(direction="SELL", symbol="BTCUSD", size=clamp_size(symbol, 0.5), currency="USD")
        #   - create_position("BUY", "ETHUSD", 1.0)
        #   Sekä alias 'currencyCode'.
        # Poimi mahdolliset nimiparametrit, joita daemon käyttää
        if direction is None:
            direction = kwargs.get("direction")
        if size is None:
            size = clamp_size(symbol, kwargs.get("size"))
        epic = kwargs.get("epic")
        symbol = kwargs.get("symbol")

        # Yhteensopivuus: jos toinen positionaali annettu "epic_or_symbol"
        # ja nimettyjä ei ollut, käytetään sitä
        if not epic and not symbol and epic_or_symbol:
            symbol = epic_or_symbol

        # Valitse EPIC: alias-resoluutio symbolille
        key = epic or symbol
        if not key:
            raise CapitalError("create_position: epic/symbol puuttuu")
        epic_resolved = self._resolve_epic(key)

        # Valuutta-aliakset
        if not currency:
            currency = kwargs.get("currencyCode") or kwargs.get("currency")

        # Muut optiot, jos joskus välitetään:
        order_type = kwargs.get("orderType", "MARKET")
        guaranteed_stop = bool(kwargs.get("guaranteedStop", False))
        stop_distance = kwargs.get("stopDistance")
        limit_distance = kwargs.get("limitDistance")

        payload = {
            "epic": epic_resolved,
            "direction": (direction or "").upper(),
            "size": float(size),
            "orderType": order_type,
            "guaranteedStop": guaranteed_stop,
        }
        if currency:
            payload["currency"] = currency
        if stop_distance is not None:
            payload["stopDistance"] = float(stop_distance)
        if limit_distance is not None:
            payload["limitDistance"] = float(limit_distance)

        url = self._url("/api/v1/positions")
        r = self.session.post(url, data=json.dumps(payload))
        if r.status_code // 100 != 2:
            return {
                "error": True,
                "status_code": r.status_code,
                "text": r.text,
                "payload": payload,
            }
        try:
            return r.json()
        except Exception:
            return {"ok": True, "payload": payload}

        payload = {
            "epic": epic,
            "direction": direction.upper(),
            "size": float(size),
            "orderType": "MARKET",
            "guaranteedStop": False,
        }
        if currency:
            payload["currency"] = currency
        url = self._url("/api/v1/positions")
        r = self.session.post(url, data=json.dumps(payload))
        if r.status_code // 100 != 2:
            return {"error": True, "status_code": r.status_code, "text": r.text, "payload": payload}
        try:
            return r.json()
        except Exception:
            return {"ok": True}

def create_position(
    self,
    direction: str = None,
    epic_or_symbol: Optional[str] = None,
    size: Optional[float] = None,
    currency: Optional[str] = None,
    **kwargs,
) -> Dict:
    """
    Yhtenäistetty create_position:
    - hyväksyy epic/symbol/epic_or_symbol
    - sallii extra kwargsit (ei räjähdä 'unexpected keyword argument')
    - palauttaa aina dictin, vaikka alempi kerros palauttaisi None
    """
    epic = kwargs.pop("epic", None) or kwargs.pop("symbol", None) or epic_or_symbol or kwargs.get("instrument")
    if not epic:
        raise ValueError("create_position: missing epic_or_symbol / epic / symbol")

    if direction not in ("BUY", "SELL"):
        raise ValueError("create_position: direction must be BUY or SELL")

    if size is None:
        size = kwargs.pop("size", None) or getattr(self, "size_default", None)
        if size is None:
            raise ValueError("create_position: missing size")

    payload = dict(direction=direction, epic=epic, size=size)
    if currency:
        payload["currency"] = currency
    for k, v in list(kwargs.items()):
        if k not in payload:
            payload[k] = v

    # Etsi low-level lähettäjä
    low = None
    for name in ("_create_position", "create_position_raw", "create_position_inner", "_post_position"):
        low = getattr(self, name, None)
        if callable(low):
            break

    resp = None
    try:
        if callable(low):
            # ensisijaisesti payload-dictillä
            try:
                resp = low(payload)
            except TypeError:
                # vaihtoehtoisesti parametreina
                resp = low(**payload)
        else:
            _post = getattr(self, "_post", None)
            if callable(_post):
                resp = _post("/positions", json=payload)
    except Exception as e:
        return {"ok": False, "error": repr(e), "payload": payload, "raw": resp}

    deal_ref = None
    if isinstance(resp, dict):
        deal_ref = resp.get("dealReference") or resp.get("deal_ref") or resp.get("reference")

    return {"ok": True, "dealReference": deal_ref, "payload": payload, "raw": resp}
