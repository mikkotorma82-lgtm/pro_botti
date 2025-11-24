from typing import Dict

# Training history configuration:
# Changed to 3 years (1095 days) to reduce API load and prevent 429 errors
# Previously: 15m=730 days (2 years), 1h=1460 days (4 years), 4h=3650 days (10 years)
# The main reduction is for longer timeframes which were requesting excessive historical data
DEFAULT_TARGET_DAYS: Dict[str, int] = {
    "15m": 1095,   # 3 years (increased from 2 for consistency)
    "1h": 1095,    # 3 years (reduced from 4)
    "4h": 1095,    # 3 years (reduced from 10 - main reduction to prevent 429 errors)
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
