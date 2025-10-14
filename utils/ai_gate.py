"""
AI Gate - Decision making with model predictions
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from joblib import load


ROOT = Path("/home/runner/work/pro_botti/pro_botti")
MODELS_DIR = ROOT / "models"


def load_model_and_meta(symbol: str, timeframe: str) -> Tuple[Any, Dict]:
    """
    Load trained model and metadata
    
    Args:
        symbol: Trading symbol
        timeframe: Timeframe
    
    Returns:
        (model, metadata) tuple
    """
    model_file = MODELS_DIR / f"pro_{symbol}_{timeframe}.joblib"
    meta_file = MODELS_DIR / f"pro_{symbol}_{timeframe}.json"
    
    model = None
    meta = {}
    
    if model_file.exists():
        try:
            model = load(model_file)
        except Exception as e:
            print(f"⚠️  Error loading model: {e}")
    
    if meta_file.exists():
        try:
            with open(meta_file, 'r') as f:
                meta = json.load(f)
        except Exception as e:
            print(f"⚠️  Error loading metadata: {e}")
    
    return model, meta


def get_thresholds(meta: Dict, config: Dict) -> Tuple[float, float]:
    """
    Get buy/sell thresholds from config or metadata
    
    Args:
        meta: Model metadata
        config: Configuration dict
    
    Returns:
        (buy_threshold, sell_threshold) tuple
    """
    # Default thresholds
    buy_thr = config.get('trading', {}).get('buy_threshold', 0.52)
    sell_thr = config.get('trading', {}).get('sell_threshold', 0.48)
    
    # Override from model metadata if available
    if 'buy_threshold' in meta:
        buy_thr = meta['buy_threshold']
    if 'sell_threshold' in meta:
        sell_thr = meta['sell_threshold']
    
    return buy_thr, sell_thr


def gate_decision(
    symbol: str,
    timeframe: str,
    features: Any,
    config: Dict,
    side_hint: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Make trading decision using AI model
    
    Args:
        symbol: Trading symbol
        timeframe: Timeframe
        features: Feature row (pandas Series or dict)
        config: Configuration dict
        side_hint: Optional side hint ('BUY' or 'SELL')
    
    Returns:
        (decision, details) where decision is 'BUY', 'SELL', or 'HOLD'
    """
    # Load model and metadata
    model, meta = load_model_and_meta(symbol, timeframe)
    
    if model is None:
        return 'HOLD', {
            'reason': 'No model available',
            'confidence': 0.0,
            'symbol': symbol,
            'timeframe': timeframe
        }
    
    # Get thresholds
    buy_thr, sell_thr = get_thresholds(meta, config)
    
    try:
        # Prepare features
        if hasattr(features, 'to_dict'):
            features_dict = features.to_dict()
        else:
            features_dict = dict(features)
        
        # Remove non-feature columns
        excluded = ['time', 'target', 'symbol', 'timeframe']
        feature_values = [v for k, v in features_dict.items() if k not in excluded]
        
        # Get feature names from metadata
        feature_names = meta.get('feature_names', [])
        
        if not feature_names:
            # Fallback: use all numeric features
            feature_values = [v for v in feature_values if isinstance(v, (int, float))]
        
        # Reshape for prediction
        import numpy as np
        X = np.array(feature_values).reshape(1, -1)
        
        # Get prediction probability
        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(X)[0]
            confidence = float(proba[1])  # Probability of class 1 (UP)
        else:
            # Fallback to binary prediction
            pred = model.predict(X)[0]
            confidence = 1.0 if pred == 1 else 0.0
        
        # Make decision based on thresholds
        decision = 'HOLD'
        reason = 'Confidence below thresholds'
        
        if confidence >= buy_thr:
            decision = 'BUY'
            reason = f'Confidence {confidence:.3f} >= buy threshold {buy_thr}'
        elif confidence <= sell_thr:
            decision = 'SELL'
            reason = f'Confidence {confidence:.3f} <= sell threshold {sell_thr}'
        
        # Apply side hint if provided
        if side_hint and side_hint in ['BUY', 'SELL']:
            if decision != side_hint and decision != 'HOLD':
                reason += f' (overridden by hint: {side_hint})'
            decision = side_hint
        
        details = {
            'decision': decision,
            'confidence': confidence,
            'buy_threshold': buy_thr,
            'sell_threshold': sell_thr,
            'reason': reason,
            'symbol': symbol,
            'timeframe': timeframe,
            'model_score': meta.get('test_score', 0.0),
            'features_used': len(feature_values)
        }
        
        return decision, details
        
    except Exception as e:
        return 'HOLD', {
            'reason': f'Error in prediction: {str(e)}',
            'confidence': 0.0,
            'symbol': symbol,
            'timeframe': timeframe,
            'error': str(e)
        }


if __name__ == '__main__':
    # Test AI gate
    print("Testing AI gate decision making...")
    
    # Create mock features
    import pandas as pd
    features = pd.Series({
        'close': 50000,
        'returns': 0.01,
        'rsi': 55,
        'macd': 100,
        'ema_fast': 50100,
        'ema_slow': 49900,
        'volume': 1000000
    })
    
    config = {
        'trading': {
            'buy_threshold': 0.52,
            'sell_threshold': 0.48
        }
    }
    
    decision, details = gate_decision('BTCUSDT', '1h', features, config)
    print(f"\nDecision: {decision}")
    print(f"Details: {json.dumps(details, indent=2)}")
    print("\n✅ AI gate test complete")
