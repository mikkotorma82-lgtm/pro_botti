import math, time, statistics as stats
from dataclasses import dataclass

@dataclass
class RiskCfg:
    bal: float
    risk_pct: float
    atr: float
    pip_value: float
    sl_mult: float
    tp_mult: float
    slippage_bps: float

def _clamp(x, lo, hi): return max(lo, min(hi, x))

def units_by_risk(cfg: RiskCfg):
    """Risk-per-trade kokolaskenta ATR-stopilla."""
    risk_usd = cfg.bal * (cfg.risk_pct/100.0)
    stop_usd = max(1e-6, cfg.atr * cfg.pip_value * cfg.sl_mult)
    raw = risk_usd / stop_usd
    # suoja: älä ylitä spread/slippage-riskillä liikaa
    raw *= (1.0 - cfg.slippage_bps/10000.0)
    return max(1.0, raw)

def sl_tp(price, side, atr, sl_mult, tp_mult):
    if side == "BUY":
        sl = price - atr*sl_mult
        tp = price + atr*tp_mult
    else:
        sl = price + atr*sl_mult
        tp = price - atr*tp_mult
    return (sl, tp)

class Circuit:
    """Yksinkertainen circuit breaker: peräkkäiset tappiot, intraday DD ja volapiikki."""
    def __init__(self, max_losses, max_dd_pct, zmax, cooldown):
        self.max_losses = max_losses
        self.max_dd_pct = max_dd_pct
        self.zmax = zmax
        self.cooldown = cooldown
        self.loss_streak = 0
        self.day_peak = None
        self.until = 0

    def note_pnl(self, eq):
        self.day_peak = eq if self.day_peak is None else max(self.day_peak, eq)
        if self.day_peak:
            dd = 100.0*(self.day_peak-eq)/self.day_peak
            if dd >= self.max_dd_pct:
                self.until = time.time()+self.cooldown
                return f"🔌 Circuit breaker: intraday DD {dd:.2f}% ≥ {self.max_dd_pct}%"
        return None

    def note_trade_result(self, pnl_usd):
        self.loss_streak = self.loss_streak+1 if pnl_usd < 0 else 0
        if self.loss_streak >= self.max_losses:
            self.until = time.time()+self.cooldown
            return f"🔌 Circuit breaker: {self.loss_streak} peräkkäistä tappiota"
        return None

    def note_vol(self, zscore):
        if zscore is not None and abs(zscore) >= self.zmax:
            self.until = time.time()+self.cooldown
            return f"🔌 Circuit breaker: vol z-score {zscore:.1f} ≥ {self.zmax}"
        return None

    def allowed(self): 
        return time.time() >= self.until
