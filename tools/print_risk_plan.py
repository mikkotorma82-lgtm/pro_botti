# /root/pro_botti/tools/print_risk_plan.py
import os, sys
sys.path.append("/root/pro_botti")  # jotta 'tools' löytyy vaikka ajetaan suoraan
from tools.capital_client import CapitalClient
from tools.position_sizer import calc_order_size, instr_info

SYMS_FILE = "/root/pro_botti/config/active_symbols.txt"
symbols = [s.strip() for s in open(SYMS_FILE, "r", encoding="utf-8").read().split() if s.strip()]

risk_pct = float(os.getenv("RISK_PCT","0.10"))
safety   = float(os.getenv("RISK_SAFETY","0.95"))

c = CapitalClient(); c.login_session()
acc = c.account_info()
free = 0.0
if isinstance(acc, dict) and "accounts" in acc:
    for a in acc["accounts"]:
        if a.get("preferred") or a.get("status")=="ENABLED":
            free = float(a.get("balance",{}).get("available",0.0)); break

for sym in symbols:
    px = c.last_price(sym) or 1.0
    ii = instr_info(sym)
    step = 0.0  # lisää jos käytät sizes.jsonia
    size = calc_order_size(sym, px, free, risk_pct=risk_pct, min_size=ii.get("min_trade_size"), step=step, safety_mult=safety)
    print(f"{sym:8s} px={px:<12} free={free:<10.2f} lev={ii.get('leverage')} mf={ii.get('margin_factor')} -> size={size}")
