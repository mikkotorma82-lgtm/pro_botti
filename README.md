
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

## META Ensemble Training & Multi-AI Trading Engine

### Overview

The META ensemble training system enables automated training of multiple AI models (GBDT, LR, XGBoost, LightGBM) across all symbols and timeframes with minimal configuration. The trade engine combines signals from these models to make intelligent trading decisions.

### META Training

#### Quick Start

```bash
# Train all symbols from symbols.txt on Capital.com
META_SYMBOLS_FILE=config/symbols.txt \
META_EXCHANGE_ID=capitalcom \
META_TRAINER_PATH=tools.meta_ensemble:train_symbol_tf \
python -m tools.meta_train_all

# Limit to specific timeframes
META_TFS=15m,1h python -m tools.meta_train_all

# Increase parallelism
META_PARALLEL=8 python -m tools.meta_train_all

# Test with limited symbols
META_MAX_SYMBOLS=5 python -m tools.meta_train_all
```

#### Configuration

All configuration is environment-driven:

| Variable | Default | Description |
|----------|---------|-------------|
| `META_EXCHANGE_ID` | `capitalcom` | Exchange identifier (capitalcom, kraken, etc.) |
| `META_SYMBOLS_FILE` | `./config/symbols.txt` | Path to symbols file |
| `META_TFS` | `15m,1h,4h` | Comma-separated timeframes |
| `META_PARALLEL` | `4` | Number of parallel training workers |
| `META_MIN_CANDLES` | `300` | Minimum candles required per timeframe |
| `META_MAX_SYMBOLS` | `0` | Limit symbols for testing (0 = unlimited) |
| `META_TRAINER_PATH` | `tools.meta_ensemble:train_symbol_tf` | Trainer module:function |
| `META_ENS_PF` | `1.0` | Ensemble profit factor target |
| `META_THR` | `0.6` | Base prediction threshold |
| `META_MODELS` | `gbdt,lr,xgb,lgbm` | Models to train |

#### Symbol Normalization

The system automatically normalizes symbol formats:
- `BTCUSD` → `BTC/USD`
- `ETHUSDT` → `ETH/USDT`
- Kraken-specific aliases (e.g., `BTC` → `XBT`)

For Capital.com, all symbols are accepted for data-based validation (not ccxt-based).

#### Systemd Automation

Install and enable the META training timer:

```bash
# Copy service files
sudo cp deploy/systemd/pro-botti-meta-train.service /etc/systemd/system/
sudo cp deploy/systemd/pro-botti-meta-train.timer /etc/systemd/system/

# Enable and start timer (runs every 30 minutes)
sudo systemctl enable pro-botti-meta-train.timer
sudo systemctl start pro-botti-meta-train.timer

# Check status
sudo systemctl status pro-botti-meta-train.timer
sudo systemctl list-timers pro-botti-meta-train.timer

# View logs
sudo journalctl -u pro-botti-meta-train.service -f
```

The timer configuration is in `deploy/systemd/pro-botti-meta-train.timer`:
- Runs 5 minutes after boot
- Runs every 30 minutes thereafter
- Randomized delay of 2 minutes to prevent thundering herd

#### Training Output

The trainer logs each symbol/timeframe with:
- ✅ **OK**: Successfully trained
- ⚠️ **SKIP**: Skipped (insufficient data, unsupported, etc.)
- ❌ **FAIL**: Failed with error

Results are stored in:
- `state/models_meta/` - Model files (`.joblib`)
- `state/models_meta.json` - Registry with metrics and weights

Example output:
```
2025-10-20 09:09:13,934 INFO META-ensemble start symbols=32 (supported) rejected=0 tfs=15m,1h,4h models=gbdt,lr,xgb,lgbm
2025-10-20 09:09:13,936 WARNING ⚠️ [META ENS SKIP] US500 15m reason=not-enough-candles(0<300)
2025-10-20 09:15:42,123 INFO ✅ [META ENS OK] BTC/USD 1h metrics={'ens_pf': 2.34, 'threshold': 0.62, 'entries': 156}
2025-10-20 09:09:13,936 INFO 📣 META-ensemble koulutus valmis | OK=24 SKIP=6 FAIL=2
```

### Multi-AI Trading Engine

The trade engine combines signals from multiple AI models to execute trades on Capital.com.

#### Quick Start

```bash
# Dry run (no actual orders)
DRY_RUN=true python -m tools.trade_engine --symbol BTC/USD --tf 1h --run-once

# Real trading (requires Capital.com credentials)
python -m tools.trade_engine --symbol ETH/USD --tf 1h --run-once

# Daemon mode (continuous monitoring)
python -m tools.trade_engine --symbol BTC/USD,ETH/USD --tf 1h,4h --daemon --interval 300
```

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `false` | Dry run mode (no actual orders) |
| `ORDER_SIZE` | `0.01` | Fixed order size |
| `ORDER_SIZE_PCT` | `0.0` | Order size as % of balance (overrides ORDER_SIZE if > 0) |
| `MAX_LEVERAGE` | `1.0` | Maximum leverage |
| `STOP_LOSS_PCT` | `2.0` | Stop loss percentage |
| `TAKE_PROFIT_PCT` | `4.0` | Take profit percentage |
| `META_THR` | `0.6` | Decision threshold for signals |
| `VOTE_TYPE` | `weighted` | Voting method: `majority` or `weighted` |
| `MIN_MODELS` | `2` | Minimum models required for decision |

#### Signal Combination

**Majority Vote** (`VOTE_TYPE=majority`):
- Decision requires >50% of models to agree
- BUY if majority predicts ≥ threshold
- SELL if majority predicts ≤ (1 - threshold)

**Weighted Vote** (`VOTE_TYPE=weighted`):
- Uses ensemble weights from training
- Weighted average of all predictions
- BUY if weighted_avg ≥ threshold
- SELL if weighted_avg ≤ (1 - threshold)

#### Risk Controls

1. **Idempotency**: Prevents duplicate orders for same symbol/timeframe
2. **Position Limits**: Respects MAX_LEVERAGE
3. **Stop Loss**: Automatic SL at STOP_LOSS_PCT
4. **Take Profit**: Automatic TP at TAKE_PROFIT_PCT
5. **Minimum Models**: Requires MIN_MODELS models for decision

#### Order Logging

All orders are logged to `state/trade_engine_orders.json`:

```json
{
  "timestamp": 1729414173,
  "symbol": "BTC/USD",
  "signal": "BUY",
  "confidence": 0.75,
  "predictions": {
    "gbdt": 0.78,
    "lr": 0.72,
    "xgb": 0.76,
    "lgbm": 0.74
  },
  "status": "executed",
  "order": {
    "side": "buy",
    "size": 0.01,
    "stop_loss_pct": 2.0,
    "take_profit_pct": 4.0
  }
}
```

#### Telegram Notifications

If Telegram is configured, the trade engine sends notifications:
- 🟢 BUY orders with confidence and risk levels
- 🔴 SELL orders with confidence and risk levels
- 🔍 DRY RUN orders (for testing)
- ❌ Order failures with error details

### Troubleshooting

**Import errors (ModuleNotFoundError: No module named 'tools.meta_ensemble')**
- Ensure `META_TRAINER_PATH` points to existing module:function
- Default: `tools.meta_ensemble:train_symbol_tf`

**Symbol normalization issues**
- Check `config/symbols.txt` format (one per line)
- Use standard formats: `BTCUSD`, `BTC/USD`, `ETHUSDT`
- Comments with `#` are supported

**Capital.com authentication errors**
- Set required environment variables:
  - `CAPITAL_API_BASE`
  - `CAPITAL_API_KEY`
  - `CAPITAL_USERNAME`
  - `CAPITAL_PASSWORD`
- Check credentials in Capital.com dashboard

**Datetime handling in send_trade_chart**
- Now supports both numpy arrays and pandas Series/Index
- Handles datetime64 with automatic unit detection
- Works with ISO timestamps and epoch seconds

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
