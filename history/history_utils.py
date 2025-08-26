from typing import Dict

# Käyttäjän defaultit:
# 15m = 730 päivää, 1h = 1460 päivää, 4h = 3650 päivää
DEFAULT_TARGET_DAYS: Dict[str, int] = {
    "15m": 730,
    "1h": 1460,
    "4h": 3650,
}

def tf_to_seconds(tf: str) -> int:
    tf = tf.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1]) * 60
    if tf.endswith("h"):
        return int(tf[:-1]) * 3600
    if tf.endswith("d"):
        return int(tf[:-1]) * 86400
    raise ValueError(f"Tuntematon timeframe: {tf}")
