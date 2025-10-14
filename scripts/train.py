#!/usr/bin/env python3
"""
Train ML models on historical data
"""
import os
import sys
from pathlib import Path
import yaml
import pandas as pd
import numpy as np
from joblib import dump
import json

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.features import build_features
from utils.risk import calculate_metrics


def run_training(config_path='config.yaml'):
    """
    Train models for each symbol and timeframe
    """
    # Load configuration
    with open(ROOT / config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    symbols = config['trading']['symbols']
    timeframes = config['trading']['timeframes']
    data_path = Path(config['data']['history_path'])
    models_path = Path(config['data']['models_path'])
    models_path.mkdir(parents=True, exist_ok=True)
    
    model_type = config['training'].get('model_type', 'xgboost')
    test_size = config['training'].get('test_size', 0.2)
    
    print("🎯 Starting model training...")
    
    # Import ML libraries
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    
    if model_type == 'xgboost':
        try:
            import xgboost as xgb
            estimator = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        except ImportError:
            print("⚠️  XGBoost not available, falling back to RandomForest")
            from sklearn.ensemble import RandomForestClassifier
            estimator = RandomForestClassifier(n_estimators=100, random_state=42)
    else:
        from sklearn.ensemble import RandomForestClassifier
        estimator = RandomForestClassifier(n_estimators=100, random_state=42)
    
    for symbol in symbols:
        for tf in timeframes:
            print(f"\n📈 Training {symbol} {tf}...")
            
            try:
                # Load historical data
                data_file = data_path / f"{symbol}_{tf}.parquet"
                if not data_file.exists():
                    print(f"⚠️  Data file not found: {data_file}")
                    continue
                
                df = pd.read_parquet(data_file)
                
                # Build features
                df = build_features(df)
                df = df.dropna()
                
                if len(df) < 100:
                    print(f"⚠️  Not enough data points ({len(df)})")
                    continue
                
                # Create target: 1 if next candle closes higher, 0 otherwise
                df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
                df = df[:-1]  # Remove last row (no target)
                
                # Prepare features
                feature_cols = [c for c in df.columns if c not in ['time', 'target']]
                X = df[feature_cols].values
                y = df['target'].values
                
                # Split data
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=test_size, random_state=42, shuffle=False
                )
                
                # Build pipeline
                model = Pipeline([
                    ('scaler', StandardScaler()),
                    ('classifier', estimator)
                ])
                
                # Train
                print(f"   Training on {len(X_train)} samples...")
                model.fit(X_train, y_train)
                
                # Evaluate
                train_score = model.score(X_train, y_train)
                test_score = model.score(X_test, y_test)
                
                print(f"   Train accuracy: {train_score:.3f}")
                print(f"   Test accuracy: {test_score:.3f}")
                
                # Calculate risk metrics
                y_pred = model.predict(X_test)
                metrics = calculate_metrics(y_test, y_pred)
                
                # Save model
                model_file = models_path / f"pro_{symbol}_{tf}.joblib"
                dump(model, model_file)
                
                # Save metadata
                meta = {
                    'symbol': symbol,
                    'timeframe': tf,
                    'train_score': float(train_score),
                    'test_score': float(test_score),
                    'n_features': len(feature_cols),
                    'feature_names': feature_cols,
                    'metrics': metrics,
                    'trained_at': pd.Timestamp.now().isoformat()
                }
                
                meta_file = models_path / f"pro_{symbol}_{tf}.json"
                with open(meta_file, 'w') as f:
                    json.dump(meta, f, indent=2)
                
                print(f"✅ Model saved to {model_file}")
                
            except Exception as e:
                print(f"❌ Error training {symbol} {tf}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    print("\n✅ Training complete!")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Train trading models')
    parser.add_argument('--config', default='config.yaml', help='Config file')
    args = parser.parse_args()
    
    run_training(args.config)
