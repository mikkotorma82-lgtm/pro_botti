#!/usr/bin/env python3
import os, json, time, logging
from tools.tele import send

LOGFILE = "/root/pro_botti/logs/ppo_trigger.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler()
    ]
)

logging.info("=== PPO Trigger service start ===")

try:
    drift_data = json.load(open("data/model_drift.json"))
    drift = drift_data.get("drift", False)
    if drift:
        logging.warning("[TRIGGER] Drift havaittu – käynnistetään PPO retrain")
        send("⚙️ PPO retrain triggered by model drift 🔁")
        os.system("systemctl start pro_botti-ppo.service")
    else:
        logging.info("[TRIGGER] Ei driftia – ei retrainia tällä kertaa")
except Exception as e:
    logging.error(f"[TRIGGER] {e}")
