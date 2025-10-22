#!/usr/bin/env python3
"""
Post-training evaluation script.
Evaluates trained models across all symbols and timeframes, calculates metrics.
"""
import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd
from loguru import logger
import joblib

# Setup paths
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.metrics import calculate_metrics


def load_env_list(key: str, default: str) -> List[str]:
    """Load comma-separated env variable as list."""
    val = os.environ.get(key, default)
    return [x.strip() for x in val.split(",") if x.strip()]


def get_symbols_and_tfs(args) -> tuple[List[str], List[str]]:
    """Get symbols and timeframes from args or env."""
    # Try args first
    if args.symbols:
        symbols = args.symbols
    else:
        # Try env
        symbols = load_env_list("SYMBOLS", "")
        if not symbols:
            # Try config.yaml
            try:
                import yaml
                cfg_path = ROOT / "config.yaml"
                if cfg_path.exists():
                    cfg = yaml.safe_load(cfg_path.read_text())
                    symbols = cfg.get("market", {}).get("symbols", [])
            except Exception:
                pass
    
    if args.timeframes:
        tfs = args.timeframes
    else:
        tfs = load_env_list("TFS", "")
        if not tfs:
            try:
                import yaml
                cfg_path = ROOT / "config.yaml"
                if cfg_path.exists():
                    cfg = yaml.safe_load(cfg_path.read_text())
                    tfs = cfg.get("train", {}).get("timeframes", ["1h"])
            except Exception:
                tfs = ["1h"]
    
    return symbols, tfs


def load_historical_data(symbol: str, tf: str, lookback_days: int) -> pd.DataFrame | None:
    """Load historical data for evaluation."""
    # Try various data locations
    data_paths = [
        ROOT / "data" / "history" / symbol / f"{symbol}_{tf}.parquet",
        ROOT / "data" / "history" / f"{symbol}_{tf}.parquet",
        ROOT / "data" / f"{symbol}_{tf}.parquet",
        ROOT / "data" / f"{symbol}_{tf}.csv",
    ]
    
    for path in data_paths:
        if not path.exists():
            continue
        
        try:
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path)
            
            # Filter by lookback
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
                df = df[df["time"] >= cutoff]
            
            logger.debug(f"Loaded {len(df)} rows for {symbol}_{tf} from {path}")
            return df
            
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            continue
    
    logger.warning(f"No data found for {symbol}_{tf}")
    return None


def load_model_and_metadata(symbol: str, tf: str) -> tuple[Any, Dict] | tuple[None, None]:
    """Load trained model and its metadata."""
    # Try various model locations
    model_paths = [
        ROOT / "models" / f"pro_{symbol}_{tf}.joblib",
        ROOT / "models" / f"ml_{symbol}_{tf}.joblib",
        ROOT / "models" / f"{symbol}_{tf}.joblib",
    ]
    
    for model_path in model_paths:
        if not model_path.exists():
            continue
        
        try:
            bundle = joblib.load(model_path)
            
            # Try to load metadata JSON
            meta_path = model_path.with_suffix(".json")
            meta = {}
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
            
            logger.debug(f"Loaded model for {symbol}_{tf} from {model_path}")
            return bundle, meta
            
        except Exception as e:
            logger.warning(f"Failed to load {model_path}: {e}")
            continue
    
    logger.warning(f"No model found for {symbol}_{tf}")
    return None, None


def evaluate_symbol_tf(
    symbol: str,
    tf: str,
    lookback_days: int = 365
) -> Dict[str, Any] | None:
    """
    Evaluate a single symbol+timeframe combination.
    
    Returns metrics dict or None if evaluation failed.
    """
    logger.info(f"Evaluating {symbol}_{tf}...")
    
    # Load model
    model_bundle, metadata = load_model_and_metadata(symbol, tf)
    if model_bundle is None:
        logger.warning(f"Skipping {symbol}_{tf}: no model found")
        return None
    
    # Load data
    df = load_historical_data(symbol, tf, lookback_days)
    if df is None or len(df) < 100:
        logger.warning(f"Skipping {symbol}_{tf}: insufficient data")
        return None
    
    try:
        # Build features (simple approach - use what's available)
        from features.feature_engineering import build_features
        feats = build_features(df, None)  # Use default features
        
        # Get model features
        if isinstance(model_bundle, dict):
            used_cols = model_bundle.get("features", [])
            models = model_bundle.get("models", [])
            if not models:
                logger.warning(f"No models in bundle for {symbol}_{tf}")
                return None
            model = models[-1]  # Use last model
        else:
            # Assume bundle is the model itself
            model = model_bundle
            used_cols = feats.columns.tolist()
        
        # Prepare data
        X = feats[used_cols].dropna()
        if len(X) == 0:
            logger.warning(f"No valid features for {symbol}_{tf}")
            return None
        
        # Get predictions
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)[:, 1]
        else:
            proba = model.predict(X)
        
        # Generate signals (simple threshold)
        signals = np.where(proba >= 0.55, 1, np.where(proba <= 0.45, -1, 0))
        
        # Calculate returns (approximate)
        close = df["close"].iloc[-len(signals):]
        returns = close.pct_change().values[1:]
        
        # Align and calculate PnL
        sig_aligned = signals[:-1]
        trade_returns = sig_aligned * returns
        
        # Calculate metrics
        metrics = calculate_metrics(trade_returns, sig_aligned)
        
        # Add symbol/tf info
        metrics["symbol"] = symbol
        metrics["tf"] = tf
        metrics["eval_bars"] = len(X)
        
        logger.info(
            f"  {symbol}_{tf}: trades={metrics['trades']}, "
            f"winrate={metrics['winrate']:.1f}%, "
            f"sharpe={metrics['sharpe']:.2f}, "
            f"pf={metrics['profit_factor']:.2f}"
        )
        
        return metrics
        
    except Exception as e:
        logger.error(f"Evaluation error for {symbol}_{tf}: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_metrics(metrics_list: List[Dict], tf: str, output_dir: Path):
    """Save metrics to JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save per-timeframe
    tf_file = output_dir / f"metrics_{tf}.json"
    tf_file.write_text(json.dumps(metrics_list, indent=2))
    logger.info(f"Saved {len(metrics_list)} metrics to {tf_file}")
    
    # Load and merge with all metrics
    all_file = output_dir / "metrics_all.json"
    all_metrics = []
    if all_file.exists():
        try:
            all_metrics = json.loads(all_file.read_text())
        except Exception:
            pass
    
    # Remove old entries for this tf
    all_metrics = [m for m in all_metrics if m.get("tf") != tf]
    
    # Add new entries
    all_metrics.extend(metrics_list)
    
    # Save combined
    all_file.write_text(json.dumps(all_metrics, indent=2))
    logger.info(f"Updated {all_file} with total {len(all_metrics)} entries")


def main():
    parser = argparse.ArgumentParser(description="Evaluate trained models")
    parser.add_argument("--symbols", nargs="+", help="Symbols to evaluate")
    parser.add_argument("--timeframes", nargs="+", help="Timeframes to evaluate")
    parser.add_argument("--lookback-days", type=int, default=365, help="Days of history to evaluate")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "metrics", help="Output directory")
    args = parser.parse_args()
    
    symbols, tfs = get_symbols_and_tfs(args)
    
    if not symbols:
        logger.error("No symbols specified. Use --symbols or set SYMBOLS env variable")
        sys.exit(1)
    
    logger.info(f"Evaluating {len(symbols)} symbols x {len(tfs)} timeframes")
    logger.info(f"Symbols: {symbols}")
    logger.info(f"Timeframes: {tfs}")
    logger.info(f"Lookback: {args.lookback_days} days")
    
    for tf in tfs:
        logger.info(f"\n{'='*60}")
        logger.info(f"Evaluating timeframe: {tf}")
        logger.info(f"{'='*60}")
        
        tf_metrics = []
        for symbol in symbols:
            metrics = evaluate_symbol_tf(symbol, tf, args.lookback_days)
            if metrics:
                tf_metrics.append(metrics)
        
        if tf_metrics:
            save_metrics(tf_metrics, tf, args.output_dir)
        else:
            logger.warning(f"No metrics collected for {tf}")
    
    logger.info("\n" + "="*60)
    logger.info("Evaluation complete!")
    logger.info("="*60)


if __name__ == "__main__":
    main()
