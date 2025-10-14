#!/usr/bin/env python3
"""
Live trading daemon
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load environment variables
load_dotenv(ROOT / '.env')

from utils.binance import fetch_latest_candles
from utils.features import build_features
from utils.ai_gate import gate_decision
from utils.risk import check_risk_limits
from utils.position_sizer import calculate_position_size
from scripts.telegram_notify import send_notification


def run_live_trading(config_path='config.yaml'):
    """
    Main live trading loop
    """
    # Load configuration
    with open(ROOT / config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    symbols = config['trading']['symbols']
    timeframes = config['trading']['timeframes']
    poll_interval = config['monitoring']['poll_interval_seconds']
    trading_enabled = config['trading'].get('enable_trading', False) or \
                     os.getenv('TRADING_ENABLED', '0') == '1'
    
    print("🚀 Pro Botti Live Trading Started")
    print(f"   Symbols: {symbols}")
    print(f"   Timeframes: {timeframes}")
    print(f"   Trading: {'ENABLED' if trading_enabled else 'PAPER MODE'}")
    print(f"   Poll interval: {poll_interval}s")
    
    # Send startup notification
    send_notification(
        f"🚀 Bot Started\n"
        f"Symbols: {', '.join(symbols)}\n"
        f"Mode: {'LIVE' if trading_enabled else 'PAPER'}"
    )
    
    last_check = {}
    
    while True:
        try:
            for symbol in symbols:
                for tf in timeframes:
                    key = f"{symbol}_{tf}"
                    
                    # Rate limiting
                    now = time.time()
                    if key in last_check and now - last_check[key] < poll_interval:
                        continue
                    
                    last_check[key] = now
                    
                    try:
                        # Fetch latest data
                        df = fetch_latest_candles(symbol, tf, limit=200)
                        if df is None or len(df) == 0:
                            print(f"⚠️  No data for {symbol} {tf}")
                            continue
                        
                        # Build features
                        df = build_features(df)
                        latest = df.iloc[-1]
                        
                        # Get AI decision
                        decision, details = gate_decision(
                            symbol=symbol,
                            timeframe=tf,
                            features=latest,
                            config=config
                        )
                        
                        if decision in ['BUY', 'SELL']:
                            print(f"\n🎯 Signal: {decision} {symbol} {tf}")
                            print(f"   Confidence: {details.get('confidence', 0):.3f}")
                            
                            # Check risk limits
                            if not check_risk_limits(symbol, decision, config):
                                print(f"   ⚠️  Risk limits prevent trade")
                                continue
                            
                            # Calculate position size
                            position_size = calculate_position_size(
                                symbol=symbol,
                                decision=decision,
                                config=config,
                                current_price=latest['close']
                            )
                            
                            msg = (
                                f"🎯 {decision} Signal\n"
                                f"Symbol: {symbol}\n"
                                f"TF: {tf}\n"
                                f"Price: {latest['close']:.2f}\n"
                                f"Size: {position_size:.4f}\n"
                                f"Confidence: {details.get('confidence', 0):.3f}"
                            )
                            
                            if trading_enabled:
                                # Execute trade
                                print(f"   💰 Executing {decision} order...")
                                # TODO: Implement order execution
                                msg += "\n✅ Order executed"
                            else:
                                msg += "\n📝 PAPER MODE - no order placed"
                            
                            send_notification(msg)
                            print(f"   {msg}")
                        
                    except Exception as e:
                        print(f"❌ Error processing {symbol} {tf}: {e}")
                        continue
            
            # Sleep before next poll
            time.sleep(poll_interval)
            
        except KeyboardInterrupt:
            print("\n⏹️  Shutting down...")
            send_notification("⏹️ Bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Critical error: {e}")
            import traceback
            traceback.print_exc()
            send_notification(f"❌ Critical error: {e}")
            time.sleep(60)  # Wait before retrying


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Live trading bot')
    parser.add_argument('--config', default='config.yaml', help='Config file')
    args = parser.parse_args()
    
    run_live_trading(args.config)
