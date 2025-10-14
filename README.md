
# pro_botti

A configurable trading research + live system. Nothing is hardcoded — all tunables live in `config.yaml`.

## Quick start

```bash
pip install -r requirements.txt

# 1) prepare data (CSV with columns: timestamp, open, high, low, close, volume)
python -m cli data.fetch --symbol BTCUSDT --tf 15m --days 120

# 2) train
python -m cli train --config config.yaml

# 3) backtest
python -m cli backtest --config config.yaml

# 4) go live (paper by default)
python -m cli live --config config.yaml
```

## New Features: Top-5 Symbol Selection & Position Monitoring

### Overview

The trading bot now includes an automated system to:
1. Evaluate all trained models across symbols and timeframes
2. Select the top-K best performing symbols based on composite scoring
3. Trade only selected symbols in live mode
4. Continue monitoring ALL open positions (even if symbol is removed from top-K)
5. Automatically retrain and update selection on a schedule

### Workflow

```
┌─────────────┐     ┌─────────┐     ┌──────────┐     ┌─────────────┐
│  Backfill   │ --> │  Train  │ --> │ Evaluate │ --> │ Select Top  │
│    Data     │     │ Models  │     │ Metrics  │     │  Symbols    │
└─────────────┘     └─────────┘     └──────────┘     └─────────────┘
                                                              │
                                                              v
                                                    ┌──────────────────┐
                                                    │ active_symbols.  │
                                                    │     json         │
                                                    └──────────────────┘
                                                              │
                                                              v
                                                    ┌──────────────────┐
                                                    │  Live Trading    │
                                                    │  (Top-K only)    │
                                                    └──────────────────┘
                                                              │
                                                              v
                                                    ┌──────────────────┐
                                                    │Position Watcher  │
                                                    │ (All positions)  │
                                                    └──────────────────┘
```

### Configuration

The `config.yaml` file includes new sections for symbol selection and evaluation:

```yaml
selection:
  top_k: 5                # Number of top symbols to select
  min_trades: 25          # Minimum trades required for selection
  weights:
    sharpe: 0.5           # Weight for Sharpe ratio
    profit_factor: 0.3    # Weight for profit factor
    max_drawdown: 0.2     # Weight for max drawdown (penalty)
    winrate: 0.0          # Weight for win rate

evaluation:
  lookback_days: 365      # Days of history to evaluate
  timeframes: [15m, 1h, 4h]

live:
  always_manage_open_positions: true  # Continue managing all open positions
```

Environment variables can override config:
- `TOP_K` - Number of symbols to select
- `MIN_TRADES` - Minimum trades threshold
- `EVAL_LOOKBACK_DAYS` - Evaluation lookback period
- `SELECT_WEIGHTS` - JSON string of scoring weights
- `ACTIVE_TFS` - Comma-separated timeframes
- `ALWAYS_MANAGE_OPEN_POSITIONS` - Continue managing all positions

### Manual Usage

#### 1. Evaluate Trained Models

```bash
# Evaluate all symbols for a specific timeframe
python scripts/evaluate.py --timeframes 1h --lookback-days 365

# Evaluate specific symbols
python scripts/evaluate.py --symbols US500 BTCUSDT EURUSD --timeframes 1h 4h

# Custom lookback period
python scripts/evaluate.py --timeframes 1h --lookback-days 180
```

This creates metrics files in `results/metrics/`:
- `metrics_1h.json` - Metrics for 1h timeframe
- `metrics_4h.json` - Metrics for 4h timeframe
- `metrics_all.json` - Combined metrics

#### 2. Select Top Symbols

```bash
# Select top-5 symbols for 1h timeframe
python -m cli select-top --tf 1h --top-k 5 --min-trades 25

# Custom weights (JSON format)
python -m cli select-top --tf 1h --top-k 5 \
  --weights '{"sharpe": 0.6, "profit_factor": 0.3, "max_drawdown": 0.1, "winrate": 0.0}'

# Higher minimum trades threshold
python -m cli select-top --tf 1h --top-k 5 --min-trades 50
```

This creates `state/active_symbols.json`:

```json
{
  "generated_at": "2025-10-14T07:47:18.843Z",
  "timeframes": ["1h"],
  "top_k": 5,
  "symbols": ["US500", "NAS100", "BTCUSDT", "EURUSD", "GBPUSD"],
  "criteria": {
    "min_trades": 25,
    "weights": {
      "sharpe": 0.5,
      "profit_factor": 0.3,
      "max_drawdown": 0.2,
      "winrate": 0.0
    },
    "lookback_days": 365
  }
}
```

#### 3. Show Active Symbols

```bash
python -m cli show-active
```

Output:
```
============================================================
ACTIVE TRADING SYMBOLS
============================================================
Generated at: 2025-10-14T07:47:18.843Z
Top-K: 5
Timeframes: 1h

Selected symbols (5):
  • US500
  • NAS100
  • BTCUSDT
  • EURUSD
  • GBPUSD

Criteria:
  min_trades: 25
  lookback_days: 365
  Weights:
    sharpe: 0.5
    profit_factor: 0.3
    max_drawdown: 0.2
    winrate: 0.0
============================================================
```

#### 4. Run Live Trading

Live trading automatically loads `state/active_symbols.json`:

```bash
python -m cli live --config config.yaml
```

If `active_symbols.json` doesn't exist, it falls back to symbols in config.yaml or environment variables.

### Automated Retraining

The `scripts/auto_retrain.sh` script automates the full pipeline:

```bash
# Run manually
./scripts/auto_retrain.sh

# Or schedule with cron (every day at 2 AM)
0 2 * * * /root/pro_botti/scripts/auto_retrain.sh
```

#### Using systemd (Recommended)

1. Install systemd service files:

```bash
sudo cp deploy/pro_botti-retrain.service /etc/systemd/system/
sudo cp deploy/pro_botti-retrain.timer /etc/systemd/system/
sudo cp deploy/pro_botti.service /etc/systemd/system/
```

2. Enable and start services:

```bash
# Enable retrain timer (runs daily at 2 AM)
sudo systemctl enable pro_botti-retrain.timer
sudo systemctl start pro_botti-retrain.timer

# Enable live trading service
sudo systemctl enable pro_botti.service
sudo systemctl start pro_botti.service
```

3. Check status:

```bash
# Check timer status
sudo systemctl status pro_botti-retrain.timer

# Check when next retrain is scheduled
sudo systemctl list-timers pro_botti-retrain.timer

# Check live service status
sudo systemctl status pro_botti.service

# View logs
sudo journalctl -u pro_botti-retrain.service -f
sudo journalctl -u pro_botti.service -f
```

### Position Monitoring

The position watcher continuously monitors all open positions, even if their symbols are no longer in the top-K list:

- **Check interval**: Every 30 seconds (configurable)
- **Management**: Applies TP/SL/trailing stop logic from `position_guard.py`
- **Scope**: ALL open positions, not just active symbols
- **Safety**: Prevents orphaned positions if symbol is removed from active list

To disable position watching:
```bash
export ALWAYS_MANAGE_OPEN_POSITIONS=0
```

### Metrics Explained

The evaluation calculates these metrics for each symbol+timeframe:

- **trades**: Number of trades executed
- **winrate**: Percentage of winning trades
- **profit_factor**: Total gains / total losses
- **sharpe**: Annualized Sharpe ratio (risk-adjusted returns)
- **sortino**: Annualized Sortino ratio (downside risk)
- **max_drawdown**: Maximum peak-to-trough decline (%)
- **avg_trade_return**: Average return per trade
- **exposure**: Percentage of time in position
- **total_return**: Cumulative return over evaluation period

### Composite Scoring

Symbols are ranked using a weighted composite score:

```
score = w_sharpe × norm(sharpe) 
      + w_pf × norm(profit_factor) 
      - w_dd × norm(max_drawdown)
      + w_wr × norm(winrate)
```

Where:
- Metrics are normalized to [0, 1] range with clamping
- Drawdown is subtracted (lower is better)
- Default weights: sharpe=0.5, profit_factor=0.3, max_drawdown=0.2, winrate=0.0

### Troubleshooting

**No metrics found**
```bash
# Run evaluation first
python scripts/evaluate.py --timeframes 1h
```

**Selection fails**
```bash
# Check if metrics file exists
ls -la results/metrics/metrics_1h.json

# View metrics
cat results/metrics/metrics_1h.json | jq
```

**Live trading not using active symbols**
```bash
# Verify active_symbols.json exists
python -m cli show-active

# Check logs
tail -f logs/live.log
```

## Layout

- `config.yaml` – all params
- `config.py`   – dataclasses + loader
- `data/loader.py` – OHLCV IO, resampling, merges features
- `features/feature_engineering.py` – TA features
- `labels/labeling.py` – forward return / barrier labels
- `models/trainer.py` – walk-forward CV training + save artifacts
- `strategy/alpha.py` – signal->orders
- `risk/risk.py` – RiskCfg + sizing + caps
- `broker/base.py` – broker interface
- `broker/paper.py` – in-memory paper broker
- `broker/capital_http.py` – thin wrapper (optional)
- `live/live_trader.py` – live loop
- `backtest/engine.py` – vectorized backtester
- `cli.py` – command-line entrypoints
- **`utils/metrics.py`** – comprehensive trading metrics
- **`utils/selector.py`** – top-K symbol selection with composite scoring
- **`utils/position_watcher.py`** – continuous position monitoring
- **`scripts/evaluate.py`** – post-train evaluation across symbols/timeframes
- **`scripts/auto_retrain.sh`** – automated retrain pipeline
- **`state/active_symbols.json`** – selected trading symbols
- **`deploy/`** – systemd service templates
