# Pro Botti - Modern Trading Bot

A modern, modular trading bot with machine learning capabilities for cryptocurrency and financial markets.

## Features

- 🤖 **ML-Powered Signals**: XGBoost/RandomForest models for trade predictions
- 📊 **Multi-Timeframe Analysis**: Support for 15m, 1h, 4h timeframes
- 🔄 **Multiple Exchanges**: Binance, Capital.com (extensible)
- 🛡️ **Risk Management**: Position sizing, stop-loss, take-profit automation
- 📱 **Telegram Notifications**: Real-time trade alerts
- 📈 **Technical Indicators**: RSI, MACD, Bollinger Bands, EMA, ATR, and more

## Project Structure

```
pro_botti/
├── main.py                 # Main entry point
├── config.yaml             # Configuration file
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (secrets)
├── data/                   # Historical data storage
├── models/                 # Trained ML models
├── scripts/                # Core scripts
│   ├── backfill.py        # Historical data fetching
│   ├── train.py           # Model training
│   ├── live.py            # Live trading daemon
│   └── telegram_notify.py # Telegram integration
└── utils/                  # Utility modules
    ├── capital.py         # Capital.com API
    ├── binance.py         # Binance API
    ├── features.py        # Feature engineering
    ├── risk.py            # Risk management
    ├── ai_gate.py         # AI decision making
    ├── position_sizer.py  # Position sizing
    └── llm.py             # LLM utilities (optional)
```

## Quick Start

### 1. Installation

```bash
# Clone repository
git clone https://github.com/mikkotorma82-lgtm/pro_botti.git
cd pro_botti

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy `.env` to `.env.local` and configure your API keys:

```bash
cp .env .env.local
nano .env.local
```

Edit `config.yaml` to set your trading parameters:
- Symbols to trade
- Timeframes
- Risk limits
- Buy/sell thresholds

### 3. Backfill Historical Data

```bash
python main.py --mode backfill --config config.yaml
```

### 4. Train Models

```bash
python main.py --mode train --config config.yaml
```

### 5. Run Live Trading

```bash
# Paper trading (default)
python main.py --mode live --config config.yaml

# Live trading (set TRADING_ENABLED=1 in .env)
TRADING_ENABLED=1 python main.py --mode live --config config.yaml
```

## Configuration

### Trading Parameters

- `symbols`: List of trading pairs (e.g., BTCUSDT, ETHUSDT)
- `timeframes`: Analysis timeframes (15m, 1h, 4h)
- `buy_threshold`: Minimum confidence for buy signals (default: 0.52)
- `sell_threshold`: Maximum confidence for sell signals (default: 0.48)
- `enable_trading`: Enable actual order execution (default: false)

### Risk Management

- `max_position_size_usdt`: Maximum position size in USDT
- `max_drawdown_pct`: Maximum allowed drawdown
- `stop_loss_pct`: Stop loss percentage
- `take_profit_pct`: Take profit percentage
- `max_leverage`: Maximum leverage (default: 1)

## Development

### Running Individual Scripts

```bash
# Backfill specific symbol
python scripts/backfill.py --config config.yaml

# Train models
python scripts/train.py --config config.yaml

# Live trading
python scripts/live.py --config config.yaml

# Send test notification
python scripts/telegram_notify.py "Test message"
```

### Testing Utilities

```bash
# Test Binance connection
python utils/binance.py

# Test feature engineering
python utils/features.py

# Test risk calculations
python utils/risk.py

# Test AI gate
python utils/ai_gate.py
```

## Safety Features

1. **Paper Trading Mode**: Default mode, no real orders placed
2. **Risk Limits**: Position size and drawdown limits
3. **Cooldown Periods**: Prevent overtrading
4. **Model Validation**: Only trade with validated models
5. **Telegram Alerts**: Real-time notifications

## Deployment

For production deployment:

1. Set `enable_trading: true` in `config.yaml` or `TRADING_ENABLED=1` in `.env`
2. Configure proper risk limits
3. Set up systemd service for automatic restarts
4. Monitor logs and Telegram notifications
5. Start with small position sizes

## License

MIT License

## Disclaimer

This software is for educational purposes only. Use at your own risk. 
Cryptocurrency trading involves substantial risk of loss. 
Always test thoroughly in paper trading mode before going live.
