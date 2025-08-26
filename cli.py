
import argparse, pandas as pd, numpy as np, os, joblib
from loguru import logger
from config import load_config
from utils.logger import setup_logging
from data.loader import read_ohlcv_csv, resample, merge_features
from features.feature_engineering import build_features
from labels.labeling import make_labels
from models.trainer import train_walk_forward
from backtest.engine import run_backtest
from broker.paper import PaperBroker
from live.live_trader import run_live

def _csv_path(root, symbol, tf):
    return os.path.join(root, f"{symbol}_{tf}.csv")

def cmd_train(args):
    cfg = load_config(args.config)
    setup_logging(cfg.general.log_level)
    for sym in cfg.market.symbols:
        path = _csv_path(cfg.general.data_dir, sym, cfg.market.timeframe)
        df = read_ohlcv_csv(path, tz=cfg.market.exchange_tz)
        X = build_features(df, cfg.features)
        y = make_labels(df, cfg.labels).loc[X.index]
        oof = train_walk_forward(X, y, cfg.cv, cfg.model, os.path.join(cfg.general.model_dir, f"{sym}_{cfg.market.timeframe}.joblib"))
    logger.info("Training complete.")

def cmd_backtest(args):
    cfg = load_config(args.config)
    setup_logging(cfg.general.log_level)
    sym = cfg.market.symbols[0]
    path = _csv_path(cfg.general.data_dir, sym, cfg.market.timeframe)
    df = read_ohlcv_csv(path, tz=cfg.market.exchange_tz)
    X = build_features(df, cfg.features)
    from pathlib import Path
    bundle_path = Path(cfg.general.model_dir)/f"{sym}_{cfg.market.timeframe}.joblib"
    if not bundle_path.exists():
        logger.error(f"Train first: {bundle_path} missing")
        return
    bundle = joblib.load(bundle_path)
    used_cols = bundle["features"]
    X = X[used_cols].dropna()
    model = bundle["models"][-1]
    proba = pd.Series(model.predict_proba(X)[:,1], index=X.index)
    from strategy.alpha import signals_from_proba
    sig = signals_from_proba(proba)
    bt = run_backtest(df.loc[sig.index], sig, cfg.execution.fees_bp, cfg.execution.slippage_bp)
    logger.info(f"Backtest equity end={bt['equity'].iloc[-1]:.3f}")
    print(bt.tail(10))

def cmd_live(args):
    cfg = load_config(args.config)
    setup_logging(cfg.general.log_level)

    def data_fetch(symbol, tf):
        # expects CSV updated externally; here we just read
        path = _csv_path(cfg.general.data_dir, symbol, tf)
        try:
            return read_ohlcv_csv(path, tz=cfg.market.exchange_tz)
        except Exception:
            return None

    broker = PaperBroker(cash=cfg.backtest.initial_cash)
    def price_fn(symbol):
        df = data_fetch(symbol, cfg.market.timeframe)
        return None if df is None or df.empty else float(df["close"].iloc[-1])

    run_live(cfg, data_fetch, price_fn, broker)

def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    t = sp.add_parser("train"); t.add_argument("--config", default="config.yaml"); t.set_defaults(func=cmd_train)
    b = sp.add_parser("backtest"); b.add_argument("--config", default="config.yaml"); b.set_defaults(func=cmd_backtest)
    l = sp.add_parser("live"); l.add_argument("--config", default="config.yaml"); l.set_defaults(func=cmd_live)
    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help(); return
    args.func(args)

if __name__ == "__main__":
    main()
