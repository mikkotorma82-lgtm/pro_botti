PY=python
CSV=data/EURUSD_15m.csv
MODEL=models/EURUSD_15m_lr.joblib
PREDS=data/EURUSD_15m_preds.csv
RES=results

all: train infer thr backtest

train:
	$(PY) -m tools.train_loop --csv $(CSV) --out_dir models --cv 3

infer:
	$(PY) -m tools.offline_live --model $(MODEL) --csv $(CSV) --out $(PREDS) --thr 0.5

thr:
	$(PY) -m tools.threshold_opt --data_csv $(CSV) --preds_csv $(PREDS) --fee_bps 3 --metric f1 --out $(RES)/thr_f1.json

backtest:
	THR=$$(jq -r .best_thr $(RES)/thr_f1.json); \
	$(PY) -m tools.backtest_lr --data_csv $(CSV) --preds_csv $(PREDS) --fee_bps 3 --use_proba --thr $$THR --out_prefix $(RES)/EURUSD_15m_lr_best

.PHONY: all train infer thr backtest
