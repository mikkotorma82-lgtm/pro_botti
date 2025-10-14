#!/usr/bin/env python3
"""
Backfill historical data from exchanges
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import yaml
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.binance import fetch_ohlcv


def run_backfill(config_path='config.yaml'):
    """
    Fetch and store historical OHLCV data for configured symbols and timeframes
    """
    # Load configuration
    with open(ROOT / config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    symbols = config['trading']['symbols']
    timeframes = config['trading']['timeframes']
    history_years = config['data']['history_years']
    data_path = Path(config['data']['history_path'])
    data_path.mkdir(parents=True, exist_ok=True)
    
    print("📊 Starting backfill...")
    
    for symbol in symbols:
        for tf in timeframes:
            print(f"\n⏳ Fetching {symbol} {tf}...")
            
            try:
                # Calculate how far back to fetch
                years = history_years.get(tf, 2)
                since = datetime.now() - timedelta(days=years * 365)
                
                # Fetch data
                df = fetch_ohlcv(symbol, tf, since=since)
                
                if df is not None and len(df) > 0:
                    # Save to parquet
                    output_file = data_path / f"{symbol}_{tf}.parquet"
                    df.to_parquet(output_file, index=False)
                    print(f"✅ Saved {len(df)} candles to {output_file}")
                else:
                    print(f"⚠️  No data received for {symbol} {tf}")
                    
            except Exception as e:
                print(f"❌ Error fetching {symbol} {tf}: {e}")
                continue
    
    print("\n✅ Backfill complete!")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Backfill historical data')
    parser.add_argument('--config', default='config.yaml', help='Config file')
    args = parser.parse_args()
    
    run_backfill(args.config)
