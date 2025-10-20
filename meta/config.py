import os

def _split_csv(v, default):
    s = (v or "").strip()
    return [x.strip() for x in s.split(",") if x.strip()] if s else default

def _resolve_symbols_file():
    # 1) Ympäristömuuttuja voittaa
    env = os.getenv("META_SYMBOLS_FILE", "").strip()
    if env:
        return env
    # 2) Yleisimmät fallback-polut (WorkingDirectoryn alta)
    candidates = [
        "./symbols.txt",
        "./config/symbols.txt",
        "./data/symbols.txt",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # 3) Viimeinen yritys: absoluuttiset polut CWD:stä
    cwd = os.getcwd()
    for c in [os.path.join(cwd, "symbols.txt"),
              os.path.join(cwd, "config", "symbols.txt"),
              os.path.join(cwd, "data", "symbols.txt")]:
        if os.path.isfile(c):
            return c
    # 4) Palauta oletus (loader antaa selkeän virheen jos puuttuu)
    return "./symbols.txt"

class MetaConfig:
    def __init__(self):
        self.symbols_file = _resolve_symbols_file()
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
