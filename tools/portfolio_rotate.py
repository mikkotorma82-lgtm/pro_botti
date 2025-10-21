import os, csv, sys
from collections import defaultdict

PNL_CSV = "results/pnl.csv"          # oletus: ts,symbol,pnl
OUT     = "config/active_symbols.txt"
TOPN    = int(os.getenv("PORTFOLIO_TOPN","6"))

def read_pnl(path):
    d = defaultdict(float)
    if not os.path.exists(path): 
        return d
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            sym = (row.get("symbol") or "").upper()
            if not sym: 
                continue
            d[sym] += float(row.get("pnl", 0) or 0)
    return d

def main():
    pnl = read_pnl(PNL_CSV)
    if not pnl:
        base = ["EURUSD","GBPUSD","US500","US100","BTCUSD","ETHUSD"]
        open(OUT,"w").write(" ".join(base) + "\n")
        print("no_pnl -> wrote base", file=sys.stderr)
        return
    ranked = sorted(pnl.items(), key=lambda kv: kv[1], reverse=True)
    winners = [s for s,v in ranked if v>0][:TOPN]
    if not winners:
        winners = [s for s,_ in ranked[:TOPN]]
    open(OUT,"w").write(" ".join(winners) + "\n")
    print("wrote", winners, file=sys.stderr)

if __name__ == "__main__":
    main()
