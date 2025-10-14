#!/usr/bin/env python3
"""
Pro Botti - Modern Trading Bot
Main entry point for the trading bot
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description='Pro Botti Trading Bot')
    parser.add_argument('--mode', choices=['backfill', 'train', 'live'], 
                       required=True, help='Operating mode')
    parser.add_argument('--config', default='config.yaml', 
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    if args.mode == 'backfill':
        from scripts.backfill import run_backfill
        run_backfill(args.config)
    elif args.mode == 'train':
        from scripts.train import run_training
        run_training(args.config)
    elif args.mode == 'live':
        from scripts.live import run_live_trading
        run_live_trading(args.config)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
