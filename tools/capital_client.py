# /root/pro_botti/tools/capital_client.py
# -*- coding: utf-8 -*-
"""
CapitalClient – yhteensopiva asiakas liven odottamille metodeille:
- place_market, place_order, modify_order, cancel_order, close_position
- get_open_positions, account_info, last_price
- adopt_open_positions, manage_positions_loop

Käyttää samaa sessio- ja loginpolkua kuin tools.capital_session:
- capital_rest_login() -> (requests.Session, base)
- API-päätepisteet: /api/v1/* (prices, positions)
- Headerit ja tokenit linjassa capital_sessionin kanssa
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

    d["min_trade_size"] = _flt(d.get("min_trade_size"), 0.0)
    d["lot_step"] = _flt(d.get("lot_step") or d.get("step") or d.get("quantity_step"), 0.0)
    lev  = _flt(d.get("leverage"), None)
    mf   = _flt(d.get("margin_factor"), None)
    if lev is None and mf not in (None, 0):
        try:
            lev = 100.0 / float(mf)
        except Exception:
            lev = None
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
        self.account_id = os.environ.get("CAPITAL_ACCOUNT_ID", "").strip()

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
        Lisää myös VERSION ja X-CAP-ACCOUNT-ID headerit jos saatavilla.
        """
        try:
            sess, base = capital_rest_login()
            self.session = sess
            self.base = base.rstrip("/")
            # Jotkin instanssit vaativat VERSION-headerin (2)
            self.session.headers.setdefault("VERSION", "2")
            # Tilivalinta headeriin jos annettu
            if self.account_id:
                self.session.headers["X-CAP-ACCOUNT-ID"] = self.account_id

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
                print(f"[CapitalClient][account_info] HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                print(f"[CapitalClient][account_info][ERROR] {e}")
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
        return ("." in s) and (" " not in s)

    def _resolve_epic(self, symbol_or_name: str) -> str:
        s = (symbol_or_name or "").strip()
        if not s:
            return s
        if self._is_prob_epic(s):
            return s

        key = "CAPITAL_EPIC_" + re.sub(r"[^A-Z0-9]", "", s.upper())
        v = os.environ.get(key, "").strip()
        if v:
            return v

        try:
            hits = capital_market_search(s)
            if hits:
                target = s.upper().replace("/", "").replace(" ", "")
                for h in hits:
                    sym = (h.get("symbol") or "").upper().replace("/", "").replace(" ", "")
                    if sym and sym == target:
                        return h["epic"]
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

        return s.replace("/", "").replace(" ", "")

    # ---------------------- order & positio-operaatiot ----------------------

    def place_market(self, symbol: str, side: str, size: float,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None,
                     trailing: Optional[Dict[str, Any]] = None,
                     comment: Optional[str] = None) -> Dict[str, Any]:
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
                print(f"[CapitalClient][get_open_positions] HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                print(f"[CapitalClient][get_open_positions][ERROR] {e}")
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
        1) REST: POST /api/v1/positions/otc (IG/Capital-tyyli).
           Jos palaa 405/404 -> koita POST /api/v1/positions (osa instansseista käyttää tätä).
        2) Fallback: local mock position cache
        """
        if self.session and self.base:
            try:
                epic = self._resolve_epic(req.symbol)
                self.session.headers.setdefault("VERSION", "2")
                if self.account_id:
                    self.session.headers["X-CAP-ACCOUNT-ID"] = self.account_id

                payload_otc = {
                    "epic": epic,
                    "direction": req.side,              # BUY/SELL
                    "size": float(req.size),
                    "orderType": req.order_type,        # MARKET/LIMIT/STOP
                    "timeInForce": "FILL_OR_KILL",
                    "forceOpen": True,
                }
                if req.price is not None and req.order_type != "MARKET":
                    payload_otc["level"] = float(req.price)
                if req.take_profit is not None:
                    payload_otc["limitLevel"] = float(req.take_profit)
                if req.stop_loss is not None:
                    payload_otc["stopLevel"] = float(req.stop_loss)

                # 1) positions/otc
                url_otc = f"{self.base}/api/v1/positions/otc"
                r = self.session.post(url_otc, json=payload_otc, timeout=25)
                if r.status_code // 100 != 2:
                    # Jos ei sallittu/ei löydy, kokeile /positions
                    if r.status_code in (404, 405):
                        payload_pos = {
                            "symbol": epic,               # jotkut instanssit käyttävät "symbol" kenttää
                            "side": req.side,             # BUY/SELL
                            "size": float(req.size),
                            "type": req.order_type,       # MARKET/LIMIT/STOP
                            "tif": "FOK",
                        }
                        if req.price is not None and req.order_type != "MARKET":
                            payload_pos["price"] = float(req.price)
                        # SL/TP nimet voivat poiketa – yritetään geneerisiä
                        if req.take_profit is not None:
                            payload_pos["take_profit"] = float(req.take_profit)
                        if req.stop_loss is not None:
                            payload_pos["stop_loss"] = float(req.stop_loss)

                        url_pos = f"{self.base}/api/v1/positions"
                        rr = self.session.post(url_pos, json=payload_pos, timeout=25)
                        rr.raise_for_status()
                        data = rr.json() if rr.text else {}
                    else:
                        r.raise_for_status()
                        data = r.json() if r.text else {}
                else:
                    data = r.json() if r.text else {}

                order_id = str((data or {}).get("dealId") or (data or {}).get("order_id") or (data or {}).get("id") or "")
                pos_id = str((data or {}).get("position") or (data or {}).get("position_id") or "")

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

        # 2) Fallback: mock
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
        print(f"[ORDER][LOCAL] {req.symbol} {req.side} {req.size} type={req.orderType} -> mock pos {pos_id}")
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
