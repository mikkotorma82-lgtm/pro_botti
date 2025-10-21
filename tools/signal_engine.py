import logging, random
from agents.meta_agent import get_meta_signal
from core.pnl_feedback import record_trade

def evaluate_signal(symbol, features):
    """Arvioi signaali ja palauta päätös"""
    meta = get_meta_signal(symbol, features)
    logging.info(f"[SIGNAL] {symbol} → {meta['decision']} (score={meta['meta_score']})")
    return meta

def report_trade_result(symbol, pnl):
    """Kun treidi suljetaan, päivitä agentin painot"""
    record_trade(symbol, pnl)
