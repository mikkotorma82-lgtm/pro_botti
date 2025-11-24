from typing import Dict

# Training history configuration:
# Changed from 10 years to 3 years to reduce API load and prevent 429 errors
# 15m = 1095 days (3 years), 1h = 1095 days (3 years), 4h = 1095 days (3 years)
DEFAULT_TARGET_DAYS: Dict[str, int] = {
    "15m": 1095,   # 3 years
    "1h": 1095,    # 3 years
    "4h": 1095,    # 3 years
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
