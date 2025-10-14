# Changelog

## [Unreleased] - 2025-10-14

### Added

#### Top-K Symbol Selection System
- **Post-train evaluation** across all symbols and timeframes
- **Composite scoring** with configurable weights for Sharpe, profit factor, drawdown, and win rate
- **Automatic symbol selection** based on performance metrics
- **State management** via `state/active_symbols.json`

#### Enhanced Metrics
- New `utils/metrics.py` module with comprehensive trading metrics:
  - trades, winrate, profit_factor
  - sharpe, sortino ratios
  - max_drawdown, avg_trade_return
  - exposure calculation
- Robust metric calculation with edge case handling

#### Position Monitoring
- New `utils/position_watcher.py` for continuous position monitoring
- Monitors ALL open positions, even if symbol removed from active list
- Integrates with existing `position_guard.py` for TP/SL/trailing stop logic
- Configurable check interval (default: 30 seconds)

#### Evaluation Framework
- New `scripts/evaluate.py` for post-train model evaluation
- Loads historical data and trained models
- Calculates comprehensive metrics for each symbol+timeframe
- Outputs JSON metrics files in `results/metrics/`
- Supports custom lookback periods

#### Symbol Selector
- New `utils/selector.py` with intelligent symbol selection
- Composite scoring with normalized metrics
- Minimum trades threshold filtering
- Configurable top-K selection
- Detailed logging of selection criteria and results

#### CLI Commands
- `select-top`: Select top-K symbols based on metrics
  - Arguments: `--tf`, `--top-k`, `--min-trades`, `--lookback-days`, `--weights`
- `show-active`: Display currently active trading symbols
  - Shows selection criteria and symbol details

#### Automated Retraining
- New `scripts/auto_retrain.sh` pipeline script
  - Backfill → Train → Evaluate → Select-top
  - Comprehensive error handling and logging
  - Summary reporting
- Systemd integration templates in `deploy/`:
  - `pro_botti-retrain.service`: One-shot retrain service
  - `pro_botti-retrain.timer`: Daily scheduled retraining (2 AM UTC)
  - `pro_botti.service`: Updated live trading service

#### Live Trading Integration
- Modified `tools/live_runner.py` to:
  - Load symbols from `state/active_symbols.json`
  - Fallback to config/env if state file missing
  - Initialize and run position watcher
  - Manage all open positions continuously

#### Configuration
- Extended `config.yaml` with new sections:
  ```yaml
  selection:
    top_k: 5
    min_trades: 25
    weights: {...}
  
  evaluation:
    lookback_days: 365
    timeframes: [15m, 1h, 4h]
  
  live:
    always_manage_open_positions: true
  ```
- Environment variable support:
  - `TOP_K`, `MIN_TRADES`, `EVAL_LOOKBACK_DAYS`
  - `SELECT_WEIGHTS` (JSON format)
  - `ACTIVE_TFS`, `ALWAYS_MANAGE_OPEN_POSITIONS`

#### Documentation
- Comprehensive README update with:
  - Feature overview and workflow diagram
  - Configuration examples
  - Manual usage instructions
  - Automated retraining setup
  - systemd service installation
  - Troubleshooting guide
- New CHANGES.md (this file)

### Changed
- Live trading now prioritizes `state/active_symbols.json` over static config
- Position monitoring is now continuous and symbol-agnostic

### Technical Details

#### Metric Normalization
- Robust min-max scaling with clamping
- Handles outliers gracefully
- Configurable value ranges per metric

#### Position Safety
- No orphaned positions when symbols rotate
- Continuous TP/SL management for all positions
- Graceful degradation if position watcher unavailable

#### Backward Compatibility
- Falls back to traditional symbol loading if `active_symbols.json` missing
- All new features are opt-in via configuration
- Existing workflows continue to work unchanged

### File Structure
```
pro_botti/
├── utils/
│   ├── metrics.py              # NEW: Comprehensive metrics
│   ├── selector.py             # NEW: Symbol selection logic
│   └── position_watcher.py     # NEW: Position monitoring
├── scripts/
│   ├── evaluate.py             # NEW: Post-train evaluation
│   └── auto_retrain.sh         # NEW: Automated pipeline
├── deploy/
│   ├── pro_botti-retrain.service  # NEW: Retrain service
│   ├── pro_botti-retrain.timer    # NEW: Retrain timer
│   └── pro_botti.service          # NEW: Live service template
├── state/
│   └── active_symbols.json     # NEW: Selected symbols
├── results/
│   └── metrics/                # NEW: Evaluation outputs
│       ├── metrics_15m.json
│       ├── metrics_1h.json
│       ├── metrics_4h.json
│       └── metrics_all.json
├── cli.py                      # MODIFIED: Added new commands
├── config.yaml                 # MODIFIED: Added new sections
├── tools/live_runner.py        # MODIFIED: Symbol loading + watcher
├── README.md                   # MODIFIED: Comprehensive docs
└── CHANGES.md                  # NEW: This file
```

### Usage Examples

```bash
# Evaluate models
python scripts/evaluate.py --timeframes 1h --lookback-days 365

# Select top-5 symbols
python -m cli select-top --tf 1h --top-k 5 --min-trades 25

# Show active symbols
python -m cli show-active

# Run automated pipeline
./scripts/auto_retrain.sh

# Setup systemd scheduling
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl enable --now pro_botti-retrain.timer
sudo systemctl enable --now pro_botti.service
```

### Performance Considerations
- Evaluation: O(symbols × timeframes × data_rows)
- Selection: O(candidates × log(candidates))
- Position watching: O(open_positions) every 30 seconds
- Memory usage: < 100MB additional for metrics and selection

### Future Enhancements
- Multi-timeframe aggregation for symbol selection
- Rolling window evaluation (not just static lookback)
- Real-time metric updates during live trading
- Web dashboard for metrics visualization
- Alert notifications on symbol rotation
