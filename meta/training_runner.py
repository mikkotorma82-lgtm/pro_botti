import concurrent.futures as fut
import logging
from typing import Dict, Tuple, List

import ccxt

from meta.config import MetaConfig
from meta.symbols import load_symbols_file, normalize_symbols, filter_supported_symbols

log = logging.getLogger("meta.train")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def _has_enough_data(ex, symbol: str, tf: str, min_candles: int) -> Tuple[bool, int]:
    limit = min(max(min_candles, 200), 1000)
    try:
        ohlcv = ex.fetch_ohlcv(symbol, tf, limit=limit)
        n = len(ohlcv or [])
        return (n >= min_candles), n
    except Exception as e:
        log.warning("Data check failed for %s %s: %s", symbol, tf, e)
        return (False, 0)

def _train_one(symbol: str, tf: str, cfg: MetaConfig) -> Dict:
    ex_cls = getattr(ccxt, cfg.exchange_id)
    ex = ex_cls()
    enough, n = _has_enough_data(ex, symbol, tf, cfg.min_candles)
    if not enough:
        return {"symbol": symbol, "tf": tf, "status": "SKIP",
                "reason": f"not-enough-candles({n}<{cfg.min_candles})", "metrics": {}}
    try:
        from meta.ensemble import train_symbol_tf
    except Exception:
        try:
            from tools.meta_ensemble import train_symbol_tf
        except Exception as e:
            return {"symbol": symbol, "tf": tf, "status": "FAIL",
                    "reason": f"cannot-import-trainer:{type(e).__name__}:{e}", "metrics": {}}
    try:
        metrics = train_symbol_tf(symbol=symbol, timeframe=tf, **cfg.train_kwargs)
        return {"symbol": symbol, "tf": tf, "status": "OK", "reason": "", "metrics": metrics or {}}
    except Exception as e:
        return {"symbol": symbol, "tf": tf, "status": "FAIL",
                "reason": f"{type(e).__name__}:{e}", "metrics": {}}

def run_all(cfg: MetaConfig) -> Dict:
    log.info("Using symbols file: %s", cfg.symbols_file)
    raw_symbols = load_symbols_file(cfg.symbols_file)
    if cfg.max_symbols:
        raw_symbols = raw_symbols[: cfg.max_symbols]
    # Normalisoi (lisää /-merkki, aliasoi XBT jne.)
    norm_syms = normalize_symbols(cfg.exchange_id, raw_symbols)

    ex_cls = getattr(ccxt, cfg.exchange_id)
    ex = ex_cls()
    supported, rejected = filter_supported_symbols(ex, norm_syms)

    log.info("META-ensemble start symbols=%d (supported) rejected=%d tfs=%s models=%s",
             len(supported), len(rejected), ",".join(cfg.timeframes), ",".join(cfg.train_kwargs.get("models", [])))
    for s, r in rejected.items():
        log.warning("SKIP %s reason=%s", s, r)

    results: List[Dict] = []
    with fut.ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
        futures = [pool.submit(_train_one, s, tf, cfg) for s in supported for tf in cfg.timeframes]
        for f in fut.as_completed(futures):
            res = f.result(); results.append(res)
            tag = "✅" if res["status"] == "OK" else ("⚠️" if res["status"] == "SKIP" else "❌")
            if res["status"] == "OK":
                log.info("%s [META ENS OK] %s %s metrics=%s", tag, res["symbol"], res["tf"], res.get("metrics", {}))
            else:
                log.warning("%s [META ENS %s] %s %s reason=%s", tag, res["status"], res["symbol"], res["tf"], res["reason"])

    ok = [r for r in results if r["status"] == "OK"]
    sk = [r for r in results if r["status"] == "SKIP"]
    fl = [r for r in results if r["status"] == "FAIL"]
    log.info("📣 META-ensemble koulutus valmis | OK=%d SKIP=%d FAIL=%d", len(ok), len(sk), len(fl))

    return {"results": results, "rejected": rejected,
            "exchange": cfg.exchange_id, "timeframes": cfg.timeframes,
            "models": cfg.train_kwargs.get("models", [])}
