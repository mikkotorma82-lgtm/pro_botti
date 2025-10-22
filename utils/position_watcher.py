import time
from loguru import logger
from tools.position_guard import guard_positions
from tools.tele import send as send_telegram

class PositionWatcher:
    def __init__(self, broker, check_interval=30, guard_config=None):
        self.broker = broker
        self.check_interval = check_interval
        self.guard_config = guard_config if guard_config else {}
        self.last_check = 0

    def should_check(self):
        now = time.time()
        if now - self.last_check > self.check_interval:
            self.last_check = now
            return True
        return False

    def check_and_manage_positions(self, symbols):
        results = []
        try:
            positions = self.broker.get_positions()
            # Edge-case: tukee useita positioformaatteja
            if not isinstance(positions, list):
                positions = list(positions.values())
            for pos in positions:
                symbol = pos.get("symbol")
                if symbol not in symbols:
                    continue
                # Kutsu guard_positions - TP/SL/Trail ja riskienhallinta
                guard_result = guard_positions(self.broker, pos, self.guard_config)
                msg = f"PositionWatcher: {symbol} {pos.get('side')} qty={pos.get('qty')} guard={guard_result}"
                logger.info(msg)
                send_telegram(msg)
                results.append({"symbol": symbol, "result": guard_result})
        except Exception as e:
            logger.error(f"PositionWatcher error: {e}")
            send_telegram(f"[ERROR] PositionWatcher: {e}")
        return results

def create_position_watcher(broker, check_interval=30, guard_config=None):
    """
    Factory-funktio, helpottaa laajennettavuutta.
    """
    return PositionWatcher(broker, check_interval, guard_config)
