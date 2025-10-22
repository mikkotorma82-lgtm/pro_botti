# 24/7 Autopilot (Capital)

This stack runs fully automatic:
- Live loop fetches Capital candles, generates consensus signals, executes orders, logs trades
- Trade frequency controller nudges thresholds toward a target trades/day
- Daily backfill, weekly retraining (WFA-Pro)
- Online learning (threshold nudge) from realized PnL

## Env

```
set -a; source ./secrets.env; set +a
# Symbols & TFs
export TRADE_SYMBOLS="US SPX 500,EUR/USD,GOLD,AAPL,BTC/USD"
export LIVE_TFS="15m,1h"
# Execution realism & position mode
export SIM_FEE_BPS=1.0
export SIM_SLIP_BPS=1.5
export SIM_SPREAD_BPS=0.5
export SIM_POSITION_MODE=longflat   # or longshort
export SIM_SR_FILTER=1
# Frequency target (~10/day total, override per symbol__tf in state/trade_freq_stats.json)
# CAPITAL_* already set in secrets.env
```

## One-time: train

```
python -m tools.train_wfa_pro
```

## Live

```
# foreground
python -m tools.auto_daemon_pro
```

Recommended: create a systemd unit and a weekly timer for `tools.train_wfa_pro`.
