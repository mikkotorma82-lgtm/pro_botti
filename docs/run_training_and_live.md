# Capital SMA training + live signals

This pipeline:
- reads symbols from env: `TRADE_SYMBOLS` (fallback `CAPITAL_SYMBOLS`)
- backfills Capital OHLCV
- runs Walk-Forward (SMA) and writes a registry of best params
- produces live signals via Capital prices

## 1) Prepare env

```
set -a; source ./secrets.env; set +a
export CAPITAL_LOGIN_TTL=540
export CAPITAL_RATE_LIMIT_SLEEP=120
# symbols like: TRADE_SYMBOLS=US SPX 500,EUR/USD,GOLD,AAPL,BTC/USD
```

## 2) Train (backfill + WFA)

```
python -m tools.train_capital_wfa
```

Outputs:
- data/capital/SYMBOL__TF.csv
- state/models_sma.json

## 3) Live signals

```
python -m tools.live_signal_sma
# control TFs:
LIVE_TFS="1h,15m" python -m tools.live_signal_sma
```

Integrate to your live trade loop by mapping signals to orders (BUY/SELL/HOLD). Use existing broker/order router modules.
