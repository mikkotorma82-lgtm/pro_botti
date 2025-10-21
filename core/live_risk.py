import sys, os, json, time, logging, pandas as pd
from datetime import datetime

ROOT = "/root/pro_botti"
sys.path.append(ROOT)
sys.path.append(os.path.join(ROOT, "tools"))

from tools.tele import send

RISK_FILE = "data/risk_state.json"
EQUITY_FILE = "data/equity_curve.csv"

def update_equity(pnl: float, balance: float):
    """Päivitä equity-curve ja riskitaso"""
    try:
        df = pd.read_csv(EQUITY_FILE) if os.path.exists(EQUITY_FILE) else pd.DataFrame(columns=["timestamp","balance","pnl"])
    except Exception:
        df = pd.DataFrame(columns=["timestamp","balance","pnl"])
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    new = pd.DataFrame([[now, balance, pnl]], columns=["timestamp","balance","pnl"])
    df = pd.concat([df, new], ignore_index=True)
    df.to_csv(EQUITY_FILE, index=False)
    logging.info(f"[EQUITY] Updated {EQUITY_FILE} ({len(df)} rows)")

    # Riskin säätö – mitä parempi tuotto, sitä korkeampi riskitaso (max 1.5x)
    risk = 1.0
    if len(df) > 10:
        recent = df.tail(10)
        mean_pnl = recent["pnl"].mean()
        risk = min(1.5, max(0.5, 1.0 + mean_pnl / 20.0))
    json.dump({"risk_level": risk, "timestamp": time.time()}, open(RISK_FILE, "w"), indent=2)
    logging.info(f"[RISK] Dynamic risk adjusted → {risk:.2f}")
    try:
        send(f"📈 Equity updated | Risk {risk:.2f} | PnL {pnl:+.2f} | Balance {balance:.2f}")
    except Exception:
        pass
