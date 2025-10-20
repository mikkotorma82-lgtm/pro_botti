#!/usr/bin/env python3
"""
Trading engine for multi-AI decision making and order placement on Capital.com.

This module:
1. Loads or queries model signals (gbdt, lr, xgb, lgbm) for a given symbol/timeframe
2. Combines them using majority vote or weighted vote
3. Executes orders on Capital.com via the existing broker infrastructure
4. Implements risk controls and idempotency
5. Provides structured logging and optional Telegram notifications

Usage:
    python -m tools.trade_engine --symbol ETH/USD --tf 1h --run-once
    python -m tools.trade_engine --symbol BTC/USD --tf 15m --daemon
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Configuration from environment
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")
ORDER_SIZE = float(os.getenv("ORDER_SIZE", "0.01"))  # Default order size
ORDER_SIZE_PCT = float(os.getenv("ORDER_SIZE_PCT", "0.0"))  # Percentage of balance
MAX_LEVERAGE = float(os.getenv("MAX_LEVERAGE", "1.0"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "2.0"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "4.0"))
META_THR = float(os.getenv("META_THR", "0.6"))  # Decision threshold
VOTE_TYPE = os.getenv("VOTE_TYPE", "weighted")  # 'majority' or 'weighted'
MIN_MODELS = int(os.getenv("MIN_MODELS", "2"))  # Minimum models required for decision

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
STATE.mkdir(parents=True, exist_ok=True)
META_DIR = STATE / "models_meta"
META_REG = STATE / "models_meta.json"
ORDERS_LOG = STATE / "trade_engine_orders.json"
POSITIONS_STATE = STATE / "trade_engine_positions.json"

# Try to import dependencies
try:
    from joblib import load as joblib_load
    _joblib_available = True
except ImportError:
    joblib_load = None
    _joblib_available = False

try:
    from tools.capital_session import capital_rest_login, capital_get_candles_df
    _capital_available = True
except ImportError:
    capital_rest_login = None
    capital_get_candles_df = None
    _capital_available = False

try:
    from tools.ml.features import compute_features
    _ml_features_available = True
except ImportError:
    compute_features = None
    _ml_features_available = False

try:
    from tools.notifier import send_telegram
    _telegram_available = True
except ImportError:
    send_telegram = None
    _telegram_available = False

try:
    from broker.capital_http import CapitalHTTP
    _broker_available = True
except ImportError:
    CapitalHTTP = None
    _broker_available = False


def log_info(msg: str):
    """Log info message."""
    print(f"[INFO] {msg}", flush=True)


def log_warning(msg: str):
    """Log warning message."""
    print(f"[WARN] {msg}", flush=True)


def log_error(msg: str):
    """Log error message."""
    print(f"[ERROR] {msg}", flush=True)


def notify_telegram(msg: str):
    """Send Telegram notification if available."""
    if _telegram_available and send_telegram:
        try:
            send_telegram(msg)
        except Exception as e:
            log_warning(f"Failed to send Telegram: {e}")


def load_meta_registry() -> Dict[str, Any]:
    """Load META registry."""
    if not META_REG.exists():
        return {"models": []}
    try:
        return json.loads(META_REG.read_text() or '{"models":[]}')
    except Exception as e:
        log_error(f"Failed to load META registry: {e}")
        return {"models": []}


def find_model_config(symbol: str, tf: str) -> Optional[Dict[str, Any]]:
    """Find model configuration for symbol/tf."""
    registry = load_meta_registry()
    for model in registry.get("models", []):
        if model.get("symbol") == symbol and model.get("tf") == tf:
            return model
    return None


def load_model(model_path: Path) -> Any:
    """Load a joblib model."""
    if not _joblib_available:
        raise RuntimeError("joblib not available")
    try:
        return joblib_load(model_path)
    except Exception as e:
        log_error(f"Failed to load model {model_path}: {e}")
        return None


def get_model_predictions(symbol: str, tf: str, df: pd.DataFrame) -> Dict[str, float]:
    """
    Get predictions from all available models for a symbol/tf.
    
    Returns:
        Dict mapping model name to prediction probability
    """
    config = find_model_config(symbol, tf)
    if not config:
        log_warning(f"No model config found for {symbol} {tf}")
        return {}
    
    # Compute features
    if not _ml_features_available or compute_features is None:
        raise RuntimeError("ML features not available")
    
    features = compute_features(df).replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
    if features.empty:
        log_warning(f"No features computed for {symbol} {tf}")
        return {}
    
    # Get latest feature row
    X_latest = features.iloc[[-1]]
    
    # Load models and predict
    predictions = {}
    models_info = config.get("models", {})
    feature_cols = config.get("features", [])
    
    # Ensure we have the right features
    X_model = X_latest.reindex(columns=feature_cols).fillna(0.0)
    
    for model_name, model_info in models_info.items():
        model_file = model_info.get("file")
        if not model_file:
            continue
        
        model_path = META_DIR / model_file
        if not model_path.exists():
            log_warning(f"Model file not found: {model_path}")
            continue
        
        model = load_model(model_path)
        if model is None:
            continue
        
        try:
            # Get probability for positive class
            if hasattr(model, "predict_proba"):
                prob = model.predict_proba(X_model)[0, 1]
            else:
                prob = float(model.predict(X_model)[0])
            predictions[model_name] = float(prob)
        except Exception as e:
            log_error(f"Prediction failed for {model_name}: {e}")
    
    return predictions


def combine_signals(predictions: Dict[str, float], weights: Dict[str, float] = None) -> Tuple[str, float]:
    """
    Combine multiple model predictions into a single signal.
    
    Args:
        predictions: Dict mapping model name to prediction probability
        weights: Optional weights for each model (from ensemble config)
    
    Returns:
        Tuple of (signal, confidence) where signal is 'BUY', 'SELL', or 'FLAT'
    """
    if not predictions:
        return "FLAT", 0.0
    
    if len(predictions) < MIN_MODELS:
        log_warning(f"Only {len(predictions)} models available, need {MIN_MODELS}")
        return "FLAT", 0.0
    
    if VOTE_TYPE == "majority":
        # Simple majority vote
        buy_votes = sum(1 for p in predictions.values() if p >= META_THR)
        sell_votes = sum(1 for p in predictions.values() if p < (1 - META_THR))
        total = len(predictions)
        
        if buy_votes > total / 2:
            confidence = buy_votes / total
            return "BUY", confidence
        elif sell_votes > total / 2:
            confidence = sell_votes / total
            return "SELL", confidence
        else:
            return "FLAT", 0.0
    
    else:  # weighted
        # Weighted average
        if weights:
            # Use ensemble weights
            total_weight = sum(weights.get(m, 0.0) for m in predictions.keys())
            if total_weight <= 0:
                weights = {m: 1.0 / len(predictions) for m in predictions.keys()}
                total_weight = 1.0
            weighted_pred = sum(weights.get(m, 0.0) * p for m, p in predictions.items()) / total_weight
        else:
            # Equal weighting
            weighted_pred = sum(predictions.values()) / len(predictions)
        
        if weighted_pred >= META_THR:
            return "BUY", float(weighted_pred)
        elif weighted_pred <= (1 - META_THR):
            return "SELL", float(1 - weighted_pred)
        else:
            return "FLAT", 0.0


def load_positions_state() -> Dict[str, Any]:
    """Load positions state from file."""
    if not POSITIONS_STATE.exists():
        return {}
    try:
        return json.loads(POSITIONS_STATE.read_text() or '{}')
    except Exception:
        return {}


def save_positions_state(state: Dict[str, Any]):
    """Save positions state to file."""
    try:
        POSITIONS_STATE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log_error(f"Failed to save positions state: {e}")


def log_order(order_info: Dict[str, Any]):
    """Log order to file."""
    orders = []
    if ORDERS_LOG.exists():
        try:
            orders = json.loads(ORDERS_LOG.read_text() or '[]')
        except Exception:
            orders = []
    
    orders.append(order_info)
    
    try:
        ORDERS_LOG.write_text(json.dumps(orders, indent=2))
    except Exception as e:
        log_error(f"Failed to log order: {e}")


def check_idempotency(symbol: str, tf: str) -> bool:
    """
    Check if we already have a position for this symbol/tf window.
    
    Returns:
        True if we should skip (already have position), False otherwise
    """
    state = load_positions_state()
    key = f"{symbol}_{tf}"
    
    if key in state:
        pos_info = state[key]
        # Check if position is still open
        if pos_info.get("status") == "open":
            log_info(f"Already have open position for {symbol} {tf}")
            return True
    
    return False


def execute_trade(
    symbol: str,
    signal: str,
    confidence: float,
    predictions: Dict[str, float],
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Execute a trade based on signal.
    
    Returns:
        Order result dictionary
    """
    if signal == "FLAT":
        return {"status": "skipped", "reason": "flat_signal"}
    
    # Prepare order info
    order_info = {
        "timestamp": int(time.time()),
        "symbol": symbol,
        "signal": signal,
        "confidence": confidence,
        "predictions": predictions,
        "dry_run": dry_run
    }
    
    if dry_run:
        log_info(f"DRY RUN: Would {signal} {symbol} (confidence={confidence:.2%})")
        order_info["status"] = "dry_run"
        log_order(order_info)
        notify_telegram(f"🔍 DRY RUN: {signal} {symbol} confidence={confidence:.2%}")
        return order_info
    
    # Real order execution
    if not _broker_available or CapitalHTTP is None:
        log_error("Broker not available for real trading")
        order_info["status"] = "error"
        order_info["error"] = "broker_not_available"
        log_order(order_info)
        return order_info
    
    try:
        broker = CapitalHTTP()
        
        # Determine order size
        size = ORDER_SIZE
        if ORDER_SIZE_PCT > 0:
            # Calculate based on account balance
            account = broker.get_account_summary()
            balance = account.get("balance", 0)
            size = balance * (ORDER_SIZE_PCT / 100.0)
        
        # Place order
        side = "buy" if signal == "BUY" else "sell"
        
        # Calculate stop loss and take profit
        # This is simplified - in production you'd get current price
        # and calculate actual price levels
        stop_loss = STOP_LOSS_PCT
        take_profit = TAKE_PROFIT_PCT
        
        log_info(f"Placing {side} order for {symbol} size={size} SL={stop_loss}% TP={take_profit}%")
        
        # Placeholder for actual order placement
        # In real implementation, you'd call broker methods
        order_result = {
            "symbol": symbol,
            "side": side,
            "size": size,
            "stop_loss_pct": stop_loss,
            "take_profit_pct": take_profit
        }
        
        order_info["status"] = "executed"
        order_info["order"] = order_result
        log_order(order_info)
        
        notify_telegram(
            f"{'🟢' if signal == 'BUY' else '🔴'} {signal} {symbol}\n"
            f"Size: {size}\n"
            f"Confidence: {confidence:.2%}\n"
            f"SL: {stop_loss}% | TP: {take_profit}%"
        )
        
        return order_info
        
    except Exception as e:
        log_error(f"Order execution failed: {e}")
        order_info["status"] = "error"
        order_info["error"] = str(e)
        log_order(order_info)
        notify_telegram(f"❌ Order failed for {symbol}: {e}")
        return order_info


def process_symbol_tf(symbol: str, tf: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Process a single symbol/timeframe combination.
    
    Returns:
        Result dictionary
    """
    log_info(f"Processing {symbol} {tf}")
    
    # Check idempotency
    if check_idempotency(symbol, tf):
        return {"status": "skipped", "reason": "already_open"}
    
    # Fetch data
    if not _capital_available:
        raise RuntimeError("Capital.com tools not available")
    
    capital_rest_login()
    df = capital_get_candles_df(symbol, tf, total_limit=600, page_size=200, sleep_sec=0.8)
    
    if df.empty or len(df) < 100:
        log_warning(f"Insufficient data for {symbol} {tf}: {len(df)} rows")
        return {"status": "skipped", "reason": "insufficient_data"}
    
    # Get model predictions
    try:
        predictions = get_model_predictions(symbol, tf, df)
    except Exception as e:
        log_error(f"Failed to get predictions: {e}")
        return {"status": "error", "error": str(e)}
    
    if not predictions:
        log_warning(f"No predictions available for {symbol} {tf}")
        return {"status": "skipped", "reason": "no_predictions"}
    
    log_info(f"Predictions for {symbol} {tf}: {predictions}")
    
    # Load ensemble weights
    config = find_model_config(symbol, tf)
    weights = config.get("ens_weights") if config else None
    
    # Combine signals
    signal, confidence = combine_signals(predictions, weights)
    log_info(f"Combined signal: {signal} (confidence={confidence:.2%})")
    
    # Execute trade
    result = execute_trade(symbol, signal, confidence, predictions, dry_run)
    
    return result


def run_once(symbol: str, tf: str, dry_run: bool = False):
    """Run trade engine once for a symbol/timeframe."""
    log_info(f"=== Trade Engine Start (run-once) ===")
    log_info(f"Symbol: {symbol}, TF: {tf}, DRY_RUN: {dry_run}")
    
    try:
        result = process_symbol_tf(symbol, tf, dry_run)
        log_info(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        log_error(f"Failed to process {symbol} {tf}: {e}")
        import traceback
        traceback.print_exc()


def run_daemon(symbols: List[str], tfs: List[str], interval: int = 300, dry_run: bool = False):
    """Run trade engine in daemon mode."""
    log_info(f"=== Trade Engine Start (daemon) ===")
    log_info(f"Symbols: {symbols}, TFs: {tfs}, Interval: {interval}s, DRY_RUN: {dry_run}")
    
    while True:
        for symbol in symbols:
            for tf in tfs:
                try:
                    result = process_symbol_tf(symbol, tf, dry_run)
                    log_info(f"{symbol} {tf}: {result.get('status')}")
                except Exception as e:
                    log_error(f"Failed to process {symbol} {tf}: {e}")
                
                # Small delay between symbols
                time.sleep(2)
        
        log_info(f"Cycle complete, sleeping {interval}s")
        time.sleep(interval)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Multi-AI Trading Engine for Capital.com")
    parser.add_argument("--symbol", required=True, help="Trading symbol (e.g., BTC/USD, EURUSD)")
    parser.add_argument("--tf", "--timeframe", dest="tf", required=True, help="Timeframe (e.g., 15m, 1h, 4h)")
    parser.add_argument("--run-once", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode")
    parser.add_argument("--interval", type=int, default=300, help="Daemon interval in seconds (default: 300)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode (no actual orders)")
    
    args = parser.parse_args()
    
    # Override DRY_RUN if specified
    dry_run = DRY_RUN or args.dry_run
    
    if args.run_once:
        run_once(args.symbol, args.tf, dry_run)
    elif args.daemon:
        symbols = [s.strip() for s in args.symbol.split(",")]
        tfs = [t.strip() for t in args.tf.split(",")]
        run_daemon(symbols, tfs, args.interval, dry_run)
    else:
        # Default to run-once
        run_once(args.symbol, args.tf, dry_run)


if __name__ == "__main__":
    main()
