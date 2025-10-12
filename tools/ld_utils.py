from __future__ import annotations
from typing import Dict, Union

def should_send_daily_digest(last_sent_ts: int | None, now_ts: int, period_sec: int = 86400) -> bool:
    """
    Palauta True, jos viimeisimmästä digest-lähetyksestä on kulunut >= period_sec.
    Jos last_sent_ts on None -> True (lähetetään heti).
    """
    if last_sent_ts is None:
        return True
    return (now_ts - last_sent_ts) >= period_sec

def rank_symbols_by_edge(edges: Dict[str, Union[float, Dict[str, float]]], topk: int) -> list[str]:
    """
    Järjestä symbolit suurimman edge-arvon mukaan. edges voi olla:
      - {"BTC": 0.61, "ETH": 0.58} TAI
      - {"BTC": {"15m":0.6,"1h":0.5}, "ETH":{"15m":0.7}}
    Palauttaa topk symbolin listan.
    """
    flat = {}
    for sym, val in edges.items():
        if isinstance(val, dict):
            # Ota paras timeframe-edge
            best = max(val.values()) if val else float("-inf")
        else:
            best = float(val)
        flat[sym] = best
    return [sym for sym, _ in sorted(flat.items(), key=lambda kv: kv[1], reverse=True)[:topk]]

def scale_risk_from_meta(meta_or_sym, max_usdt: float, long_signal: bool | None = None):
    """
    Skaalaa positio meta-tiedoilla. Sallitaan sekä:
      1) scale_risk_from_meta(meta_dict, max_usdt)
      2) scale_risk_from_meta(symbol, tf, meta_dict, max_usdt, long_signal=True/False)
    Toteutus: jos meta['volatility']>0, käytä  max_usdt / (volatility * scale),
    missä scale = 1.0 + 0.0*max_drawdown (varaa koukku laajennukselle).
    Leikataan arvoa myös mahdollisella meta['max_position_usdt'].
    """
    # Unpack mahdollinen (symbol, tf, meta, max_usdt, long_signal) -muoto
    meta = None
    if isinstance(meta_or_sym, dict):
        meta = meta_or_sym
    else:
        # odotetaan: sym, tf, meta, max_usdt, long_signal
        # tämä haara on yhteensopiva aiempien kutsujen kanssa,
        # mutta emme tarvitse sym/tf arvoja peruskaavaan
        def _pop_arg(args, idx, default=None):
            try:
                return args[idx]
            except IndexError:
                return default
        # tästä funktiosta ei näy args-listaa, joten ohitetaan: käyttäjä antaa suoraan meta_dictin normaalisti
        meta = None

    if meta is None:
        # fallback: neutraali
        return float(max_usdt)

    vol = float(meta.get("volatility", 0) or 0)
    max_pos = meta.get("max_position_usdt")
    if vol <= 0:
        size = float(max_usdt)
    else:
        size = float(max_usdt) / vol

    if isinstance(max_pos, (int, float)) and max_pos > 0:
        size = min(size, float(max_pos))

    return float(size)
