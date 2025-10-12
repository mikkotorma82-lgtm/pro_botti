from __future__ import annotations
import logging
from typing import Dict, List

log = logging.getLogger(__name__)

DEFAULTS = dict(
    TAKE_PROFIT_PCT = 2.0,   # sulje kun +2%
    STOP_LOSS_PCT   = 1.0,   # sulje kun -1%
    TRAIL_START_PCT = 1.0,   # trail alkaa +1%
    TRAIL_STEP_PCT  = 0.5,   # kiristys joka +0.5%
)

_memory = {}

def _pct(pl: float, open_level: float) -> float:
    if not open_level:
        return 0.0
    return (pl / open_level) * 100.0

def guard_positions(capital_client, cfg: Dict = None):
    """Käy läpi avoimet positiot ja sulkee TP/SL/Trail-logiikalla."""
    if cfg is None:
        cfg = {}
    C = {**DEFAULTS, **cfg}

    try:
        # odotetaan että clientissä on metodi open_positions() joka palauttaa listan
        open_pos = capital_client.open_positions()
    except Exception as e:
        log.error("[GUARD] open_positions failed: %s", e)
        return

    if not open_pos:
        return

    for pos in open_pos:
        try:
            epic = pos.get("epic") or pos.get("symbol") or pos.get("instrument")
            direction = pos.get("direction")
            open_level = pos.get("openLevel") or pos.get("open_price") or 0.0
            upl = pos.get("unrealizedPL") or pos.get("profit") or 0.0
            pct_now = _pct(upl, open_level)

            mem = _memory.setdefault(epic, {"best_pct": 0.0, "trail_anchor": None})
            if pct_now > mem["best_pct"]:
                mem["best_pct"] = pct_now

            # Take Profit
            if pct_now >= C["TAKE_PROFIT_PCT"]:
                log.info("[GUARD] %s TP hit: %.2f%% ≥ %.2f%% → CLOSE", epic, pct_now, C["TAKE_PROFIT_PCT"])
                try:
                    capital_client.close_position(epic=epic, direction=direction)
                except Exception as e:
                    log.error("[GUARD] %s close failed: %s", epic, e)
                continue

            # Stop Loss
            if pct_now <= -C["STOP_LOSS_PCT"]:
                log.info("[GUARD] %s SL hit: %.2f%% ≤ -%.2f%% → CLOSE", epic, pct_now, C["STOP_LOSS_PCT"])
                try:
                    capital_client.close_position(epic=epic, direction=direction)
                except Exception as e:
                    log.error("[GUARD] %s close failed: %s", epic, e)
                continue

            # Trailing
            if pct_now >= C["TRAIL_START_PCT"]:
                if mem["trail_anchor"] is None:
                    mem["trail_anchor"] = pct_now
                # jos on pudonnut enemmän kuin TRAIL_STEP aiemmasta huipusta → sulje
                drop = mem["best_pct"] - pct_now
                if drop >= C["TRAIL_STEP_PCT"]:
                    log.info("[GUARD] %s TRAIL drop: %.2f%% ≥ %.2f%% (peak=%.2f%%) → CLOSE",
                             epic, drop, C["TRAIL_STEP_PCT"], mem["best_pct"])
                    try:
                        capital_client.close_position(epic=epic, direction=direction)
                    except Exception as e:
                        log.error("[GUARD] %s close failed: %s", epic, e)

        except Exception as e:
            log.error("[GUARD] position loop error: %s", e)
