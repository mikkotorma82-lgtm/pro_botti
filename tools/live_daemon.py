#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tools.epic_resolver import resolve_epic, rest_bid_ask
def resolve_epic(symbol: str) -> str:
    """Palauta Capital EPIC annetulle symbolille:
    1) ENV: CAPITAL_EPIC_<SYMBOL>
    2) provider_capital.SYMBOL_TO_EPIC
    3) fallback: SYMBOL sellaisenaan
    """
    import os
    s = (symbol or "").upper()
    epic = os.environ.get(f"CAPITAL_EPIC_{s}")
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

"""
live_daemon.py — Live-traderi

Integraatiot:
 - AI-gate: tools.ai_gate._gd_call_and_exec(lukee models/pro_{SYMBOL}_{TF}.json -> ai_thresholds)
 - Position sizer: tools.position_sizer.calc_order_size (riskipohjainen, broker-minimit/step/leverage)
 - Capital API: tools.capital_client.CapitalClient (tilin vapaa pääoma, hinnat, toimeksiannot)

Ympäristömuuttujat (systemd-palvelussa):
  SYMBOLS=BTCUSDT,ETHUSDT,...        # pilkulla eroteltu lista
  TFS=15m,1h,4h                      # pilkulla eroteltu lista
  LOOP_SEC=30                        # loopin viive sekunteina
  RISK_PCT=0.10                      # perusriskiprosentti (override mahdollinen risk_overrides.json)
  RISK_SAFETY=0.95                   # turvakerroin riskibudjetille
  DRY_RUN=0                          # 1=älä tee toimeksiantoja, logita vain
  AIGATE_TG=0                        # 1=lähetä päätöslokit TG:hen tools.tele:n kautta

Huom:
 - Jos signaalimoduuli (tools.trade_live) ei ole saatavilla tai ei palauta p_up-todennäköisyyttä,
   daemon ei avaa treidiä (HOLD). Tämä on tarkoituksella turvallista.
"""

import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List

# ----- Sisäiset työkalut -----
try:
    from tools.tele import send as tgsend
except Exception:
    def tgsend(msg: str):  # no-op jos TG ei ole konffattu
        pass

from tools.ai_gate import gate_decision
from tools.position_sizer import calc_order_size
try:
    from tools.instrument_loader import load_instruments
except Exception:
    # Fallback: kerää instrumentit models/pro_*.json -tiedostoista
    def load_instruments():
        import json, glob, os
        models_dir = os.path.join(os.path.dirname(__file__), "..", "models")
        paths = glob.glob(os.path.join(models_dir, "pro_*_*.json"))
        out = []
        for path in paths:
            try:
                with open(path) as f:
                    meta = json.load(f)
                sym = meta.get("symbol")
                tf  = meta.get("tf") or meta.get("timeframe") or meta.get("tf_str")
                if sym and tf:
                    # Palautetaan listana dicttejä: {"symbol": "...", "tf": "..."}
                    out.append({"symbol": sym, "tf": tf})
            except Exception:
                pass
        # Poista duplikaatit (symbol, tf)
        seen = set()
        uniq = []
        for d in out:
            k = (d["symbol"], d["tf"])
            if k in seen:
                continue
            seen.add(k); uniq.append(d)
        return uniq


# Capital API -asiakas (sallitaan puuttua -> dry mode)
try:
    from tools.capital_client import CapitalClient
except Exception:
    CapitalClient = None  # type: ignore

ROOT = "/root/pro_botti"


# --------- Pienet apurit ---------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def log(line: str) -> None:
    try:
        print(line, flush=True)
    except Exception:
        pass

def env_csv(name: str, default: str) -> List[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]

def safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


# --------- Capital-asiakas & tiedot ---------

class Broker:
    def __init__(self):
        self.cli = None
        self.logged_in = False
        self._last_free = 0.0

        # CapitalClient voi puuttua — tällöin DRY
        try:
            from tools.capital_client import CapitalClient as _Cap  # lazy import
        except Exception:
            log("[WARN] CapitalClient ei saatavilla -> DRY mode")
            self.cli = None
            self.logged_in = False
            return

        # Luo clientti; jos onnistuu, kirjataan sisään (clientin oma login tai REST-tokenit)
        try:
            self.cli = _Cap()
            # jos live_daemonissa on _capital_login, käytä sitä
            try:
                from tools import live_daemon as _ld
                if hasattr(_ld, "_capital_login"):
                    self.logged_in = bool(_ld._capital_login(self.cli))
                else:
                    # fallback: jos clientissa on login-metodi
                    if hasattr(self.cli, "login"):
                        self.cli.login()
                        self.logged_in = True
                    else:
                        self.logged_in = True
            except Exception:
                # yritä clientin loginia, jos löytyy
                if hasattr(self.cli, "login"):
                    self.cli.login()
                    self.logged_in = True
                else:
                    self.logged_in = True
            log("[INFO] Capital login ok")
        except Exception as e:
            import traceback
            log(f"[AIGATE-ERR] {e!r}")
            log(traceback.format_exc())
            self.cli = None
            self.logged_in = False

    def free_balance(self) -> float:
        """Hae tilin vapaa pääoma (available)."""
        if not self.logged_in or self.cli is None:
            return self._last_free
        try:
            acc = self.cli.account_info()
            free = 0.0
            if isinstance(acc, dict) and "accounts" in acc:
                for a in acc["accounts"]:
                    if a.get("preferred") or a.get("status") == "ENABLED":
                        free = safe_float(a.get("balance", {}).get("available", 0.0))
                        break
            self._last_free = max(0.0, free)
        except Exception as e:
            log(f"[WARN] account_info epäonnistui: {e}")
        return self._last_free

    def _rest_last_price(self, symbol: str):

        """Capital REST: /api/v1/prices/{EPIC}?resolution=MINUTE&max=1 (VERSION=3).
Mapittaa USDT->USD ennen EPIC-resoluutiota ja parsii closePrice.bid/ask → mid.
Palauttaa float tai None.
"""

        if self.cli is None or not hasattr(self.cli, "session"):

            return None

        import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

def map_symbol_for_capital(sym: str) -> str:
    sym = (sym or "").upper()
    return sym[:-4] + "USD" if sym.endswith("USDT") else sym


def _capital_resolve_epic(cli, symbol: str) -> str:
    """Palauta EPIC. Oletus: EPIC == symbol (esim. BTCUSD).
    Yliaja env: CAPITAL_EPIC_<SYMBOL> (esim. CAPITAL_EPIC_BTCUSD=BTCUSD)"""
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    key = f"CAPITAL_EPIC_{symbol.upper()}"
    return os.getenv(key, symbol)

def map_symbol_for_capital(sym: str) -> str:
    sym = (sym or "").upper()
    return sym[:-4] + "USD" if sym.endswith("USDT") else sym

def _capital_resolve_epic(cli, symbol: str) -> str:
    """Palauta EPIC Capitalille. Oletus: EPIC == symbol (esim. BTCUSD).
    Yliaja env: CAPITAL_EPIC_<SYMBOL> (esim. CAPITAL_EPIC_BTCUSD=BTCUSD)."""
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    key = f"CAPITAL_EPIC_{(symbol or '').upper()}"
    return os.getenv(key, symbol)

def map_symbol_for_capital(sym: str) -> str:
    sym = (sym or "").upper()
    return sym[:-4] + "USD" if sym.endswith("USDT") else sym

def _capital_resolve_epic(cli, symbol: str) -> str:
    """Palauta EPIC Capitalille. Oletus: EPIC == symbol (esim. BTCUSD).
    Yliaja env: CAPITAL_EPIC_<SYMBOL> (esim. CAPITAL_EPIC_BTCUSD=BTCUSD)."""
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    key = f"CAPITAL_EPIC_{(symbol or '').upper()}"
    return os.getenv(key, symbol)


def _cap_get(cli, url, version: int, timeout=10):
    sess = cli.session
def _broker_last_price(self, symbol: str) -> float:
    """Palauta viimeisin hinta Capitalista.
    Järjestys:
      1) yritä CapitalClient.* last price -metodeja
      2) REST /api/v1/prices/{EPIC}?resolution=MINUTE&max=1 (VERSION=3)
      3) ENV-välimuisti LASTPX_<SYMBOL>
    """
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s


    # apu: num/dict mid
    def _mid(v):
        if isinstance(v, dict):
            b, a = v.get("bid"), v.get("ask")
            if isinstance(b, (int, float)) and isinstance(a, (int, float)):
                return (b + a) / 2.0
        if isinstance(v, (int, float)):
            return float(v)
        return None

    raw = (symbol or "").upper()
    sym = map_symbol_for_capital(raw) if 'map_symbol_for_capital' in globals() else raw

    # 1) client-metodit
    if getattr(self, "cli", None) is not None:
        for nm in ("last_price","price","quote","get_price","get_last_price"):
            fn = getattr(self.cli, nm, None)
            if callable(fn):
                try:
                    val = fn(sym)
                    px = None
                    if isinstance(val, (int, float)):
                        px = float(val)
                    elif isinstance(val, dict):
                        px = (
                            _mid(val.get("mid"))
                            or _mid(val.get("price"))
                            or _mid(val.get("last"))
                            or _mid(val.get("close"))
                            or _mid(val)
                        )
                    elif isinstance(val, (list, tuple)) and val:
                        px = _mid(val[-1])
                    if isinstance(px, (int, float)):
                        os.environ[f"LASTPX_{sym}"] = str(px)
                        return float(px)
                except Exception:
                    pass

    # 2) REST /prices (VERSION=3)
    try:
        base = getattr(self.cli, "base", None) or os.getenv("CAPITAL_API_BASE")
        sess = getattr(self.cli, "session", None)
        if base and sess:
            try:
                epic = _capital_resolve_epic(self.cli, sym)  # env-override jos määritelty
            except Exception:
                epic = sym
            url = f"{base.rstrip('/')}/api/v1/prices/{epic}?resolution=MINUTE&max=1"
            # käytä _cap_get jos olemassa (asettaa VERSION-headerin oikein)
            # unified request using _cap_get if present, else plain session.get
            r = (_cap_get(self.cli, url, 3, timeout=10) if "_cap_get" in globals() else sess.get(url, headers=hdr, timeout=10))
                    r = sess.get(url, headers=hdr, timeout=10)
try:
    Broker  # varmista että luokka on olemassa
    if not hasattr(Broker, "last_price"):
        setattr(Broker, "last_price", _broker_last_price)
except Exception:
    pass

def _cap_price_mid(cli, raw_symbol: str):
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    base = getattr(cli, "base", None) or os.getenv("CAPITAL_API_BASE")
    if not base: 
        return None
    sym  = map_symbol_for_capital(raw_symbol)  # BTCUSDT -> BTCUSD
    epic = _capital_resolve_epic(cli, sym)
    url  = f"{base.rstrip('/')}/api/v1/prices/{epic}?resolution=MINUTE&max=1"
    try:
        r   = _cap_get(cli, url, 3)
        js  = r.json() or {}
        arr = js.get("prices") or js.get("content") or []
        if not arr: 
            return None
        last = arr[-1]
        cp   = last.get("closePrice") or {}
        bid, ask = cp.get("bid"), cp.get("ask")
        if isinstance(bid,(int,float)) and isinstance(ask,(int,float)):
            return (bid+ask)/2.0
        # fallbackeja jos closePrice puuttuu
        for k in ("openPrice","highPrice","lowPrice"):
            p = last.get(k) or {}
            b,a = p.get("bid"), p.get("ask")
            if isinstance(b,(int,float)) and isinstance(a,(int,float)):
                return (b+a)/2.0
    except Exception:
        pass
    return None

def _get_last_price_force(broker, symbol: str):
    # 1) Broker.last_price jos on
    try:
        px = None
        if hasattr(broker, "last_price"):
            px = _get_last_price_force(broker, symbol)
        if isinstance(px,(int,float)) and px>0:
            return float(px)
    except Exception:
        pass
    # 2) Broker.cli.* last_price variantit
    cli = getattr(broker, "cli", None)
    if cli:
        for nm in ("last_price","get_price","price","quote","get_last","get_last_price"):
            fn = getattr(cli, nm, None)
            if callable(fn):
                try:
                    v = fn(map_symbol_for_capital(symbol))
                    if isinstance(v,(int,float)) and v>0:
                        return float(v)
                    if isinstance(v, dict):
                        # dict -> mid tai price/last/close
                        if "mid" in v and isinstance(v["mid"], (int,float)):
                            return float(v["mid"])
                        for k in ("price","last","close"):
                            if isinstance(v.get(k), (int,float)):
                                return float(v[k])
                        b = v.get("bid"); a = v.get("ask")
                        if isinstance(b,(int,float)) and isinstance(a,(int,float)):
                            return (b+a)/2.0
                except Exception:
                    pass
        # 3) Pakota REST-mid
        try:
            mid = _cap_price_mid(cli, symbol)
            if isinstance(mid,(int,float)) and mid>0:
                return float(mid)
        except Exception:
            pass
    # 4) ENV-välimuisti
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    sym_map = map_symbol_for_capital(symbol)
    ev = os.getenv(f"LASTPX_{sym_map}") or os.getenv(f"LASTPX_{symbol}")
    try:
        if ev is not None:
            v = float(ev)
            if v>0: 
                return v
    except Exception:
        pass
    return None

# --- Injected wrapper: extend Broker.last_price with REST fallback (idempotent) ---
try:
    if not getattr(Broker, "_wrapped_last_price", False):
        _orig_last_price = Broker.last_price
        def _last_price_wrapped(self, symbol: str) -> float:
            # 1) Yritä alkuperäistä toteutusta
            try:
                v = _orig_last_price(self, symbol)
                if v and float(v) != 0.0:
                    return float(v)
            except Exception:
                pass
            # 2) Map USDT->USD ja REST /prices → mid
            try:
                sym = map_symbol_for_capital(symbol)
                v2 = _get_last_price_force(self, sym)
                if v2 and float(v2) != 0.0:
                    return float(v2)
            except Exception:
                pass
            # 3) ENV-välimuisti LASTPX_<SYMBOL>
            try:
                import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

                sym = map_symbol_for_capital(symbol)
                envv = os.getenv(f"LASTPX_{sym}")
                if envv:
                    return float(envv)
            except Exception:
                pass
            return 0.0
        Broker.last_price = _last_price_wrapped
        Broker._wrapped_last_price = True
except Exception:
    pass

def _cap_rest_last_mid(broker, epic: str):
    import json
    sess, base = _cap_get_rest_session(broker)
    if not (sess and base and epic):
        return None
    url = f"{base}/api/v1/prices/{epic}?resolution=MINUTE&max=1"
    h = dict(sess.headers); h["VERSION"] = "3"; h.setdefault("Accept","application/json")
    r = sess.get(url, headers=h, timeout=10)
    r.raise_for_status()
    js = r.json() or {}
    arr = js.get("prices") or js.get("content") or []
    if not arr:
        return None
    p = arr[-1]
    cb = ((p.get("closePrice") or {}).get("bid")); ca = ((p.get("closePrice") or {}).get("ask"))
    if isinstance(cb,(int,float)) and isinstance(ca,(int,float)):
        return (cb+ca)/2.0
    ob = ((p.get("openPrice") or {}).get("bid")); oa = ((p.get("openPrice") or {}).get("ask"))
    if isinstance(ob,(int,float)) and isinstance(oa,(int,float)):
        return (ob+oa)/2.0
    return None

def capital_ensure_tokens(cli) -> bool:
    """
    Varmistaa että sessiossa on CST & X-SECURITY-TOKEN.
    """
    try:
        sess = getattr(cli, "session", None)
        base = getattr(cli, "base", None)
        if not sess or not base:
            return False
        if sess.headers.get("CST") and sess.headers.get("X-SECURITY-TOKEN"):
            return True

        # 1) Jos CapitalClientilta löytyy login/authenticate tms., kokeile
        for nm in ("login","authenticate","signin","create_session","start","login_session"):
            fn = getattr(cli, nm, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
                if sess.headers.get("CST") and sess.headers.get("X-SECURITY-TOKEN"):
                    return True

        # 2) Meidän REST-login
        return _capital_rest_login(cli)
    except Exception:
        return False

def _pick_exec_price(side: str, bid: float, ask: float) -> float:
    side = (side or "").upper()
    if side == "BUY":
        return float(ask)
    if side == "SELL":
        return float(bid)
    # oletus: konservatiivinen
    return float((bid + ask) / 2.0)

def trade_loop():
    """
    Yksinkertainen päätössilmukka:
      - Broker & token-varmistus (capital_ensure_tokens)
      - SYMBOLS x TFS iterointi
      - bid/ask haku Capitalista + spread-vartija (SPREAD_MAX_PCT, oletus 0.4%)
      - gate_decision-kutsu (tuottaa [AIGATE]-logit)
    """
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s
, time, traceback
    LOOP_SEC = int(os.getenv("LOOP_SEC", "30"))
    SPREAD_MAX_PCT = float(os.getenv("SPREAD_MAX_PCT", "0.004"))

    from tools import live_daemon as ld
    log = getattr(ld, "log", print)

    log("[LOOP] trade_loop start")
    while True:
        try:
            # Broker + mahdolliset Capital-tokenit
            b = ld.Broker()
            cli = getattr(b, "cli", None)
            if cli is not None and hasattr(ld, "capital_ensure_tokens"):
                ld.capital_ensure_tokens(cli)

            # Aja kaikki symbolit ja timeframe:t
            symbols = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT")
            tfs = os.getenv("TFS", "15m,1h,4h")
            syms = [x.strip() for x in symbols.split(",") if x.strip()]
            tf_list = [x.strip() for x in tfs.split(",") if x.strip()]

            for symbol in syms:
                try:
                    symbol_cap = ld.map_symbol_for_capital(symbol)
                    bid, ask = ld.get_bid_ask(b, symbol_cap)
                    if bid is None or ask is None:
                        log(f"[PRICE] {symbol} -> {symbol_cap} (no bid/ask)")
                        continue

                    mid = (bid + ask) / 2.0
                    spread = (ask - bid) / mid if mid else 1e9
                    if spread > SPREAD_MAX_PCT:
                        log(f"[PRICE] {symbol} spread {spread*100:.3f}% > {SPREAD_MAX_PCT*100:.2f}% -> skip")
                        continue

                    log(f"[PRICE] {symbol} -> {symbol_cap} bid={bid} ask={ask} spread={spread*100:.3f}%")

                    for tf in tf_list:
                        try:
                            ld._gd_call_and_exec(symbol, tf)
                        except Exception as e:
                            log(f"[AIGATE-ERR] {symbol} {tf}: {e}")
                except Exception as e:
                    log(f"[ERR] symbol loop {symbol}: {e}")

            time.sleep(LOOP_SEC)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            log(f"[LOOP-ERR] {e}")
            traceback.print_exc()
            time.sleep(LOOP_SEC)


if __name__ == "__main__":
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s
, time, traceback, types
    try:
        LOOP_SEC = int(os.getenv("LOOP_SEC", "30"))
    except Exception:
        LOOP_SEC = 30

    print("[BOOT] live_daemon starting")
    entry = os.getenv("ENTRY_FN") or os.getenv("MAIN_FN")
    candidates = ("main","run_loop","run","trade_loop","loop","start","daemon","live","run_once","step")
    print(f"[BOOT] ENTRY_FN={entry!r} | candidates={candidates}")

    funcs = sorted([k for k,v in globals().items() if isinstance(v, types.FunctionType)])
    print(f"[BOOT] functions_in_globals={funcs}")

    fn = None
    if entry:
        fn = globals().get(entry)
    if not fn:
        for name in candidates:
            fn = globals().get(name)
            if callable(fn):
                entry = name
                break

    if callable(fn):
        print(f"[BOOT] Entry function resolved -> {entry}(); running…")
        try:
            fn()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"[BOOT-ERR] {e}")
            traceback.print_exc()
            time.sleep(LOOP_SEC)
    else:
        print("[BOOT] No entry function found; idling")
        while True:
            time.sleep(LOOP_SEC)

# --- ORDER EXECUTION GLUE ----------------------------------------------------
def _envf(name, default):
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    try:
        v = os.getenv(name)
        return float(v) if v not in (None, "") else float(default)
    except Exception:
        return float(default)

def _envi(name, default):
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    try:
        v = os.getenv(name)
        return int(v) if v not in (None, "") else int(default)
    except Exception:
        return int(default)

def _envb(name, default=False):
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    v = str(os.getenv(name, str(int(default)))).strip().lower()
    return v in ("1","true","yes","on")

def on_signal(symbol, side, tf, bid, ask):
    """
    Kutsutaan kun gate_decision antaa selkeän LONG/SHORT signaalin.
    side: 'BUY' tai 'SELL'
    """
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s
, math, time
    spread = (ask-bid)/((ask+bid)/2.0)
    spread_max = _envf("SPREAD_MAX_PCT", 0.004)
    if spread > spread_max:
        log(f"[ORDER] {symbol} skip: spread {spread:.3%} > {spread_max:.3%}")
        return

    # Riskinhallinta ja position koko
    balance = _envf("ACCOUNT_BALANCE_USD", 10000.0)
    risk_pct = _envf("RISK_PER_TRADE", 0.0075)
    stop_pct = _envf("STOP_LOSS_PCT", 0.005)
    risk_usd = balance * risk_pct
    price = ask if side == "BUY" else bid
    notional = risk_usd / stop_pct
    qty = notional / price

    tp_rr = _envf("TAKE_PROFIT_RR", 2.0)
    if side == "BUY":
        sl = price * (1 - stop_pct)
        tp = price * (1 + stop_pct * tp_rr)
    else:
        sl = price * (1 + stop_pct)
        tp = price * (1 - stop_pct * tp_rr)

    # Toteutus: kuiva-ajo vai oikea toimeksianto
    if not _envb("EXECUTE_ORDERS", False) or _envb("DRY_RUN", False) or not _envb("ENABLE", True):
        log(f"[ORDER][DRY] {side} {symbol} qty≈{qty:.6f} @~{price:.4f} SL~{sl:.4f} TP~{tp:.4f} tf={tf}")
        return

    try:
        # TODO: Lisää Capital REST order -kutsu tänne (place_market_order_capital)
        log(f"[ORDER] {side} {symbol} qty≈{qty:.6f} @~{price:.4f} SL~{sl:.4f} TP~{tp:.4f} tf={tf}")
    except Exception as e:
        log(f"[ORDER][ERR] {symbol} {side} -> {e}")


def _gd_call_and_exec(symbol, tf, bid=None, ask=None):


    """Wrapperi AIGATE-kutsulle. Sallii kutsun ilman bid/ask-arvoja.


    Jos bid/ask puuttuu, haetaan ne get_bid_ask(symbol) avulla. Palauttaa gate_decisionin paluuarvon.


    Mahdolliset poikkeukset lokitetaan tracebackilla."""


    try:


        if bid is None or ask is None:


            try:


                bid, ask = get_bid_ask(symbol)


            except Exception:


                bid = ask = None





        # Delegoi alkuperäiseen päätösfunktioon; wrapper ei muuta logiikkaa


        return gate_decision(symbol, tf)





    except Exception as e:


        import traceback


        log(f"[AIGATE-ERR] {e!r} ")


        log(traceback.format_exc())


        return None


def on_signal_pro(symbol, side, tf, bid, ask):
    """Perusriskit + SL/TP. Suorittaa vain kun ENABLE=1, EXECUTE_ORDERS=1 ja DRY_RUN=0."""
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    def _f(name, default):
        try:
            v = os.getenv(name)
            return float(v) if v not in (None, "") else float(default)
        except Exception:
            return float(default)

    spread = (ask - bid) / ((ask + bid) / 2.0)
    spread_max = _f("SPREAD_MAX_PCT", 0.006)
    if spread > spread_max:
        log(f"[ORDER] {symbol} skip: spread {spread:.3%} > {spread_max:.3%}")
        return

    balance = _f("ACCOUNT_BALANCE_USD", 10000.0)
    risk_pct = _f("RISK_PER_TRADE", 0.0075)
    stop_pct = _f("STOP_LOSS_PCT", 0.005)
    tp_rr    = _f("TAKE_PROFIT_RR", 2.0)

    risk_usd = balance * risk_pct
    price = ask if side == "BUY" else bid
    notional = risk_usd / max(stop_pct, 1e-6)
    qty = max(notional / max(price, 1e-9), 0.0)

    if side == "BUY":
        sl = price * (1 - stop_pct)
        tp = price * (1 + stop_pct * tp_rr)
    else:
        sl = price * (1 + stop_pct)
        tp = price * (1 - stop_pct * tp_rr)

    if (not _envb("ENABLE", True)) or _envb("DRY_RUN", False) or (not _envb("EXECUTE_ORDERS", False)):
        log(f"[ORDER][DRY] {side} {symbol} qty≈{qty:.6f} @~{price:.4f} SL~{sl:.4f} TP~{tp:.4f} tf={tf}")
        return

    # Tässä kohtaa tee varsinainen Capital.com -orderi.
    log(f"[ORDER] {side} {symbol} qty≈{qty:.6f} @~{price:.4f} SL~{sl:.4f} TP~{tp:.4f} tf={tf}")

# === CAPITAL REST PATCH (clean) ===
def _cap_get_rest_session(broker=None):
    """
    Palauta (requests.Session, base_url). Ei koskaan palauta None-sessionia.
    Perusotsikot asetetaan; login lisää CST ja X-SECURITY-TOKEN.
    """
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s
, requests
    base = os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com").rstrip("/")
    s = requests.Session()
    api_key = os.getenv("CAPITAL_API_KEY") or os.getenv("CAPITAL_COM_API_KEY") or ""
    s.headers.update({
        "X-CAP-API-KEY": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    return s, base

def _capital_rest_login(cli):
    """
    Kirjaudu sisään Capital RESTiin. Asettaa CST ja X-SECURITY-TOKEN session headersiin.
    Palauttaa True/False.
    """
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    base = os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com").rstrip("/")
    user = os.getenv("CAPITAL_LOGIN")
    pwd  = os.getenv("CAPITAL_PASSWORD")
    if not (cli and user and pwd):
        return False
    url = f"{base}/session"
    try:
        r = cli.post(url, json={"identifier": user, "password": pwd}, timeout=20)
    except Exception:
        return False
    if r.status_code // 100 != 2:
        return False
    cst = r.headers.get("CST") or r.headers.get("cst")
    sec = r.headers.get("X-SECURITY-TOKEN") or r.headers.get("x-security-token")
    if cst: cli.headers["CST"] = cst
    if sec: cli.headers["X-SECURITY-TOKEN"] = sec
    return True

def capital_ensure_tokens(cli) -> bool:
    """Tarkista että CST ja X-SECURITY-TOKEN ovat session headersissa."""
    if not cli:
        return False
    h = getattr(cli, "headers", {}) or {}
    return bool(h.get("CST") and h.get("X-SECURITY-TOKEN"))
# === /CAPITAL REST PATCH (clean) ===

import requests, os, json, time


# --- Capital.com cached login + helpers (override) ---
_CAP_CACHE = {"sess": None, "base": None, "cst": None, "sec": None, "ts": 0}

def capital_rest_login(force=False):
    """
    Kirjautuu /api/v1/session:iin ja tallettaa sessioon CST/X-SECURITY-TOKEN-headerit.
    Välimuisti: ei uusiudu ellei 9 min vanhempi tai force=True.
    Palauttaa (session, base) tai (None, None).
    """
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s
, time, requests
    now = time.time()
    if (not force and _CAP_CACHE["sess"] and _CAP_CACHE["cst"] and _CAP_CACHE["sec"]
        and (now - _CAP_CACHE["ts"] < 540)):  # 9 min
        return _CAP_CACHE["sess"], _CAP_CACHE["base"]

    base = os.getenv("CAPITAL_API_BASE","https://api-capital.backend-capital.com").rstrip("/")
    key  = os.getenv("CAPITAL_API_KEY")
    user = os.getenv("CAPITAL_LOGIN")
    pw   = os.getenv("CAPITAL_PASSWORD")
    if not all([base, key, user, pw]):
        print("[CAPITAL] ERROR: missing CAPITAL_* envs")
        return (None, None)

    s = requests.Session()
    hdr = {"X-CAP-API-KEY": key, "Accept":"application/json","Content-Type":"application/json"}
    payload = {"identifier": user, "password": pw}

    for attempt in range(5):
        r = s.post(f"{base}/api/v1/session", json=payload, headers=hdr, timeout=20)
        if r.status_code == 200:
            cst = r.headers.get("CST")
            sec = r.headers.get("X-SECURITY-TOKEN")
            if not (cst and sec):
                print("[CAPITAL] login missing tokens")
                return (None, None)
            s.headers.update({"X-CAP-API-KEY": key, "CST": cst, "X-SECURITY-TOKEN": sec,
                              "Accept":"application/json","Content-Type":"application/json"})
            _CAP_CACHE.update({"sess": s, "base": base, "cst": cst, "sec": sec, "ts": time.time()})
            print("[CAPITAL] login OK (cached) ->", base)
            return s, base
        if r.status_code == 429:
            wait = min(2**attempt, 30)
            print(f"[CAPITAL] 429 too-many-requests; sleep {wait}s")
            time.sleep(wait)
            continue
        print("[CAPITAL] login fail", r.status_code, (r.text or "")[:200])
        break
    return (None, None)

def capital_send_order(symbol, side, qty, price=None, stop_loss=None, take_profit=None, sess=None, base=None):
    """
    Lähettää MARKKINATOIMEKSIANNON /api/v1/positions/otc.
    Käyttää annettua sessiota tai cache-loginia. Palauttaa requests.Response tai None.
    """
    import time
    if not (sess and base):
        sess, base = capital_rest_login()
    if not sess:
        print("[ORDER] Login failed — no session")
        return None

    epic = symbol.replace("USDT","USD")
    direction = "BUY" if str(side).upper().startswith("B") else "SELL"
    deal_ref = f"BOT-{symbol}-{direction}-{int(time.time())}"

    payload = {
        "epic": epic,
        "direction": direction,
        "size": round(float(qty), 4),
        "orderType": "MARKET",
        "guaranteedStop": False,
        "currencyCode": "USD",
        "forceOpen": True,
        "dealReference": deal_ref,
    }
    if stop_loss:   payload["stopLevel"]  = round(float(stop_loss), 5)
    if take_profit: payload["limitLevel"] = round(float(take_profit), 5)
    if price:       payload["level"]      = round(float(price), 5)

    for attempt in range(3):
        r = sess.post(f"{base}/api/v1/positions" if os.getenv("CAPITAL_ACCOUNT_TYPE","CFD")=="CFD" else f"{base}/api/v1/positions/otc", json=payload, timeout=20)
        print("[ORDER] POST /positions/otc ->", r.status_code)
        if r.status_code == 200:
            print("[ORDER] OK:", (r.text or "")[:400])
            return r
        if r.status_code == 429:
            wait = 1 + attempt*2
            print(f"[ORDER] 429; sleep {wait}s and retry")
            time.sleep(wait)
            continue
        print("[ORDER] FAIL:", (r.text or "")[:400])
        return r
    return None



    # --- Capital-lähetys gatingin takana ---


    if _envb("ENABLE", True) and _envb("EXECUTE_ORDERS", False):


        if _envb("DRY_RUN", False):


            log(f"[ORDER][DRY] {side} {symbol} @ bid={bid} ask={ask} tf={tf}")


        else:


            _send_via_capital(symbol, side, tf, bid, ask)


    else:


        log("[ORDER] Skipped: ENABLE/EXECUTE_ORDERS gates")



def _send_via_capital(symbol, side, tf, bid, ask):
    """Laskee SL/TP + määrän ja lähettää toimeksiannon Capitaliin."""
    import os

def resolve_epic(symbol: str) -> str:
    s = (symbol or "").upper()
    env_key = f"CAPITAL_EPIC_{s}"
    epic = os.environ.get(env_key)
    if epic:
        return epic
    try:
        from tools import provider_capital as _pc
        m = getattr(_pc, "SYMBOL_TO_EPIC", {})
        if isinstance(m, dict) and s in m and m[s]:
            return m[s]
    except Exception:
        pass
    return s

    try:
        price = ask if side.upper()=="BUY" else bid
        if price is None:
            log("[ORDER] FAIL: price missing"); return False

        sl_pct = safe_float(os.getenv("STOP_LOSS_PCT"), 0.003) or 0.003
        rr     = safe_float(os.getenv("TAKE_PROFIT_RR"), 1.5) or 1.5
        risk   = safe_float(os.getenv("RISK_PER_TRADE"), 0.0005) or 0.0005

        if side.upper()=="BUY":
            sl = price*(1-sl_pct); tp = price*(1+sl_pct*rr)
        else:
            sl = price*(1+sl_pct); tp = price*(1-sl_pct*rr)

        fq = os.getenv("FIXED_QTY")
        if fq:
            qty = float(fq); log(f"[ORDER] FIXED_QTY override -> {qty}")
        else:
            qty = calc_order_size(symbol, price, sl, risk)

        if not qty or qty <= 0:
            log("[ORDER] FAIL: qty<=0"); return False

        sess, base = capital_rest_login()
        if not sess: 
            log("[ORDER] FAIL: Capital login failed"); return False

        r = capital_send_order(symbol, side.upper(), qty, price=price,
                               stop_loss=sl, take_profit=tp, sess=sess, base=base)
        if r is not None and getattr(r, "ok", False):
            log(f"[ORDER] SENT {side} {symbol} qty≈{qty:.6f} @~{price:.5f} SL~{sl:.5f} TP~{tp:.5f} tf={tf}")
            return True
        log("[ORDER] FAIL: send_order returned None or non-OK")
        return False
    except Exception as e:
        import traceback
        log(f"[ORDER] EXC: {e!r}")
        log(traceback.format_exc())
        return False

_CAP_PRICE_CACHE = {'data': {}, 'retry_after': 0}


def capital_get_bidask(symbol, sess=None, base=None, ttl=3.0):
    """
    Hakee bid/ask Capital RESTistä, käyttäen shared-loginia + per-symbol cachea.
    TTL=3s vähentää 429-virheitä. 429 -> backoff 10s.
    Palauttaa (bid, ask) tai (None, None).
    """
    import time, json, os
    global _CAP_CACHE, _CAP_PRICE_CACHE

    now = time.time()
    # 429-backoff
    if _CAP_PRICE_CACHE.get('retry_after', 0) > now:
        return (None, None)

    # cache-hitti?
    d = _CAP_PRICE_CACHE.setdefault('data', {})
    row = d.get(symbol)
    if row and (now - row.get('ts', 0)) < ttl:
        return (row.get('bid'), row.get('ask'))

    # sessio & base (vältetään turhat login-ujut)
    if not sess or not base:
        sess, base = capital_rest_login()   # käyttää cachea

    try:
        epic = map_symbol_for_capital(symbol)
        r = sess.get(f"{base}/api/v1/markets/{epic}", timeout=10)
        if r.status_code == 429:
            # kevyt backoff ettei tukita rajapintaa
            _CAP_PRICE_CACHE['retry_after'] = now + 10
            try:
                log(f"[PRICE] 429 rate-limited for {symbol}; backing off 10s")
            except Exception:
                print("[PRICE] 429 rate-limited; backoff 10s")
            return (None, None)
        if r.status_code != 200:
            try:
                log(f"[PRICE] FAIL {symbol} {r.status_code} {r.text[:200]}")
            except Exception:
                print("[PRICE] FAIL", symbol, r.status_code, r.text[:200])
            return (None, None)
        j = r.json()
        bid = safe_float(j.get('snapshot', {}).get('bid'))
        ask = safe_float(j.get('snapshot', {}).get('offer'))
        # tallenna cacheen
        d[symbol] = {'bid': bid, 'ask': ask, 'ts': now}
        try:
            log(f"[PRICE] {symbol} -> {map_symbol_for_capital(symbol)} bid={bid} ask={ask}")
        except Exception:
            pass
        return (bid, ask)
    except Exception as e:
        try:
            log(f"[PRICE] REST fallback error for {symbol}: {e!r}")
        except Exception:
            print("[PRICE] REST fallback error:", e)
        return (None, None)

def get_bid_ask(symbol: str, sess=None, base=None):
    """
    Palauta (bid, ask) Capital.comista annetulle symbolille.
    - EPIC ratkaistaan tools.epic_resolver.resolve_epic(symbol) ja CAPITAL_EPIC_<SYMBOL> env:llä.
    - Jos sess/base puuttuu, haetaan ne capital_rest_login():lla.
    - Palauttaa tuple (bid, ask) tai (None, None).
    """
    try:
        from tools import epic_resolver
        from tools import live_daemon as _ld  # itse moduuli (cap login)
    except Exception:
        return (None, None)

    # Session & base
    if sess is None or base is None:
        try:
            sess, base = _ld.capital_rest_login(force=False)
        except Exception:
            return (None, None)
    if not sess or not base:
        return (None, None)

    # EPIC
    try:
        epic = epic_resolver.resolve_epic(symbol)
    except Exception:
        epic = (symbol or '').upper()

    # Rakennetaan pyyntö
    try:
        hdr = dict(getattr(sess, "headers", {}))
        hdr.setdefault("Accept", "application/json")
        hdr.setdefault("Content-Type", "application/json")
        hdr["VERSION"] = "3"
        url = f"{base.rstrip('/')}/api/v1/prices/{epic}?resolution=MINUTE&max=1"
        r = sess.get(url, headers=hdr, timeout=10)
        r.raise_for_status()
        js = r.json() or {}
        arr = js.get("prices") or js.get("content") or []
        if not arr:
            return (None, None)
        p = arr[-1]

        # Capitalin muodot: closePrice/openPrice/etc = {'bid': x, 'ask': y}
        def _pick_bid_ask(d):
            if isinstance(d, dict):
                b = d.get("bid"); a = d.get("ask")
                if isinstance(b,(int,float)) and isinstance(a,(int,float)):
                    return (b, a)
            return (None, None)

        # Yritä yleisimmät kentät
        for key in ("closePrice","openPrice","highPrice","lowPrice"):
            b,a = _pick_bid_ask(p.get(key) or {})
            if b is not None and a is not None:
                return (b, a)

        # Fallback: jos taso on suoraan p['bid'], p['ask']
        b = p.get("bid"); a = p.get("ask")
        if isinstance(b,(int,float)) and isinstance(a,(int,float)):
            return (b, a)

        return (None, None)
    except Exception:
        return (None, None)
