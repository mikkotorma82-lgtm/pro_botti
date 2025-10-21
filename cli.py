
import argparse, pandas as pd, numpy as np, os, joblib, json
from pathlib import Path
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

def cmd_select_top(args):
    """Select top-K symbols based on evaluation metrics."""
    from datetime import datetime
    from utils.selector import select_top_symbols
    
    # Setup paths
    ROOT = Path(__file__).parent
    metrics_file = ROOT / "results" / "metrics" / f"metrics_{args.tf}.json"
    state_dir = ROOT / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    output_file = state_dir / "active_symbols.json"
    
    # Load metrics
    if not metrics_file.exists():
        logger.error(f"Metrics file not found: {metrics_file}")
        logger.info("Run evaluation first: python scripts/evaluate.py")
        return
    
    metrics_list = json.loads(metrics_file.read_text())
    logger.info(f"Loaded {len(metrics_list)} metrics from {metrics_file}")
    
    # Parse weights if provided
    weights = None
    if args.weights:
        try:
            weights = json.loads(args.weights)
        except Exception as e:
            logger.error(f"Invalid weights JSON: {e}")
            return
    
    # Select top symbols
    top_symbols = select_top_symbols(
        metrics_list,
        top_k=args.top_k,
        min_trades=args.min_trades,
        weights=weights
    )
    
    if not top_symbols:
        logger.warning("No symbols selected!")
        return
    
    # Prepare output
    selected_symbols = [s["symbol"] for s in top_symbols]
    
    output = {
        "generated_at": datetime.now().isoformat(),
        "timeframes": [args.tf],
        "top_k": args.top_k,
        "symbols": selected_symbols,
        "criteria": {
            "min_trades": args.min_trades,
            "weights": weights or {"sharpe": 0.5, "profit_factor": 0.3, "max_drawdown": 0.2, "winrate": 0.0},
            "lookback_days": args.lookback_days,
        },
        "details": top_symbols,
    }
    
    # Save
    output_file.write_text(json.dumps(output, indent=2))
    logger.info(f"Saved top-{args.top_k} selection to {output_file}")
    logger.info(f"Selected symbols: {selected_symbols}")

def cmd_show_active(args):
    """Show currently active symbols."""
    ROOT = Path(__file__).parent
    state_file = ROOT / "state" / "active_symbols.json"
    
    if not state_file.exists():
        logger.warning(f"No active symbols file found: {state_file}")
        logger.info("Run select-top first to generate active symbols")
        return
    
    data = json.loads(state_file.read_text())
    
    print("\n" + "="*60)
    print("ACTIVE TRADING SYMBOLS")
    print("="*60)
    print(f"Generated at: {data.get('generated_at', 'N/A')}")
    print(f"Top-K: {data.get('top_k', 'N/A')}")
    print(f"Timeframes: {', '.join(data.get('timeframes', []))}")
    print(f"\nSelected symbols ({len(data.get('symbols', []))}):")
    for sym in data.get("symbols", []):
        print(f"  • {sym}")
    
    print(f"\nCriteria:")
    criteria = data.get("criteria", {})
    for key, val in criteria.items():
        if key != "weights":
            print(f"  {key}: {val}")
    
    if "weights" in criteria:
        print(f"  Weights:")
        for k, v in criteria["weights"].items():
            print(f"    {k}: {v}")
    
    print("="*60 + "\n")

def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    t = sp.add_parser("train"); t.add_argument("--config", default="config.yaml"); t.set_defaults(func=cmd_train)
    b = sp.add_parser("backtest"); b.add_argument("--config", default="config.yaml"); b.set_defaults(func=cmd_backtest)
    l = sp.add_parser("live"); l.add_argument("--config", default="config.yaml"); l.set_defaults(func=cmd_live)
    
    # New commands
    st = sp.add_parser("select-top", help="Select top-K symbols based on metrics")
    st.add_argument("--tf", default="1h", help="Timeframe to evaluate")
    st.add_argument("--top-k", type=int, default=5, help="Number of top symbols to select")
    st.add_argument("--min-trades", type=int, default=25, help="Minimum trades threshold")
    st.add_argument("--lookback-days", type=int, default=365, help="Lookback days")
    st.add_argument("--weights", help="JSON string of weights (sharpe, profit_factor, max_drawdown, winrate)")
    st.set_defaults(func=cmd_select_top)
    
    sa = sp.add_parser("show-active", help="Show currently active symbols")
    sa.set_defaults(func=cmd_show_active)
    
    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help(); return
    args.func(args)

if __name__ == "__main__":
    main()
