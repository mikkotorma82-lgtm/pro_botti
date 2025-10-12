# /root/pro_botti/tools/patch_live_pick_size.py
import re, sys, os

LIVE_PATH = "/root/pro_botti/tools/live_daemon.py"

def read(p): 
    with open(p, encoding="utf-8") as f: 
        return f.read()

def write(p, s):
    with open(p, "w", encoding="utf-8") as f: 
        f.write(s)

def ensure_import(src: str) -> str:
    if "from tools.position_sizer import calc_order_size" in src:
        return src
    return src.replace(
        "from tools.instrument_loader import load_instruments",
        "from tools.instrument_loader import load_instruments\nfrom tools.position_sizer import calc_order_size, instr_info"
    )

NEW_PICK = r'''
def pick_size(symbol, sizes_map, default_size):
    """Riskipohjainen koko: free_balance * RISK_PCT * safety * leverage / price,
    pyöristetty instrumentin minimiin/steppiin. Fallback: default_size.
    Hakee tarvittaessa hinnan ja vapaan pääoman Capital API:sta."""
    import os
    free_src = "env"
    px_src = "env"
    # --- step/min_size konfigista
    info = {}
    try:
        info = sizes_map.get(symbol, {}) if isinstance(sizes_map, dict) else {}
    except Exception:
        info = {}
    try: step = float(info.get("step") or 0.0)
    except: step = 0.0
    try: minsz = float(info.get("min_size") or 0.0)
    except: minsz = 0.0

    # --- vapaa pääoma
    try: free = float(os.environ.get("CAP_FREE_BALANCE","0") or 0.0)
    except: free = 0.0

    # --- viime hinta
    px_env = os.environ.get(f"LASTPX_{symbol}", "") or os.environ.get("LASTPX", "")
    try: px = float(px_env or "0")
    except: px = 0.0

    # --- jos puuttuu, hae Capital API:sta
    if free <= 0 or px <= 0:
        try:
            from tools.capital_client import CapitalClient
            cli = CapitalClient(); cli.login_session()
            if px <= 0:
                v = cli.last_price(symbol)
                if v: 
                    px = float(v)
                    px_src = "api"
            if free <= 0:
                acc = cli.account_info()
                if isinstance(acc, dict) and "accounts" in acc:
                    for a in acc["accounts"]:
                        if a.get("preferred") or a.get("status") == "ENABLED":
                            free = float(a.get("balance", {}).get("available", 0.0)); break
                    free_src = "api"
        except Exception:
            pass

    # riskiparametrit
    try: risk_pct = float(os.environ.get("RISK_PCT","0.10"))
    except: risk_pct = 0.10
    try: safety = float(os.environ.get("RISK_SAFETY","0.95"))
    except: safety = 0.95

    # jos ei vieläkään dataa → default
    if free <= 0 or px <= 0:
        try:
            print(f"[SIZE] {symbol} px={px}({px_src}) free={free}({free_src}) risk={risk_pct} safety={safety} step={step} min={minsz} -> size={float(default_size)} [fallback-default]", flush=True)
        except Exception:
            pass
        return float(default_size)

    size = calc_order_size(symbol=symbol, price=px, free_balance=free,
                           risk_pct=risk_pct, min_size=minsz, step=step,
                           safety_mult=safety)
    try:
        print(f"[SIZE] {symbol} px={px}({px_src}) free={free}({free_src}) risk={risk_pct} safety={safety} step={step} min={minsz} -> size={size}", flush=True)
    except Exception:
        pass
    return float(size if size>0 else default_size)
'''.lstrip()

def replace_pick_size(src: str) -> str:
    m = re.search(r"\ndef\s+pick_size\s*\([^)]*\):\n", src)
    if not m:
        raise SystemExit("ERROR: pick_size() ei löytynyt live_daemon.py:stä.")
    start = m.start()+1
    m2 = re.search(r"\n(def\s+\w+\s*\(|if __name__\s*==\s*['\"]__main__['\"]\s*:)", src[m.end()-1:], re.M)
    end = (m.end()-1 + m2.start()) if m2 else len(src)
    return src[:start] + NEW_PICK + "\n" + src[end:]

def main():
    src = read(LIVE_PATH)
    src = ensure_import(src)
    src = replace_pick_size(src)
    write(LIVE_PATH, src)
    print("OK: live_daemon.py päivitetty (pick_size + [SIZE]-logi).")

if __name__ == "__main__":
    main()
