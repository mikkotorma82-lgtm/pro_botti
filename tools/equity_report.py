#!/usr/bin/env python3
import sys, os, pandas as pd, matplotlib.pyplot as plt, logging

ROOT = "/root/pro_botti"
sys.path.append(ROOT)
sys.path.append(os.path.join(ROOT, "tools"))

from tools.tele import send, send_photo

EQUITY_FILE = "data/equity_curve.csv"
IMG_FILE = "data/equity_curve.png"
LOGFILE = "/root/pro_botti/logs/equity_report.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOGFILE), logging.StreamHandler()]
)

if not os.path.exists(EQUITY_FILE):
    send("❌ Ei equity dataa vielä (puuttuu CSV).")
    exit()

try:
    df = pd.read_csv(EQUITY_FILE)
except pd.errors.EmptyDataError:
    send("❌ Ei equity dataa vielä (tyhjä CSV).")
    exit()

if len(df) < 2:
    send("❌ Ei tarpeeksi dataa kuvaajalle.")
    exit()

plt.figure(figsize=(8,4))
plt.plot(df["timestamp"], df["balance"], label="Equity", color="dodgerblue")
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.title("CapitalBot Equity Curve")
plt.ylabel("Balance")
plt.legend()
plt.savefig(IMG_FILE)
logging.info(f"[EQUITY] Image saved: {IMG_FILE}")

if os.path.exists(IMG_FILE):
    send_photo(IMG_FILE, "📊 Daily Equity Curve")
else:
    send("⚠️ Ei kuvaa luotu (mahdollisesti tyhjä data).")
