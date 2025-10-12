#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
model_report.py — listaa ja suodattaa koulutetut mallit (/models/pro_*.json)

Näyttää symbolin, TF:n, PF:n, win raten, ai_threshin yms. ja tarjoaa
suodatuksen (min PF), järjestyksen, ryhmittelyn sekä CSV-viennin.

Esimerkit:
  python /root/pro_botti/tools/model_report.py
  python /root/pro_botti/tools/model_report.py --min-pf 1.30 --sort pf
  python /root/pro_botti/tools/model_report.py --group-by tf --sort pf --top-n 10
  python /root/pro_botti/tools/model_report.py --csv /root/pro_botti/models/report.csv

Parametrit:
  --dir       Polku models-hakemistoon (oletus /root/pro_botti/models)
  --min-pf    Minimi PF -kynnys suodatukselle (oletus 1.0)
  --sort      Järjestys: pf|wr|symbol|tf|date (oletus pf)
  --desc      Käänteinen järjestys (oletus True)
  --group-by  Ryhmittely: none|symbol|tf (oletus none)
  --top-n     Näytä top-N riviä (suodatuksen jälkeen)
  --csv       Jos annettu, kirjoittaa tuloksen CSV:ksi tähän polkuun
"""

from __future__ import annotations
import os, sys, json, argparse, glob
from datetime import datetime
from typing import List, Dict, Any, Tuple

DEFAULT_MODELS_DIR = "/root/pro_botti/models"

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Report trained models (pro_*.json)")
    ap.add_argument("--dir", default=DEFAULT_MODELS_DIR, help="Models directory")
    ap.add_argument("--min-pf", type=float, default=1.0, dest="min_pf", help="Minimum PF filter")
    ap.add_argument("--sort", default="pf", choices=["pf","wr","symbol","tf","date"], help="Sort key")
    ap.add_argument("--desc", action="store_true", default=True, help="Sort descending (default)")
    ap.add_argument("--asc",  action="store_true", default=False, help="Override to ascending sort")
    ap.add_argument("--group-by", default="none", choices=["none","symbol","tf"], help="Group rows")
    ap.add_argument("--top-n", type=int, default=0, help="Show top-N rows after filtering (0=all)")
    ap.add_argument("--csv", default="", help="If set, write CSV to this path")
    return ap.parse_args()

def iso_parse(s: str) -> datetime | None:
    try:
        # tukee "Z" ja offsetit
        s = str(s)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None

def load_one(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta = meta if isinstance(meta, dict) else {}
        # jos tiedostonimestä voi päätellä symbol/tf, täydennä
        base = os.path.basename(path)
        if base.startswith("pro_") and base.endswith(".json") and "_" in base:
            core = base[len("pro_"):-len(".json")]
            # yritetään erottaa TF viimeisestä '_' kohdalta
            if "_" in core:
                sym = core[:core.rfind("_")]
                tf  = core[core.rfind("_")+1:]
                meta.setdefault("symbol", sym)
                meta.setdefault("tf", tf)
        # normalisoinnit
        meta["_file"] = path
        meta["pf"] = _to_float(meta.get("pf"))
        meta["win_rate"] = _to_float(meta.get("win_rate"))  # 0..1 tai 0..100, normalisoidaan myöhemmin
        meta["ai_thresh"] = _to_float(meta.get("ai_thresh"))
        meta["features"] = _to_int(meta.get("features"))
        meta["trained_at"] = meta.get("trained_at")
        meta["_dt"] = iso_parse(meta.get("trained_at") or "")
        return meta
    except Exception:
        return None

def _to_float(x) -> float | None:
    try:
        if x is None:
            return None
        if str(x).lower() == "nan":
            return None
        return float(x)
    except Exception:
        return None

def _to_int(x) -> int | None:
    try:
        if x is None: return None
        return int(x)
    except Exception:
        return None

def load_all(models_dir: str) -> List[Dict[str, Any]]:
    files = sorted(glob.glob(os.path.join(models_dir, "pro_*.json")))
    out: List[Dict[str, Any]] = []
    for p in files:
        m = load_one(p)
        if m: out.append(m)
    return out

def win_rate_pct(meta: Dict[str, Any]) -> float | None:
    wr = meta.get("win_rate")
    if wr is None:
        return None
    # tulokset voivat olla valmiiksi 0..1; jos >1, tulkitaan prosentiksi
    return float(wr*100.0) if wr <= 1.0000001 else float(wr)

def sort_key(meta: Dict[str, Any], key: str):
    if key == "pf":
        return (meta.get("pf") or -1.0)
    if key == "wr":
        wrp = win_rate_pct(meta)
        return (wrp if wrp is not None else -1.0)
    if key == "symbol":
        return (str(meta.get("symbol") or ""))
    if key == "tf":
        return (str(meta.get("tf") or ""))
    if key == "date":
        dt = meta.get("_dt")
        return dt or datetime.min
    return (meta.get("pf") or -1.0)

def group_key(meta: Dict[str, Any], how: str) -> str:
    if how == "symbol":
        return str(meta.get("symbol") or "")
    if how == "tf":
        return str(meta.get("tf") or "")
    return ""

def fit_width(text: str, width: int) -> str:
    s = str(text)
    if len(s) <= width:
        return s + " "*(width - len(s))
    return s[:max(0,width-1)] + "…"

def print_table(rows: List[Dict[str, Any]], group_by: str = "none"):
    # sarakeleveys
    w_sym, w_tf, w_pf, w_wr, w_thr, w_feat, w_date = 12, 6, 8, 8, 8, 8, 20

    def header():
        h = [
            fit_width("SYMBOL", w_sym),
            fit_width("TF", w_tf),
            fit_width("PF", w_pf),
            fit_width("WR%", w_wr),
            fit_width("THR", w_thr),
            fit_width("FEATS", w_feat),
            fit_width("TRAINED_AT", w_date),
        ]
        print(" ".join(h))

    def line(meta: Dict[str, Any]):
        sym = fit_width(meta.get("symbol",""), w_sym)
        tf  = fit_width(meta.get("tf",""), w_tf)
        pf  = meta.get("pf"); pf_s = f"{pf:.2f}" if isinstance(pf,(int,float)) and pf==pf else "-"
        wrp = win_rate_pct(meta); wr_s = f"{wrp:.1f}" if isinstance(wrp,(int,float)) and wrp==wrp else "-"
        thr = meta.get("ai_thresh"); thr_s = f"{thr:.2f}" if isinstance(thr,(int,float)) and thr==thr else "-"
        feats = meta.get("features"); feats_s = f"{feats:d}" if isinstance(feats,int) else "-"
        dt = meta.get("trained_at") or ""
        row = [
            sym, tf,
            fit_width(pf_s, w_pf),
            fit_width(wr_s, w_wr),
            fit_width(thr_s, w_thr),
            fit_width(feats_s, w_feat),
            fit_width(dt, w_date),
        ]
        print(" ".join(row))

    if group_by == "none":
        header()
        for m in rows:
            line(m)
        return

    # ryhmittely
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for m in rows:
        g = group_key(m, group_by)
        groups.setdefault(g, []).append(m)

    for gname in sorted(groups.keys()):
        print(f"\n## {group_by.upper()}: {gname}")
        header()
        for m in groups[gname]:
            line(m)

def write_csv(rows: List[Dict[str, Any]], path: str):
    import csv
    cols = ["symbol","tf","pf","win_rate_pct","ai_thresh","features","trained_at","file"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for m in rows:
            w.writerow([
                m.get("symbol",""),
                m.get("tf",""),
                _safe_num(m.get("pf")),
                _safe_num(win_rate_pct(m)),
                _safe_num(m.get("ai_thresh")),
                m.get("features",""),
                m.get("trained_at",""),
                m.get("_file",""),
            ])

def _safe_num(x):
    try:
        if x is None: return ""
        if isinstance(x, float) and x != x:  # NaN
            return ""
        return f"{float(x)}"
    except Exception:
        return ""

def main():
    args = parse_args()
    models_dir = args.dir

    rows = load_all(models_dir)
    total = len(rows)

    # suodatus PF:llä
    min_pf = float(args.min_pf)
    rows = [m for m in rows if (m.get("pf") or 0.0) >= min_pf]
    kept = len(rows)

    # järjestys
    key = args.sort
    descending = (not args.asc)  # --desc oletus True, --asc kääntää
    rows.sort(key=lambda m: sort_key(m, key), reverse=descending)

    # top-N
    if args.top_n and args.top_n > 0:
        rows = rows[:args.top_n]

    # tuloste
    print(f"[models] dir={models_dir}  total={total}  kept_pf≥{min_pf:.2f}={kept}")
    print(f"[sort] key={key}  order={'desc' if descending else 'asc'}  group_by={args.group_by}")
    print_table(rows, group_by=args.group_by)

    # CSV
    if args.csv:
        try:
            write_csv(rows, args.csv)
            print(f"\n[ok] CSV written -> {args.csv}")
        except Exception as e:
            print(f"[warn] CSV write failed: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
