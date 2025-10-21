#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live_readiness_report.py — Mallien live-kelpoisuuden raportointi ja aktivointi.

Tekee:
- Lukee /root/pro_botti/models/pro_*.json (pf, win_rate, ai_thresholds, trained_at)
- Suodattaa PF-kynnyksen mukaan (oletus ≥ 1.30) ja tuottaa listan “liveen valmiit”
- (valinnainen) Päivittää config/active_symbols.txt automaattisesti (--write-active)
- Tulostaa ryhmittelyn TF:n mukaan (--group-by tf) tai symbolin mukaan (--group-by symbol)
- Ottaa huomioon klusterit (crypto / indices / fx / equities) ja voi rajoittaa top-N per klusteri

Esimerkit:
  python tools/live_readiness_report.py
  python tools/live_readiness_report.py --min-pf 1.40 --group-by tf --top-n 10
  python tools/live_readiness_report.py --write-active --per-cluster 6
"""

import os, sys, json, glob
from pathlib import Path
from typing import Dict, List, Tuple

ROOT   = Path("/root/pro_botti")
MODELS = ROOT / "models"
CONF   = ROOT / "config"
CONF.mkdir(parents=True, exist_ok=True)
ACTIVE_F = CONF / "active_symbols.txt"

def parse_model_path(p: Path) -> Tuple[str,str]:
    # pro_SYMBOL_TF.json
    name = p.stem  # pro_SYMBOL_TF
    try:
        _, sym, tf = name.split("_", 2)
        return sym, tf
    except Exception:
        return "", ""

def load_meta(p: Path) -> Dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def cluster_of(sym: str) -> str:
    s = sym.upper()
    if s.endswith("USDT") or s in ("BTCUSD","ETHUSD","SOLUSD","XRPUSD"): return "crypto"
    if s in ("US100","US500"): return "indices"
    if s in ("EURUSD","GBPUSD"): return "fx"
    return "equities"

def load_all(min_pf: float) -> List[Dict]:
    out = []
    for f in MODELS.glob("pro_*.json"):
        sym, tf = parse_model_path(f)
        if not sym or not tf:
            continue
        meta = load_meta(f)
        pf = float(meta.get("pf") or 0.0)
        wr = float(meta.get("win_rate") or 0.0)
        thr= meta.get("ai_thresholds") or {}
        if pf >= min_pf:
            out.append({
                "symbol": sym, "tf": tf, "pf": pf, "wr": wr,
                "thr": thr, "trained_at": meta.get("trained_at",""),
                "cluster": cluster_of(sym)
            })
    return sorted(out, key=lambda x: (x["pf"], x["wr"]), reverse=True)

def by_group(items: List[Dict], key: str) -> Dict[str, List[Dict]]:
    groups = {}
    for it in items:
        k = it.get(key, "")
        groups.setdefault(k, []).append(it)
    for k in groups:
        groups[k].sort(key=lambda x: (x["pf"], x["wr"]), reverse=True)
    return groups

def print_table(items: List[Dict], title: str=None):
    if title:
        print(f"\n## {title}")
    print(f"{'SYMBOL':<10} {'TF':<5} {'PF':>6} {'WR%':>7} {'CLUSTER':<9} {'TRH':<17} {'TRAINED_AT'}")
    for it in items:
        wrp = f"{it['wr']*100:.1f}%"
        thr = it['thr'] if it['thr'] else "-"
        print(f"{it['symbol']:<10} {it['tf']:<5} {it['pf']:>6.2f} {wrp:>7} {it['cluster']:<9} {str(thr):<17} {it['trained_at']}")

def write_active_symbols(items: List[Dict], per_cluster: int = 8):
    """
    Kirjoittaa active_symbols.txt – top-N per klusteri PF:n mukaan.
    """
    buckets = by_group(items, "cluster")
    chosen = []
    for cl, arr in buckets.items():
        chosen.extend(arr[:per_cluster])
    # järjestä PF:n mukaan
    chosen.sort(key=lambda x: (x["pf"], x["wr"]), reverse=True)
    # symbolit uniikiksi (sama symboli eri TF voi esiintyä useasti – live hakee kaikki TF:t envistä)
    uniq = []
    seen = set()
    for it in chosen:
        s = it["symbol"]
        if s not in seen:
            seen.add(s); uniq.append(s)
    ACTIVE_F.write_text("\n".join(uniq) + "\n", encoding="utf-8")
    print(f"\n[write-active] wrote {len(uniq)} symbols -> {ACTIVE_F}")

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Live readiness report")
    ap.add_argument("--models-dir", default=str(MODELS))
    ap.add_argument("--min-pf", type=float, default=1.30)
    ap.add_argument("--group-by", choices=["none","tf","symbol","cluster"], default="none")
    ap.add_argument("--top-n", type=int, default=0, help="Rajaa tuloste top-N riveihin (kokonaisuus tai per-ryhmä).")
    ap.add_argument("--write-active", action="store_true", help="Kirjoita config/active_symbols.txt top-per-cluster -valinnalla.")
    ap.add_argument("--per-cluster", type=int, default=8, help="Montako per klusteri active_symbols.txt:ään.")
    args = ap.parse_args()

    min_pf = float(args.min_pf)
    items = load_all(min_pf)
    print(f"[models] dir={args.models_dir}   kept_pf≥{min_pf:.2f}={len(items)}")

    if args.group_by == "none":
        out = items[:args.top_n] if args.top_n>0 else items
        print_table(out, title="READY FOR LIVE")
    else:
        groups = by_group(items, args.group_by)
        for gk, arr in groups.items():
            out = arr[:args.top_n] if args.top_n>0 else arr
            print_table(out, title=f"{args.group_by.upper()}: {gk}")

    if args.write_active:
        write_active_symbols(items, per_cluster=args.per_cluster)

if __name__ == "__main__":
    main()
