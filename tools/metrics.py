from prometheus_client import Counter, Histogram, Gauge

sig_total = Counter("signals_total", "Signaalien määrä", ["symbol","tf","side"])
orders_total = Counter("orders_total", "Lähetettyjen tilausten määrä", ["symbol","side","status"])  # status: sent|rejected|filled|partial
latency_sec = Histogram("latency_seconds", "Latenssi vaiheittain", ["phase"])  # phase: signal->order, order->fill, total
slippage_bp = Histogram("slippage_bp", "Slippage basis points", ["symbol","side"])
rate_limits = Counter("api_rate_limit_hits_total", "API ratelimit -osumat", ["venue","kind"])  # kind: read|trade
risk_block = Counter("risk_blocks_total", "Riskilogi esti kaupan", ["reason"])

equity = Gauge("equity_usd", "Arvio ekviti", ["source"])  # backtest|paper|live

def observe_signal(symbol, tf, side): sig_total.labels(symbol, tf, side).inc()
def observe_order(symbol, side, status): orders_total.labels(symbol, side, status).inc()
def observe_latency(phase, seconds): latency_sec.labels(phase).observe(max(float(seconds),0.0))
def observe_slippage(symbol, side, bps): slippage_bp.labels(symbol, side).observe(float(bps))
def hit_rate_limit(venue, kind): rate_limits.labels(venue, kind).inc()
def risk_denied(reason): risk_block.labels(reason).inc()
def set_equity(val, source="live"): equity.labels(source).set(float(val))
