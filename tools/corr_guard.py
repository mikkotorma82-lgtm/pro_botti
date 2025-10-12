import sys, json

GROUPS = {
  "USD":    ["EURUSD","GBPUSD","AUDUSD","NZDUSD","USDJPY","USDCAD","USDCHF"],
  "INDEX":  ["US500","US100"],
  "CRYPTO": ["BTCUSD","ETHUSD","XRPUSD","SOLUSD","ADAUSD"]
}
def group_of(sym:str)->str:
    u = sym.upper()
    for g, arr in GROUPS.items():
        if u in arr: return g
    return "OTHER"

def main():
    taken = set()
    for ln in sys.stdin:
        ln = ln.strip()
        if not ln: continue
        s = json.loads(ln)
        sym = (s.get("symbol") or s.get("ticker") or "").upper()
        if not sym: 
            continue
        g = group_of(sym)
        if g in taken:
            # droppaa päällekkäinen samaan ryhmään
            continue
        taken.add(g)
        print(json.dumps(s, ensure_ascii=False))
    sys.stdout.flush()

if __name__ == "__main__":
    main()
