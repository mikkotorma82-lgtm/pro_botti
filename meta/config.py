import os

def _split_csv(v, default):
    s = (v or "").strip()
    return [x.strip() for x in s.split(",") if x.strip()] if s else default

def _resolve_symbols_file():
    env = os.getenv("META_SYMBOLS_FILE", "").strip()
    if env:
        return env
    candidates = [
        "./symbols.txt",
        "./config/symbols.txt",
        "./data/symbols.txt",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    cwd = os.getcwd()
    for c in [os.path.join(cwd, "symbols.txt"),
              os.path.join(cwd, "config", "symbols.txt"),
              os.path.join(cwd, "data", "symbols.txt")]:
        if os.path.isfile(c):
            return c
    return "./symbols.txt"

class MetaConfig:
    def __init__(self):
        # Capital.com on tämän botin oletus (voit override: META_EXCHANGE_ID / EXCHANGE_ID)
        self.exchange_id = os.getenv("EXCHANGE_ID", os.getenv("META_EXCHANGE_ID", "capitalcom")).lower()

        # Symbolit
        self.symbols_file = _resolve_symbols_file()

        # Aikavälit
        self.timeframes = _split_csv(os.getenv("META_TFS"), ["15m", "1h", "4h"])

        # Rinnakkaisuus
        self.max_workers = int(os.getenv("META_PARALLEL", "4"))

        # Minimikynttilät per tf, ennen kuin ajetaan koulutus
        self.min_candles = int(os.getenv("META_MIN_CANDLES", "300"))

        # Valinnainen rajoitus testejä varten (0 = ei rajaa)
        self.max_symbols = int(os.getenv("META_MAX_SYMBOLS", "0")) or None

        # Jatketaanko vaikka yksittäinen pari kaatuisi
        self.continue_on_error = os.getenv("META_CONTINUE_ON_ERROR", "true").lower() in ("1", "true", "yes")

        # Kouluttajan import-polku muodossa "paketti.moduuli:funktio"
        # Tällä poistetaan kovakoodattu tools.meta_ensemble -riippuvuus.
        self.trainer_path = os.getenv("META_TRAINER_PATH", "tools.meta_ensemble:train_symbol_tf")

        # Trainerin lisäparametrit (voit ohjata env:llä)
        self.train_kwargs = {
            "ens_pf": float(os.getenv("META_ENS_PF", "1.0")),
            "thr": float(os.getenv("META_THR", "0.6")),
            "models": _split_csv(os.getenv("META_MODELS"), ["gbdt", "lr", "xgb", "lgbm"]),
        }
