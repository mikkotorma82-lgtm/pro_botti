import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Any

# ---------- General ----------
@dataclass
class GeneralCfg:
    log_level: str = "INFO"

# ---------- Market ----------
@dataclass
class MarketCfg:
    timeframe: str = "1h"
    symbols: List[str] = field(default_factory=list)

# ---------- Backtest ----------
@dataclass
class BacktestCfg:
    initial_cash: float = 10000.0
    commission_bp: float = 1.0  # 1 = 0.01%

# ---------- Live (jos koodi vilkuilee tätä rinnalla) ----------
@dataclass
class LiveCfg:
    timeframes: List[str] = field(default_factory=lambda: ["15m", "1h", "4h"])
    symbols: List[str] = field(default_factory=list)

# ---------- Root ----------
@dataclass
class RootCfg:
    data_dir: str = "data"
    model_dir: str = "models"
    poll_seconds: Dict[str, int] = field(default_factory=lambda: {"15m": 20, "1h": 30, "4h": 60})
    general: GeneralCfg = field(default_factory=GeneralCfg)
    market: MarketCfg = field(default_factory=MarketCfg)
    backtest: BacktestCfg = field(default_factory=BacktestCfg)
    live: LiveCfg = field(default_factory=LiveCfg)

def _dict_to(cls, d: Dict[str, Any]):
    if not hasattr(cls, "__dataclass_fields__"):
        return d
    kwargs = {}
    for name, f in cls.__dataclass_fields__.items():  # type: ignore
        if name in d:
            val = d[name]
            if hasattr(f.type, "__dataclass_fields__"):
                kwargs[name] = _dict_to(f.type, val)
            else:
                kwargs[name] = val
    return cls(**kwargs)

def load_config(path: str) -> RootCfg:
    with open(path, "r", encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    cfg = RootCfg()
    for key in ("data_dir", "model_dir", "poll_seconds"):
        if key in raw:
            setattr(cfg, key, raw[key])
    if "general" in raw:
        cfg.general = _dict_to(GeneralCfg, raw["general"])
    if "market" in raw:
        cfg.market = _dict_to(MarketCfg, raw["market"])
    if "backtest" in raw:
        cfg.backtest = _dict_to(BacktestCfg, raw["backtest"])
    if "live" in raw:
        cfg.live = _dict_to(LiveCfg, raw["live"])
    if not cfg.market.symbols and cfg.live.symbols:
        cfg.market.symbols = list(cfg.live.symbols)
    return cfg
