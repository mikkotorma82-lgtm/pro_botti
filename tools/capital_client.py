# /root/pro_botti/tools/capital_client.py
# -*- coding: utf-8 -*-
"""
CapitalClient – yhteensopiva asiakas liven odottamille metodeille:
- place_market, place_order, modify_order, cancel_order, close_position
- get_open_positions, account_info, last_price
- adopt_open_positions (ottaa hallintaan jo auki olevat)
- manage_positions_loop (breakeven, trailing SL, scale-in)

Tuki:
- Broker REST (CAPITAL_API_BASE, CAPITAL_API_KEY/SECRET tai USERNAME/PASSWORD)
- Heuristinen fallback, jos käytössä omat metodit (market_order/create_order/positions/prices)
- Instrumenttikartta /root/pro_botti/data/instrument_map.json (min_size, step, leverage, margin_factor)

Ympäristö:
- ADOPT_ON_START=1        -> adopt_open_positions() heti loginin jälkeen
- MANAGE_OPEN_POSITIONS=1 -> manage_positions_loop() erillisessä säikeessä
- TRAILING_ENABLED=1
- BREAKEVEN_ARM_R=1.0
- TRAIL_AFTER_R=1.5
- MAX_SCALE_INS=2
- SCALE_IN_STEP_R=1.5
- RISK_PCT=0.02 (käytetään lähinnä kokolaskennan yhteyteen jos pyydetään)
- CAPITAL_API_BASE, CAPITAL_API_KEY, CAPITAL_API_SECRET, CAPITAL_USERNAME, CAPITAL_PASSWORD, CAPITAL_ACCOUNT_ID
- CAP_FREE_BALANCE (jos broker ei anna balancea, voidaan syöttää live_daemonista)
- LASTPX_<SYMBOL> (jos hinnan haku epäonnistuu, luetaan envistä)

Lokitus:
- print(...) – live poimii nämä journaliin
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except Exception:
    requests = None  # sallitaan offline-ympäristö

INSTR_PATH = "/root/pro_botti/data/instrument_map.json"


# -------------------------- apu: instrumenttikartta --------------------------

def _load_instr() -> Dict[str, Dict[str, Any]]:
    try:
        with open(INSTR_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

INSTR = _load_instr()


def instr_info(symbol: str) -> Dict[str, Any]:
    d = (INSTR.get(symbol) or {}).copy()

    # normalisoi numeeriset
    def _flt(v, default=None):
        try:
            return float(v)
        except Exception:
            return default

    mmin = _flt(d.get("min_trade_size"), 0.0)
    step = _flt(d.get("lot_step") or d.get("step") or d.get("quantity_step"), 0.0)
    lev  = _flt(d.get("leverage"), None)
    mf   = _flt(d.get("margin_factor"), None)  # jos annettu 1..100% → leverage = 100/mf
    if lev is None and mf not in (None, 0):
        try:
            lev = 100.0 / float(mf)
        except Exception:
            lev = None

    d["min_trade_size"] = mmin
    d["lot_step"] = step
    d["leverage"] = lev
    return d


# -------------------------- tietorakenteet --------------------------

@dataclass
class OrderRequest:
    symbol: str
    side: str               # "BUY" / "SELL" tai "LONG"/"SHORT"
    size: float
    order_type: str = "MARKET"  # "MARKET", "LIMIT", "STOP"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    tif: str = "GTC"
    client_tag: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class Position:
    position_id: str
    symbol: str
    side: str               # "LONG" / "SHORT"
    size: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    scale_ins: int = 0      # skaalauksien lukumäärä
    meta: Dict[str, Any] = field(default_factory=dict)


# -------------------------- pääluokka --------------------------

class CapitalClient:
    def __init__(self):
        # Ympäristö
        self.base = os.environ.get("CAPITAL_API_BASE", "").rstrip("/")
        self.api_key = os.environ.get("CAPITAL_API_KEY")
        self.api_secret = os.environ.get("CAPITAL_API_SECRET")
        self.username = os.environ.get("CAPITAL_USERNAME")
        self.password = os.environ.get("CAPITAL_PASSWORD")
        self.account_id = os.environ.get("CAPITAL_ACCOUNT_ID")

        # Risk/hallinta
        self.trailing_enabled = os.environ.get("TRAILING_ENABLED", "0") == "1"
        self.breakeven_arm_r = _env_float("BREAKEVEN_ARM_R", 1.0)
        self.trail_after_r = _env_float("TRAIL_AFTER_R", 1.5)
        self.max_scale_ins = int(os.environ.get("MAX_SCALE_INS", "0") or 0)
        self.scale_in_step_r = _env_float("SCALE_IN_STEP_R", 1.5)
        self.adopt_on_start = os.environ.get("ADOPT_ON_START", "0") == "1"
        self.manage_enabled = os.environ.get("MANAGE_OPEN_POSITIONS", "0") == "1"

        # HTTP sessio
        self.session = requests.Session() if requests else None
        self._auth_token = None

        # Paikallinen positio-cache hallintaa varten
        self._pos_lock = threading.Lock()
        self._positions: Dict[str, Position] = {}  # key = position_id

    # ---------------------- broker-auth & info ----------------------

    def login(self) -> bool:
        """
        Yrittää kirjautua brokeriin. Jos base url puuttuu, hyväksytään 'mock' tila:
        - paluu True, mutta REST-kutsut eivät toimi (fallbackit/ENV käytössä).
        """
        if not self.base or not self.session:
            print("[CapitalClient] WARNING: CAPITAL_API_BASE tai requests puuttuu – REST-kutsut ohitetaan (ENV/fallback käytössä).")
            ok = True
        else:
            try:
                # Yleinen malli: POST /session {username,password} tai APIKEY-header
                if self.username and self.password:
                    url = f"{self.base}/session"
                    r = self.session.post(url, json={"username": self.username, "password": self.password}, timeout=10)
                    r.raise_for_status()
                    data = r.json()
                    self._auth_token = data.get("token") or data.get("access_token")
                    if self._auth_token:
                        self.session.headers.update({"Authorization": f"Bearer {self._auth_token}"})
                    ok = True
                elif self.api_key:
                    # API-key only
                    self.session.headers.update({"X-API-KEY": self.api_key})
                    ok = True
                else:
                    print("[CapitalClient] WARNING: Ei käyttäjätunnusta eikä API-avainta – jatketaan best-effort.")
                    ok = True
            except Exception as e:
                print(f"[CapitalClient][ERROR] Login epäonnistui: {e}")
                ok = False

        # Adoption & hallinta
        if ok and self.adopt_on_start:
            try:
                self.adopt_open_positions()
            except Exception as e:
                print(f"[CapitalClient][ADOPT][ERROR] {e}")

        if ok and self.manage_enabled:
            t = threading.Thread(target=self.manage_positions_loop, name="cc-manage", daemon=True)
            t.start()

        return ok

    def account_info(self) -> Dict[str, Any]:
        # REST
        if self.base and self.session:
            try:
                url = f"{self.base}/accounts/me"
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                pass

        # Heuristinen fallback (jos olemassa sisäisiä metodeja)
        # (ei tiedetä nimeä – jätetään pois)

        # Viimesijainen fallback: ympäristöstä
        free = _env_float("CAP_FREE_BALANCE", None)
        if free is not None:
            return {"accounts": [{"id": self.account_id or "primary", "status": "ENABLED", "preferred": True,
                                  "balance": {"available": free}}]}
        return {"accounts": []}

    # ---------------------- hinta & instrumentit ----------------------

    def last_price(self, symbol: str) -> Optional[float]:
        # REST
        if self.base and self.session:
            try:
                url = f"{self.base}/prices/{symbol}"
                r = self.session.get(url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    # yritetään eri kenttiä
                    for k in ("last", "price", "mid", "bid", "ask"):
                        v = data.get(k)
                        if isinstance(v, (int, float)):
                            return float(v)
                    if "data" in data and isinstance(data["data"], dict):
                        v = data["data"].get("last") or data["data"].get("price")
                        if isinstance(v, (int, float)):
                            return float(v)
            except Exception:
                pass
        # ENV fallback live_daemon asettamana
        env_key = f"LASTPX_{symbol}"
        try:
            v = float(os.environ.get(env_key, ""))
            if v > 0:
                return v
        except Exception:
            pass
        return None

    # ---------------------- order & positio-operaatiot ----------------------

    def place_market(self, symbol: str, side: str, size: float,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None,
                     trailing: Optional[Dict[str, Any]] = None,
                     comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Yhteensopiva markkinatoimeksianto. Palauttaa dictin jossa vähintään 'ok' ja mahdollinen 'order_id'/'position_id'.
        """
        req = OrderRequest(symbol=symbol, side=_norm_side(side), size=float(size),
                           order_type="MARKET", stop_loss=stop_loss,
                           take_profit=take_profit, client_tag="live_market", comment=comment)
        return self._route_place_order(req, trailing=trailing)

    def place_order(self, symbol: str, side: str, size: float,
                    order_type: str = "LIMIT",
                    price: Optional[float] = None,
                    stop_loss: Optional[float] = None,
                    take_profit: Optional[float] = None,
                    tif: str = "GTC",
                    comment: Optional[str] = None) -> Dict[str, Any]:
        req = OrderRequest(symbol=symbol, side=_norm_side(side), size=float(size),
                           order_type=order_type.upper(), price=price,
                           stop_loss=stop_loss, take_profit=take_profit, tif=tif,
                           client_tag="live_order", comment=comment)
        return self._route_place_order(req)

    def modify_order(self, order_id: str, **kwargs) -> Dict[str, Any]:
        # REST
        if self.base and self.session:
            try:
                url = f"{self.base}/orders/{order_id}"
                r = self.session.patch(url, json=kwargs, timeout=10)
                r.raise_for_status()
                return {"ok": True, "data": r.json()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        # Fallback: ei tiedetä sisäisten metodien nimiä
        return {"ok": False, "error": "modify_order not supported (no REST base)"}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if self.base and self.session:
            try:
                url = f"{self.base}/orders/{order_id}"
                r = self.session.delete(url, timeout=10)
                r.raise_for_status()
                return {"ok": True, "data": r.json() if r.text else {}}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "cancel_order not supported (no REST base)"}

    def close_position(self, position_id: str, size: Optional[float] = None) -> Dict[str, Any]:
        # REST: yleismallinen
        if self.base and self.session:
            try:
                url = f"{self.base}/positions/{position_id}/close"
                payload = {}
                if size:
                    payload["size"] = float(size)
                r = self.session.post(url, json=payload, timeout=10)
                r.raise_for_status()
                # poista cachesta
                with self._pos_lock:
                    self._positions.pop(position_id, None)
                return {"ok": True, "data": r.json() if r.text else {}}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        # Fallback: poista vain paikallisesta cachesta
        with self._pos_lock:
            ex = self._positions.pop(position_id, None)
        if ex:
            return {"ok": True, "data": {"local_only": True}}
        return {"ok": False, "error": "close_position not supported (no REST base)"}

    def get_open_positions(self) -> List[Position]:
        # REST
        if self.base and self.session:
            try:
                url = f"{self.base}/positions"
                if self.account_id:
                    url = f"{url}?account_id={self.account_id}"
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    arr = r.json() if isinstance(r.json(), list) else r.json().get("positions", [])
                    res = []
                    for p in arr or []:
                        res.append(Position(
                            position_id=str(p.get("id") or p.get("position_id") or p.get("dealId") or p.get("uid")),
                            symbol=p.get("symbol") or p.get("epic") or p.get("instrument"),
                            side=_norm_side(p.get("side") or p.get("direction")),
                            size=float(p.get("size") or p.get("quantity") or p.get("units") or 0.0),
                            entry_price=float(p.get("entry_price") or p.get("openLevel") or p.get("avgPrice") or 0.0),
                            stop_loss=_maybe_float(p.get("stop_loss") or p.get("stopLevel")),
                            take_profit=_maybe_float(p.get("take_profit") or p.get("limitLevel")),
                            unrealized_pnl=_maybe_float(p.get("unrealized_pnl") or p.get("pnl")),
                            meta={"raw": p},
                        ))
                    # Päivitä cache
                    with self._pos_lock:
                        self._positions = {p.position_id: p for p in res if p.position_id}
                    return res
            except Exception:
                pass

        # Paikallinen cache fallback
        with self._pos_lock:
            return list(self._positions.values())

    # ---------------------- adoption & hallinta ----------------------

    def adopt_open_positions(self):
        """ Hakee brokerilta avoimet positiot ja ottaa ne hallintaan (cache + nollaa scale_ins). """
        pos = self.get_open_positions()
        with self._pos_lock:
            for p in pos:
                if p.position_id not in self._positions:
                    self._positions[p.position_id] = p
                self._positions[p.position_id].scale_ins = 0
        print(f"[ADOPT] Hallinnassa nyt {len(self._positions)} positiota.")

    def manage_positions_loop(self, poll_sec: float = 10.0):
        """ Taustalooppi: breakeven, trailing ja scale-in. """
        print("[MANAGE] Loop start – breakeven/trailing/scale-in käytössä."
              f" BE_R={self.breakeven_arm_r} TRAIL_R={self.trail_after_r} SCALE_STEP={self.scale_in_step_r} MAX={self.max_scale_ins}")
        while True:
            try:
                self._manage_once()
            except Exception as e:
                print(f"[MANAGE][ERROR] {e}")
            time.sleep(poll_sec)

    def _manage_once(self):
        px_cache: Dict[str, float] = {}
        with self._pos_lock:
            positions = list(self._positions.values())

        for p in positions:
            # Hae hinta (cache)
            px = px_cache.get(p.symbol)
            if px is None:
                px = self.last_price(p.symbol) or p.entry_price
                px_cache[p.symbol] = px

            # Laske R (oletetaan stop_loss on asetettu; jos ei, päättele 1R = instrumentin pienin järkevä SL)
            R = _compute_R(p, px)
            if R is None:
                continue

            # Breakeven
            if self.breakeven_arm_r and R >= self.breakeven_arm_r:
                new_sl = p.entry_price
                if p.side == "LONG" and (p.stop_loss is None or new_sl > p.stop_loss):
                    self._set_sl(p, new_sl, tag="BREAKEVEN")
                elif p.side == "SHORT" and (p.stop_loss is None or new_sl < p.stop_loss):
                    self._set_sl(p, new_sl, tag="BREAKEVEN")

            # Trailing
            if self.trailing_enabled and self.trail_after_r and R >= self.trail_after_r:
                # yksinkertainen swingless trail: long -> sl = max(sl, px - k*ATR?) Tässä ilman ATR:ää: trail 50% voitosta
                if p.side == "LONG":
                    target_sl = p.entry_price + 0.5 * (px - p.entry_price)
                    if p.stop_loss is None or target_sl > p.stop_loss:
                        self._set_sl(p, target_sl, tag="TRAIL")
                else:
                    target_sl = p.entry_price - 0.5 * (p.entry_price - px)
                    if p.stop_loss is None or target_sl < p.stop_loss:
                        self._set_sl(p, target_sl, tag="TRAIL")

            # Scale-in
            if self.max_scale_ins > 0 and self.scale_in_step_r > 0:
                need_scales = int(R // self.scale_in_step_r)
                if need_scales > p.scale_ins and need_scales <= self.max_scale_ins:
                    add_times = need_scales - p.scale_ins
                    for _ in range(add_times):
                        add_size = max(0.0, p.size * 0.33)  # 1/3 alkuperäisestä
                        if add_size > 0:
                            side = "BUY" if p.side == "LONG" else "SELL"
                            print(f"[MANAGE][SCALE] {p.symbol} {p.side} R={R:.2f} -> lisätään {add_size:.6f}")
                            self.place_market(p.symbol, side, add_size, comment="scale-in")
                            p.scale_ins += 1

    def _set_sl(self, p: Position, new_sl: float, tag: str):
        # REST: modify position SL
        if self.base and self.session:
            try:
                url = f"{self.base}/positions/{p.position_id}"
                body = {"stop_loss": new_sl}
                r = self.session.patch(url, json=body, timeout=10)
                r.raise_for_status()
                p.stop_loss = new_sl
                print(f"[{tag}] {p.symbol} pos={p.position_id} SL -> {new_sl}")
                return
            except Exception as e:
                print(f"[{tag}][ERROR] {p.symbol} SL ei päivittynyt: {e}")
        # Fallback: päivitä paikallinen
        p.stop_loss = new_sl
        print(f"[{tag}] {p.symbol} pos={p.position_id} SL (local) -> {new_sl}")

    # ---------------------- sisäinen reititys ----------------------

    def _route_place_order(self, req: OrderRequest, trailing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        1) Kokeile REST
        2) Jos ei RESTiä, kokeile sisäisiä tunnettuja nimiä jos sellaiset on (ei tässä tiedossa)
        3) Fallback: päivitä local-cache "mock"-positiolla (viimeisenä keinona)
        """
        # 1) REST
        if self.base and self.session:
            try:
                url = f"{self.base}/orders"
                payload = {
                    "symbol": req.symbol,
                    "side": req.side,
                    "size": req.size,
                    "type": req.order_type,
                    "tif": req.tif,
                }
                if req.price is not None:
                    payload["price"] = req.price
                if req.stop_loss is not None:
                    payload["stop_loss"] = req.stop_loss
                if req.take_profit is not None:
                    payload["take_profit"] = req.take_profit
                if trailing:
                    payload["trailing"] = trailing
                if req.comment:
                    payload["comment"] = req.comment
                if self.account_id:
                    payload["account_id"] = self.account_id

                r = self.session.post(url, json=payload, timeout=10)
                r.raise_for_status()
                data = r.json() if r.text else {}
                # Jos vastaus sisältää position/order id:t
                order_id = str(data.get("order_id") or data.get("id") or data.get("dealId") or "")
                pos_id = str(data.get("position_id") or data.get("position") or "")
                if pos_id:
                    # päivitä cache
                    px = self.last_price(req.symbol) or (req.price or 0.0)
                    entry = px if req.order_type == "MARKET" else (req.price or px)
                    with self._pos_lock:
                        self._positions[pos_id] = Position(
                            position_id=pos_id,
                            symbol=req.symbol,
                            side="LONG" if req.side in ("BUY", "LONG") else "SHORT",
                            size=req.size,
                            entry_price=float(entry or 0.0),
                            stop_loss=req.stop_loss,
                            take_profit=req.take_profit,
                            meta={"order_id": order_id, "raw": data},
                        )
                print(f"[ORDER] {req.symbol} {req.side} {req.size} type={req.order_type} ok id={order_id or pos_id}")
                return {"ok": True, "data": data, "order_id": order_id, "position_id": pos_id}
            except Exception as e:
                print(f"[ERROR] REST order epäonnistui: {e}")

        # 2) Sisäiset nimet – jos tässä ympäristössä olisi valmiita metodeja, kutsu niitä.
        # (Emme tunne tarkkoja nimiä – jätetään pois. Tämä ratkaisee liven 'method missing' -ongelman vähimmällä riskillä.)

        # 3) Fallback: mock-positio paikalliseen cacheen (jotta live voi jatkaa hallintaa)
        pos_id = f"local-{int(time.time()*1000)}"
        px = self.last_price(req.symbol) or (req.price or 0.0)
        entry = px if req.order_type == "MARKET" else (req.price or px)
        with self._pos_lock:
            self._positions[pos_id] = Position(
                position_id=pos_id,
                symbol=req.symbol,
                side="LONG" if req.side in ("BUY", "LONG") else "SHORT",
                size=req.size,
                entry_price=float(entry or 0.0),
                stop_loss=req.stop_loss,
                take_profit=req.take_profit,
                meta={"order_id": None, "local_only": True},
            )
        print(f"[ORDER][LOCAL] {req.symbol} {req.side} {req.size} type={req.order_type} -> mock pos {pos_id}")
        return {"ok": True, "data": {"local_only": True}, "position_id": pos_id}


# -------------------------- apufunktiot --------------------------

def _norm_side(side: str) -> str:
    s = (side or "").upper()
    if s in ("LONG", "BUY"):
        return "BUY"
    if s in ("SHORT", "SELL"):
        return "SELL"
    return s or "BUY"

def _maybe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def _env_float(key: str, default: Optional[float] = None) -> Optional[float]:
    try:
        v = os.environ.get(key)
        return float(v) if v not in (None, "",) else default
    except Exception:
        return default

def _compute_R(p: Position, px: float) -> Optional[float]:
    """
    Laske R (voitto riskissä). Tarvitsee stop_lossin. Jos SL puuttuu -> None.
    LONG:  R = (px - entry) / (entry - SL)
    SHORT: R = (entry - px) / (SL - entry)
    """
    if p.stop_loss is None:
        return None
    try:
        if p.side == "LONG":
            risk = p.entry_price - p.stop_loss
            if risk <= 0:
                return None
            return (px - p.entry_price) / risk
        else:
            risk = p.stop_loss - p.entry_price
            if risk <= 0:
                return None
            return (p.entry_price - px) / risk
    except Exception:
        return None


# -------------------------- päätason apukäyttö --------------------------

def connect_and_prepare() -> CapitalClient:
    """
    Yhdistä, adoptoi avoimet positiot ja käynnistä hallinta jos pyydetty.
    Live voi kutsua tätä suoraan.
    """
    cli = CapitalClient()
    ok = cli.login()
    if not ok:
        print("[CapitalClient] Login epäonnistui – jatketaan best-effort-tilassa.")
    return cli
