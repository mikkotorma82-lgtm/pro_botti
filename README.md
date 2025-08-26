
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
