import logging, json, os, time
from datetime import datetime
from agents.meta_agent import update_weights
from tools.tele import send
from core.live_risk import update_equity

PNL_FILE = "data/pnl_history.json"
RISK_FILE = "data/risk_state.json"

def record_trade(symbol, pnl):
    """Kirjaa PnL ja päivitä meta-agentin painot"""
    data = {"symbol": symbol, "pnl": pnl, "timestamp": datetime.utcnow().isoformat()}
    try:
        os.makedirs("data", exist_ok=True)
        with open(PNL_FILE, "a") as f:
            f.write(json.dumps(data) + "\n")
        logging.info(f"[FEEDBACK] {symbol} PnL={pnl:.2f} kirjattu.")
        update_weights(pnl)
        update_equity(pnl, 10000 + pnl*100)
        _update_risk_level(pnl)
    except Exception as e:
        logging.error(f"[FEEDBACK] Virhe: {e}")

def _update_risk_level(pnl):
    """Säädä riskitasoa dynaamisesti PnL:n perusteella"""
    base = 1.0
    change = 1 + (pnl / 100.0)
    new_risk = max(0.5, min(1.5, base * change))
    state = {"timestamp": time.time(), "risk_level": new_risk}
    json.dump(state, open(RISK_FILE, "w"), indent=2)
    msg = f"📊 Risk level adjusted → {new_risk:.2f} (PnL {pnl:+.2f})"
    logging.info(msg)
    try: send(msg)
    except: pass
    if pnl < -5.0:
        _trigger_ppo_retrain()

def _trigger_ppo_retrain():
    """Käynnistä PPO retrain jos tappio liian suuri"""
    try:
        send("⚠️ Auto PPO retrain triggered (PnL < -5%)")
        os.system("systemctl start pro_botti-ppo.service")
    except Exception as e:
        logging.error(f"[PPO-TRIGGER] {e}")
