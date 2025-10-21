#!/usr/bin/env python3
import os, sys, time, subprocess, importlib.util, logging
from pathlib import Path

# --- Perusasetukset ja logitus ---
ROOT = Path("/root/pro_botti")
LOGDIR = ROOT / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)
LOGFILE = LOGDIR / "trader.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info("=== CapitalBot v7.0 Professional Suite käynnistyy ===")

# --- Palveluiden lista ---
SYSTEMD_SERVICES = [
    "pro_botti-history.service",
    "pro_botti-risk.service",
    "pro_botti-train.service",
    "pro_botti-meta.service",
    "pro_botti-monitor.service"
]

def start_services():
    """Käynnistä systemd-palvelut hallitusti"""
    for svc in SYSTEMD_SERVICES:
        try:
            subprocess.run(["systemctl", "restart", svc], check=False)
            logging.info(f"[OK] Käynnistetty palvelu: {svc}")
            time.sleep(1)
        except Exception as e:
            logging.warning(f"[WARN] Palvelua {svc} ei voitu käynnistää: {e}")

def module_exists(module_path: str) -> bool:
    return Path(module_path).exists()

def try_import(module_name: str, file_path: str):
    if not module_exists(file_path):
        logging.warning(f"[SKIP] {module_name} ei löydy ({file_path})")
        return None
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    logging.info(f"[LOAD] {module_name} ladattu")
    return mod

def initialize_risk_layer():
    """Portfolio risk & allokaatio"""
    mod = try_import("portfolio_risk", "core/portfolio_risk.py")
    if mod and hasattr(mod, "update_portfolio_state"):
        try:
            mod.update_portfolio_state()
            logging.info("[RISK] Portfolio-riskilaskenta suoritettu")
        except Exception as e:
            logging.error(f"[RISK] Virhe riskilaskennassa: {e}")

def initialize_meta_ai():
    """Meta AI-kerros ja agentit"""
    mod = try_import("meta_agent", "agents/meta_agent.py")
    if mod and hasattr(mod, "load_agents"):
        try:
            mod.load_agents()
            logging.info("[AI] Meta-agentit alustettu")
        except Exception as e:
            logging.error(f"[AI] Meta-agenttien alustus epäonnistui: {e}")

def initialize_monitor():
    """Mallien health monitorointi"""
    mod = try_import("model_monitor", "tools/model_monitor.py")
    if mod and hasattr(mod, "check_model_drift"):
        try:
            drift = mod.check_model_drift()
            logging.info(f"[MONITOR] Model drift: {drift}")
            if drift:
                logging.warning("[MONITOR] Mallidrift havaittu → retrain service käynnistetään")
                subprocess.run(["systemctl", "restart", "pro_botti-train.service"], check=False)
        except Exception as e:
            logging.error(f"[MONITOR] Virhe drift-tarkistuksessa: {e}")

def start_live_daemon():
    """Käynnistä live trading daemon"""
    try:
        subprocess.Popen(
            [str(ROOT / "venv/bin/python"), "-u", "-m", "tools.live_daemon"],
            cwd=ROOT
        )
        logging.info("[LIVE] Trading daemon käynnistetty")
    except Exception as e:
        logging.error(f"[LIVE] Virhe daemonin käynnistyksessä: {e}")

def main():
    start_services()
    initialize_risk_layer()
    initialize_meta_ai()
    initialize_monitor()
    start_live_daemon()
    logging.info("=== CapitalBot v7.0 valmis käyttöön ===")
    # Päälooppi jää prosessiin
    while True:
        time.sleep(300)
        logging.info("[HEARTBEAT] Bot running OK")

if __name__ == "__main__":
    main()
