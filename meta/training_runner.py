import concurrent.futures as fut
import logging
from typing import Dict, Tuple, List
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import ccxt

from meta.config import MetaConfig
from meta.symbols import load_symbols_file, normalize_symbols, filter_supported_symbols

log = logging.getLogger("meta.train")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def _tf_secs(tf: str) -> int:
    tf = tf.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1]) * 60
    if tf.endswith("h"):
        return int(tf[:-1]) * 3600
    if tf.endswith("d"):
        return int(tf[:-1]) * 86400
    raise ValueError(f"Unsupported timeframe: {tf}")

def _has_enough_data(ex, symbol: str, tf: str, min_candles: int) -> Tuple[bool, int]:
    """
    Kevyt tarkiste: haetaan viimeiset N kynttilää (raja 1000) ja tarkistetaan laskuri.
    Ei cachea: integroi oma datavarasto jos sellainen on.
    """
    limit = min(max(min_candles, 200), 1000)
    try:
        ohlcv = ex.fetch_ohlcv(symbol, tf, limit=limit)
        n = len(ohlcv or [])
        return (n >= min_candles), n
    except Exception as e:
        log.warning("Data check failed for %s %s: %s", symbol, tf, e)
        return (False, 0)

def _train_one(symbol: str, tf: str, cfg: MetaConfig) -> Dict:
    """
    Yksi (symbol, tf) -ajo. Kutsuu teidän koulutuslogiikkaa.
    Palauta strukturoitu tulos: status (OK/FAIL/SKIP), syy, mittarit.
    """
    # 1) Data check
    ex_cls = getattr(ccxt, cfg.exchange_id)
    ex = ex_cls()
    enough, n = _has_enough_data(ex, symbol, tf, cfg.min_candles)
    if not enough:
        return {
            "symbol": symbol, "tf": tf, "status": "SKIP",
            "reason": f"not-enough-candles({n}<{cfg.min_candles})", "metrics": {}
        }

    # 2) Varsinainen koulutus – vaihda tämä import teidän toteutukseen
    #    Esim. from meta.ensemble import train_symbol_tf
    try:
        from meta.ensemble import train_symbol_tf  # TODO: varmista tämä polku/nimi teillä
    except Exception:
        # Fallback: jos polku on eri, tee toinen import tai nosta virhe
        try:
            from tools.meta_ensemble import train_symbol_tf  # vaihtoehtoinen sijainti
        except Exception as e:
            return {
                "symbol": symbol, "tf": tf, "status": "FAIL",
                "reason": f"cannot-import-trainer:{type(e).__name__}:{e}", "metrics": {}
            }

    try:
        # train_symbol_tf odotetaan palauttavan dictin tai mittarit; sopeuta tarvittaessa
        metrics = train_symbol_tf(symbol=symbol, timeframe=tf, **cfg.train_kwargs)
        return {"symbol": symbol, "tf": tf, "status": "OK", "reason": "", "metrics": metrics or {}}
    except Exception as e:
        return {"symbol": symbol, "tf": tf, "status": "FAIL", "reason": f"{type(e).__name__}:{e}", "metrics": {}}

def run_all(cfg: MetaConfig) -> Dict:
    start_ts = datetime.now(tz=timezone.utc)
    # 0) Symbolit
    raw_symbols = load_symbols_file(cfg.symbols_file)
    if cfg.max_symbols:
        raw_symbols = raw_symbols[: cfg.max_symbols]
    symbols = normalize_symbols(cfg.exchange_id, raw_symbols)

    # 1) Tuetut/ei-tuetut
    ex_cls = getattr(ccxt, cfg.exchange_id)
    ex = ex_cls()
    supported, rejected = filter_supported_symbols(ex, symbols)

    log.info("META-ensemble start symbols=%d tfs=%s models=%s",
             len(supported), ",".join(cfg.timeframes), ",".join(cfg.train_kwargs.get("models", [])))
    if rejected:
        for s, r in rejected.items():
            log.warning("SKIP %s reason=%s", s, r)

    # 2) Rinnakkaisajo
    tasks = []
    results: List[Dict] = []
    with fut.ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
        for s in supported:
            for tf in cfg.timeframes:
                tasks.append(pool.submit(_train_one, s, tf, cfg))
        for t in fut.as_completed(tasks):
            res = t.result()
            results.append(res)
            tag = "✅" if res["status"] == "OK" else ("⚠️" if res["status"] == "SKIP" else "❌")
            if res["status"] == "OK":
                log.info("%s [META ENS OK] %s %s metrics=%s", tag, res["symbol"], res["tf"], res.get("metrics", {}))
            else:
                log.warning("%s [META ENS %s] %s %s reason=%s", tag, res["status"], res["symbol"], res["tf"], res["reason"])

    # 3) Yhteenveto
    ok = [r for r in results if r["status"] == "OK"]
    sk = [r for r in results if r["status"] == "SKIP"]
    fl = [r for r in results if r["status"] == "FAIL"]

    log.info("📣 META-ensemble koulutus valmis | OK=%d SKIP=%d FAIL=%d", len(ok), len(sk), len(fl))
    if sk:
        for r in sk:
            log.info("SKIP %s %s reason=%s", r["symbol"], r["tf"], r["reason"])
    if fl:
        for r in fl:
            log.info("FAIL %s %s reason=%s", r["symbol"], r["tf"], r["reason"])

    end_ts = datetime.now(tz=timezone.utc)
    return {
        "started": start_ts.isoformat(),
        "finished": end_ts.isoformat(),
        "results": results,
        "rejected": rejected,
        "exchange": cfg.exchange_id,
        "timeframes": cfg.timeframes,
        "models": cfg.train_kwargs.get("models", []),
    }

if __name__ == "__main__":
    # Mahdollistaa suoran ajon: python -m meta.training_runner
    cfg = MetaConfig()
    run_all(cfg)
