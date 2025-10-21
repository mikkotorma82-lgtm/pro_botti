#!/usr/bin/env python3
import json, os, sys, time, logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path("/root/pro_botti")
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "tools"))

# lataa ympäristömuuttujat
load_dotenv(ROOT / "secrets.env", override=True)
import importlib.util, sys, os; sys.path.append("/root/pro_botti/tools"); tele = importlib.import_module("tele"); send = tele.send

PNL_FILE = ROOT / "data/pnl_history.json"
RISK_FILE = ROOT / "data/risk_state.json"
LOGFILE = ROOT / "logs/pnl_report.log"
REPORT_DIR = ROOT / "reports"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOGFILE), logging.StreamHandler()]
)

def read_json_lines(path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def summarize_pnl(period_days=1, save_monthly=False):
    """Laskee PnL-yhteenvedon ja (jos save_monthly) tallentaa sen tiedostoon"""
    records = read_json_lines(PNL_FILE)
    if not records:
        send("📅 Ei yhtään treidiä tällä aikajaksolla.")
        return

    helsinki = timezone(timedelta(hours=3))
    now = datetime.now(helsinki)
    cutoff = now - timedelta(days=period_days)
    sel = [r for r in records if datetime.fromisoformat(r["timestamp"]).astimezone(helsinki) >= cutoff]
    if not sel:
        send("📅 Ei yhtään treidiä valitulla aikavälillä.")
        return

    total = sum(r["pnl"] for r in sel)
    avg = total / len(sel)
    symbols = {}
    for r in sel:
        s = r["symbol"]
        symbols[s] = symbols.get(s, 0) + r["pnl"]
    top = sorted(symbols.items(), key=lambda x: -x[1])[:5]
    top_str = ", ".join([f"{s}({v:+.2f})" for s, v in top])
    risk = 1.0
    if RISK_FILE.exists():
        risk = json.load(open(RISK_FILE)).get("risk_level", 1.0)

    label = "Daily" if period_days == 1 else ("Weekly" if period_days == 7 else "Monthly")
    msg = (
        f"📅 {label} PnL Summary ({now.strftime('%H:%M')} Helsinki)\n"
        f"Period: last {period_days} day(s)\n"
        f"Trades: {len(sel)}\n"
        f"Profit: {total:+.2f} %\n"
        f"Average trade: {avg:+.3f} %\n"
        f"Risk level: {risk:.2f}\n"
        f"Top symbols: {top_str}"
    )

    logging.info(msg)
    send(msg)

    # kuukausiraportti talteen
    if save_monthly:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        file = REPORT_DIR / f"monthly_summary_{now.strftime('%Y-%m')}.txt"
        file.write_text(msg)
        logging.info(f"[MONTHLY] Summary saved to {file}")

if __name__ == "__main__":
    period = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    save_monthly = bool(len(sys.argv) > 2 and sys.argv[2] == "monthly")
    summarize_pnl(period, save_monthly)
