#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

STATE = Path(__file__).resolve().parents[1] / "state"
META_AGG = STATE / "agg_models_meta.json"
META_REG = META_AGG if META_AGG.exists() else (STATE / "models_meta.json")
PRO_AGG  = STATE / "agg_models_pro.json"
PRO_REG  = PRO_AGG if PRO_AGG.exists() else (STATE / "models_pro.json")
SELECTED = STATE / "selected_universe.json"

def load(p: Path, default):
    try:
        return json.loads(p.read_text() or "{}")
    except Exception:
        return default

def main():
    meta_obj = load(META_REG, {})
    pro_obj  = load(PRO_REG, {})
    sel_obj  = load(SELECTED, {"rules":{}, "combos":[]})
    rows     = meta_obj.get("models", [])
    pro_rows = pro_obj.get("models", [])
    combos   = sel_obj.get("combos", [])
    rules    = sel_obj.get("rules", {})

    min_cvf     = float(rules.get("min_cvpf", 1.2))
    min_entries = int(rules.get("min_entries", 200))
    allow_15m   = bool(rules.get("allow_15m", False))
    max_tfs     = int(rules.get("max_tfs_per_symbol", 2))

    pro_set = {(r.get("symbol"), r.get("tf")) for r in pro_rows if r.get("strategy") == "CONSENSUS"}
    sel_set = {(r.get("symbol"), r.get("tf")) for r in combos}

    def cvpf_of(r): return float(r.get("cv_pf_score", r.get("auc_purged", 0.0)))
    def entries_of(r): return int(r.get("entries", 0))

    def reject_reasons(r):
        sym, tf = r["symbol"], r["tf"]
        cvpf = cvpf_of(r)
        ent  = entries_of(r)
        reasons=[]
        if cvpf < min_cvf: reasons.append("cvpf_below_rule")
        if ent  < min_entries: reasons.append("entries_below_rule")
        if (tf == "15m") and not allow_15m: reasons.append("15m_disabled")
        if (sym, tf) not in pro_set: reasons.append("no_PRO")
        return reasons

    rows_sorted = sorted(rows, key=lambda r: (cvpf_of(r), entries_of(r)), reverse=True)

    print("Valintasäännöt:", {"min_cvpf":min_cvf,"min_entries":min_entries,"allow_15m":allow_15m,"max_tfs_per_symbol":max_tfs})
    print(f"META-lähde: {META_REG}")
    print(f"PRO-lähde:  {PRO_REG}")
    print(f"META_kombot={len(rows)} PRO_kombot={len(pro_rows)} valitut={len(combos)}\n")

    print(f"{'SYMBOL':12} {'TF':>3} {'cvPF':>6} {'entries':>7} {'PRO':>5} {'SELECTED':>9}  REASONS_IF_NOT_SELECTED")
    for r in rows_sorted:
        sym, tf = r["symbol"], r["tf"]
        cvpf    = cvpf_of(r)
        ent     = entries_of(r)
        has_pro = (sym, tf) in pro_set
        in_sel  = (sym, tf) in sel_set
        reasons = [] if in_sel else reject_reasons(r)
        print(f"{sym:12} {tf:>3} {cvpf:6.3f} {ent:7d} {str(has_pro):>5} {str(in_sel):>9}  {','.join(reasons)}")

    tops = [r for r in rows_sorted
            if cvpf_of(r) >= 2.0
            and entries_of(r) >= min_entries
            and (allow_15m or r['tf'] != '15m')]

    if tops:
        print("\nTOP (cv_pf>=2.0):")
        for r in tops[:100]:
            sym, tf = r["symbol"], r["tf"]
            cvpf    = cvpf_of(r)
            ent     = entries_of(r)
            has_pro = (sym, tf) in pro_set
            in_sel  = (sym, tf) in sel_set
            reasons = [] if in_sel else reject_reasons(r)
            print(f"  - {sym:12} {tf:>3} cv_pf={cvpf:.3f} entries={ent} selected={in_sel} has_PRO={has_pro} reasons={','.join(reasons) if reasons else '-'}")
    else:
        print("\nTOP (cv_pf>=2.0): ei yhtään, tämänhetkisillä säännöillä")

if __name__ == "__main__":
    main()
