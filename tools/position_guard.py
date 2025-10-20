from loguru import logger
from tools.tp_sl import compute_levels
from tools.tele import send as send_telegram

def guard_positions(broker, position, guard_config):
    """
    Valvoo yksittäisen position TP/SL/Trail-tasoja ja riskimallia.
    Palauttaa toimenpidelokin.
    """
    symbol = position.get("symbol")
    side = position.get("side")
    qty = position.get("qty")
    entry_px = position.get("entry_px")
    pos_id = position.get("id", None)

    # Riskimallin parametrit
    risk_model = guard_config.get("risk_model", "default")
    trail_enabled = guard_config.get("trail_enabled", True)
    telegram_enabled = guard_config.get("telegram", True)

    # Laske TP/SL/Trail
    levels = compute_levels(symbol, side, entry_px, risk_model=risk_model)
    sl = levels.get("sl")
    tp = levels.get("tp")
    trail = levels.get("trail")

    # Päivitä TP/SL/Trail tarvittaessa
    actions = []
    try:
        if position.get("sl") != sl:
            broker.update_stop_loss(pos_id, sl)
            actions.append(f"SL updated {sl}")
        if position.get("tp") != tp:
            broker.update_take_profit(pos_id, tp)
            actions.append(f"TP updated {tp}")
        if trail_enabled and position.get("trail") != trail:
            broker.update_trailing_stop(pos_id, trail)
            actions.append(f"Trail updated {trail}")
        if not actions:
            actions.append("No update")
        msg = f"guard_positions: {symbol} {side} qty={qty} actions={actions}"
        logger.info(msg)
        if telegram_enabled:
            send_telegram(msg)
        return actions
    except Exception as e:
        logger.error(f"guard_positions error: {e}")
        if telegram_enabled:
            send_telegram(f"[ERROR] guard_positions: {e}")
        return [f"error: {e}"]
