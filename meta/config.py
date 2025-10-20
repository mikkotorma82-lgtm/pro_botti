import os

def _split_csv(v, default):
    s = (v or "").strip()
    return [x.strip() for x in s.split(",") if x.strip()] if s else default

class MetaConfig:
    def __init__(self):
        self.symbols_file = os.getenv("META_SYMBOLS_FILE", "./symbols.txt")
        self.timeframes = _split_csv(os.getenv("META_TFS"), ["15m", "1h", "4h"])
        self.exchange_id = os.getenv("EXCHANGE_ID", os.getenv("META_EXCHANGE_ID", "kraken")).lower()
        self.max_workers = int(os.getenv("META_PARALLEL", "4"))
        self.min_candles = int(os.getenv("META_MIN_CANDLES", "300"))
        self.max_symbols = int(os.getenv("META_MAX_SYMBOLS", "0")) or None
        self.continue_on_error = os.getenv("META_CONTINUE_ON_ERROR", "true").lower() in ("1", "true", "yes")
        self.train_kwargs = {
            "ens_pf": float(os.getenv("META_ENS_PF", "1.0")),
            "thr": float(os.getenv("META_THR", "0.6")),
            "models": _split_csv(os.getenv("META_MODELS"), ["gbdt", "lr", "xgb", "lgbm"]),
        }
