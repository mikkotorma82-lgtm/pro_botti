from tools.notifier import train_started,train_finished
train_started("1 kk backtest 1000€")
initial=1000.0
# TODO: backtestoi ja tuota equity
eq_end=1000.0
pct=(eq_end/initial-1)*100
train_finished(pct, eq_end, initial, "viime kuukausi")
