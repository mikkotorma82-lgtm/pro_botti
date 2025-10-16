# /root/pro_botti/tools/capital_client.py
# -*- coding: utf-8 -*-
"""
CapitalClient – yhteensopiva asiakas liven odottamille metodeille:
- place_market, place_order, modify_order, cancel_order, close_position
- get_open_positions, account_info, last_price
- adopt_open_positions, manage_positions_loop

Tämä versio käyttää samaa sessio- ja loginpolkua kuin tools.capital_session:
- Login ja sessio: capital_rest_login() -> (requests.Session, base)
- API-päätepisteet: /api/v1/* (orders, positions, prices)
- Headerit ja tokenit linjassa capital_sessionin kanssa

Ympäristö:
- CAPITAL_API_BASE, CAPITAL_API_KEY, CAPITAL_USERNAME, CAPITAL_PASSWORD, CAPITAL_ACCOUNT_ID
- CAPITAL_ACCOUNT_TYPE (esim CFD; capital_session lisää headerin)
- ADOPT_ON_START=1, MANAGE_OPEN_POSITIONS=1 jne.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except Exception:
    requests = None  # pragma: no cover

from tools.capital_session import capital_rest_login, capital_market_search

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

    def _flt(v, default=None):
        try:
            return float(v)
        except Exception:
            return default

    mmin = _flt(d.get("min_trade_size"), 0.0)
    step = _flt(d.get("lot_step") or d.get("step") or d.get("quantity_step"), 0.0)
    lev  = _flt(d.get("leverage"), None)
    mf   = _flt(d.get("margin_factor"), None)
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
    side: str               # "BUY" / "SELL"
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
    scale_ins: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


# -------------------------- pääluokka --------------------------

class CapitalClient:
    def __init__(self):
        self.session: Optional["requests.Session"] = None
        self.base: str = ""
        self.account_id = os.environ.get("CAPITAL_ACCOUNT_ID")

        # Risk/hallinta
        self.trailing_enabled = os.environ.get("TRAILING_ENABLED", "0") == "1"
        self.breakeven_arm_r = _env_float("BREAKEVEN_ARM_R", 1.0)
        self.trail_after_r = _env_float("TRAIL_AFTER_R", 1.5)
        self.max_scale_ins = int(os.environ.get("MAX_SCALE_INS", "0") or 0)
        self.scale_in_step_r = _env_float("SCALE_IN_STEP_R", 1.5)
        self.adopt_on_start = os.environ.get("ADOPT_ON_START", "0") == "1"
        self.manage_enabled = os.environ.get("MANAGE_OPEN_POSITIONS", "0") == "1"

        self._pos_lock = threading.Lock()
        self._positions: Dict[str, Position] = {}

    # ---------------------- broker-auth & info ----------------------

    def login(self) -> bool:
        """
        Käytä capital_sessionin loginia ja jaettua sessiota/headersia.
        """
        try:
            sess, base = capital_rest_login()
            self.session = sess
            self.base = base.rstrip("/")
            if self.adopt_on_start:
                try:
                    self.adopt_open_positions()
                except Exception as e:
                    print(f"[CapitalClient][ADOPT][ERROR] {e}")
            if self.manage_enabled:
                t = threading.Thread(target=self.manage_positions_loop, name="cc-manage", daemon=True)
                t.start()
            return True
        except Exception as e:
            print(f"[CapitalClient][ERROR] Login epäonnistui: {e}")
            return False

    def account_info(self) -> Dict[str, Any]:
        if self.session and self.base:
            try:
                url = f"{self.base}/api/v1/accounts/me"
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                pass
        free = _env_float("CAP_FREE_BALANCE", None)
        if free is not None:
            return {"accounts": [{"id": self.account_id or "primary", "status": "ENABLED", "preferred": True,
                                  "balance": {"available": free}}]}
        return {"accounts": []}

    # ---------------------- hinta & instrumentit ----------------------

    def last_price(self, symbol_or_epic: str) -> Optional[float]:
        if self.session and self.base:
            try:
                url = f"{self.base}/api/v1/prices/{symbol_or_epic}"
                r = self.session.get(url, params={"resolution": "MINUTE", "max": 1}, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    arr = data.get("prices") or data.get("data") or []
                    if arr:
                        d = arr[-1]
                        for path in (("bid","offer"), ("bid","ask"), ("sell","buy")):
                            a, b = d.get(path[0]), d.get(path[1])
                            if isinstance(a, (int,float)) and isinstance(b, (int,float)):
                                return float((a+b)/2.0)
                # fall through
            except Exception:
                pass
        env_key = f"LASTPX_{symbol_or_epic}"
        try:
            v = float(os.environ.get(env_key, ""))
            if v > 0:
                return v
        except Exception:
            pass
        return None

    # ---------------------- EPIC resoluutio ----------------------

    @staticmethod
    def _is_prob_epic(s: str) -> bool:
        # EPIC usein pisteellinen, ilman välilyöntejä, esim. IX.D.SPTRD.D
        return ("." in s) and (" " not in s)

    def _resolve_epic(self, symbol_or_name: str) -> str:
        s = (symbol_or_name or "").strip()
        if not s:
            return s
        if self._is_prob_epic(s):
            return s

        # Ympäristö override: CAPITAL_EPIC_<ALNUM>
        key = "CAPITAL_EPIC_" + re.sub(r"[^A-Z0-9]", "", s.upper())
        v = os.environ.get(key, "").strip()
        if v:
            return v

        # Haku rajapinnasta
        try:
            hits = capital_market_search(s)
            if hits:
                target = s.upper().replace("/", "").replace(" ", "")
                # symbol exact (normalized)
                for h in hits:
                    sym = (h.get("symbol") or "").upper().replace("/", "").replace(" ", "")
                    if sym and sym == target:
                        return h["epic"]
                # name exact -> name contains -> first
                best = None
                for h in hits:
                    name = (h.get("instrumentName") or "").upper()
                    if name == s.upper():
                        best = h; break
                    if (s.upper() in name) and best is None:
                        best = h
                return (best or hits[0])["epic"]
        except Exception:
            pass

        # Viimeinen fallback: poista / ja välilyönnit
        return s.replace("/", "").replace(" ", "")

    # ---------------------- order & positio-operaatiot ----------------------

    def place_market(self, symbol: str, side: str, size: float,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None,
                     trailing: Optional[Dict[str, Any]] = None,
                     comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Markkinatoimeksianto IG/Capital-tyyppiseen päähän: POST /api/v1/positions/otc
        symbol paramilla annetaan näyttönimi tai EPIC; resolvoimme EPICin itse.
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
        if self.session and self.base:
            try:
                url = f"{self.base}/api/v1/orders/{order_id}"
                r = self.session.patch(url, json=kwargs, timeout=10)
                r.raise_for_status()
                return {"ok": True, "data": r.json() if r.text else {}}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "modify_order not supported (no REST base)"}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if self.session and self.base:
            try:
                url = f"{self.base}/api/v1/orders/{order_id}"
                r = self.session.delete(url, timeout=10)
                r.raise_for_status()
                return {"ok": True, "data": r.json() if r.text else {}}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "cancel_order not supported (no REST base)"}

    def close_position(self, position_id: str, size: Optional[float] = None) -> Dict[str, Any]:
        if self.session and self.base:
            try:
                url = f"{self.base}/api/v1/positions/{position_id}/close"
                payload = {}
                if size:
                    payload["size"] = float(size)
                r = self.session.post(url, json=payload, timeout=10)
                r.raise_for_status()
                with self._pos_lock:
                    self._positions.pop(position_id, None)
                return {"ok": True, "data": r.json() if r.text else {}}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        with self._pos_lock:
            ex = self._positions.pop(position_id, None)
        if ex:
            return {"ok": True, "data": {"local_only": True}}
        return {"ok": False, "error": "close_position not supported (no REST base)"}

    def get_open_positions(self) -> List[Position]:
        if self.session and self.base:
            try:
                url = f"{self.base}/api/v1/positions"
                if self.account_id:
                    url = f"{url}?account_id={self.account_id}"
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    arr = r.json() if isinstance(r.json(), list) else r.json().get("positions", [])
                    res: List[Position] = []
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
                    with self._pos_lock:
                        self._positions = {p.position_id: p for p in res if p.position_id}
                    return res
            except Exception:
                pass
        with self._pos_lock:
            return list(self._positions.values())

    # ---------------------- adoption & hallinta ----------------------

    def adopt_open_positions(self):
        pos = self.get_open_positions()
        with self._pos_lock:
            for p in pos:
                if p.position_id not in self._positions:
                    self._positions[p.position_id] = p
                self._positions[p.position_id].scale_ins = 0
        print(f"[ADOPT] Hallinnassa nyt {len(self._positions)} positiota.")

    def manage_positions_loop(self, poll_sec: float = 10.0):
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
            px = px_cache.get(p.symbol)
            if px is None:
                px = self.last_price(p.symbol) or p.entry_price
                px_cache[p.symbol] = px

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
                        add_size = max(0.0, p.size * 0.33)
                        if add_size > 0:
                            side = "BUY" if p.side == "LONG" else "SELL"
                            print(f"[MANAGE][SCALE] {p.symbol} {p.side} R={R:.2f} -> lisätään {add_size:.6f}")
                            self.place_market(p.symbol, side, add_size, comment="scale-in")
                            p.scale_ins += 1

    def _set_sl(self, p: Position, new_sl: float, tag: str):
        if self.session and self.base:
            try:
                url = f"{self.base}/api/v1/positions/{p.position_id}"
                body = {"stop_loss": new_sl}
                r = self.session.patch(url, json=body, timeout=10)
                r.raise_for_status()
                p.stop_loss = new_sl
                print(f"[{tag}] {p.symbol} pos={p.position_id} SL -> {new_sl}")
                return
            except Exception as e:
                print(f"[{tag}][ERROR] {p.symbol} SL ei päivittynyt: {e}")
        p.stop_loss = new_sl
        print(f"[{tag}] {p.symbol} pos={p.position_id} SL (local) -> {new_sl}")

    # ---------------------- sisäinen reititys ----------------------

    def _route_place_order(self, req: OrderRequest, trailing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        1) REST: POST /api/v1/positions/otc payload IG/Capital-muodossa
        2) Fallback: local mock position cache
        """
        if self.session and self.base:
            try:
                epic = self._resolve_epic(req.symbol)

                # IG/Capital "positions/otc" payload
                url = f"{self.base}/api/v1/positions/otc"
                payload = {
                    "epic": epic,
                    "direction": req.side,              # BUY/SELL
                    "size": float(req.size),
                    "orderType": req.order_type,        # MARKET/LIMIT/STOP
                    "timeInForce": "FILL_OR_KILL",      # tyypillinen
                    "forceOpen": True,
                }
                if req.price is not None and req.order_type != "MARKET":
                    payload["level"] = float(req.price)
                if req.take_profit is not None:
                    payload["limitLevel"] = float(req.take_profit)
                if req.stop_loss is not None:
                    payload["stopLevel"] = float(req.stop_loss)

                # Joissain IG/Capital-päissä tarvitaan VERSION-header (2)
                self.session.headers.setdefault("VERSION", "2")

                r = self.session.post(url, json=payload, timeout=20)
                r.raise_for_status()
                data = r.json() if r.text else {}
                order_id = str(data.get("dealId") or data.get("order_id") or data.get("id") or "")
                pos_id = str(data.get("position") or data.get("position_id") or "")

                if pos_id:
                    px = self.last_price(epic) or (req.price or 0.0)
                    entry = px if req.order_type == "MARKET" else (req.price or px)
                    with self._pos_lock:
                        self._positions[pos_id] = Position(
                            position_id=pos_id,
                            symbol=epic,
                            side="LONG" if req.side in ("BUY", "LONG") else "SHORT",
                            size=req.size,
                            entry_price=float(entry or 0.0),
                            stop_loss=req.stop_loss,
                            take_profit=req.take_profit,
                            meta={"order_id": order_id, "raw": data},
                        )
                print(f"[ORDER] {epic} {req.side} {req.size} type={req.order_type} ok id={order_id or pos_id}")
                return {"ok": True, "data": data, "order_id": order_id, "position_id": pos_id}
            except Exception as e:
                print(f"[ERROR] REST order epäonnistui: {e}")

        # Fallback: mock
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
    Live voi kutsua tätä suoraan (order_router käyttää tätä).
    """
    cli = CapitalClient()
    ok = cli.login()
    if not ok:
        print("[CapitalClient] Login epäonnistui – jatketaan best-effort-tilassa.")
    return cli
