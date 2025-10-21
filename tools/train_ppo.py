#!/usr/bin/env python3
import os, sys, logging, time
from pathlib import Path

# Lisää projektihakemisto Python-polkuun
ROOT = Path("/root/pro_botti")
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "agents"))
sys.path.append(str(ROOT / "tools"))

# Nyt voi tuoda meta_agent ja tele
from agents.meta_agent import train_ppo
from tools.tele import send

LOGFILE = ROOT / "logs" / "ppo_train.log"
LOGFILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.info("=== PPO retrain aloitettu ===")
start = time.time()
try:
    model = train_ppo()
    msg = "[PPO] ✅ Uusi PPO-agentti koulutettu ja tallennettu."
    logging.info(msg)
    send("🤖 PPO retrain completed successfully ✅")
except Exception as e:
    err = f"[PPO] ❌ Virhe koulutuksessa: {e}"
    logging.exception(err)
    send(f"⚠️ PPO retrain failed: {e}")
finally:
    elapsed = time.time() - start
    logging.info(f"=== PPO retrain valmis ({elapsed:.1f}s) ===")
