from __future__ import annotations
import json, os, csv
from pathlib import Path
from typing import List, Dict

METRICS = Path(
    "data/metrics/latest_metrics.csv"
)  # muodossa: symbol,tf,roi,sharpe,trades
ACTIVE_OUT = Path("data/universe_active.json")


def load_candidates() -> List[Dict]:
    if not METRICS.exists():
        return []
    out = []
    with METRICS.open() as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                out.append(
                    {
                        "symbol": row["symbol"].upper(),
                        "tf": row["tf"],
                        "roi": float(row["roi"]),
                        "sharpe": float(row.get("sharpe", "0") or 0),
                        "trades": int(row.get("trades", "0") or 0),
                    }
                )
            except:
                pass
    return out


def select_active(rows: List[Dict], min_roi=0.30, min_trades=80, min_sharpe=0.6):
    syms = set()
    for x in rows:
        if (
            x["roi"] >= min_roi
            and x["trades"] >= min_trades
            and x["sharpe"] >= min_sharpe
        ):
            syms.add(x["symbol"])
    return sorted(syms)


def main():
    rows = load_candidates()
    if not rows:
        ACTIVE_OUT.write_text(
            json.dumps(
                {
                    "active": None,
                    "note": "no metrics yet -> using full universe at runtime",
                },
                indent=2,
            )
        )
        print(json.dumps({"ok": True, "active_count": None, "note": "no metrics yet"}))
        return
    active = select_active(rows)
    ACTIVE_OUT.write_text(
        json.dumps(
            {"active": active, "note": "ROI>=30%, Sharpe>=0.6, trades>=80"}, indent=2
        )
    )
    print(json.dumps({"ok": True, "active_count": len(active)}))


if __name__ == "__main__":
    main()
