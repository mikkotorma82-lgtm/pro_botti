import os
import time
import json
from tools.send_trade_chart import build_chart
from tools.tele import send as send_telegram, send_photo as send_telegram_photo

# ... muu alkuperäinen sisältö ja DEFAULTS ...

_memory = {}

def _pct(pl: float, open_level: float) -> float:
    if not open_level:
        return 0.0
    return (pl / open_level) * 100.0

def guard_positions(capital_client, cfg: dict = None):
    """Käy läpi avoimet positiot ja sulkee TP/SL/Trail-logiikalla + telegram ilmoitus + chart."""
    if cfg is None:
        cfg = {}
    C = {**DEFAULTS, **cfg}

    try:
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
            entry_ts = pos.get("openTime") or pos.get("entry_ts") or pos.get("opened") or int(time.time()) - 3600
            exit_ts = int(time.time())
            tf = pos.get("tf") or "1h"

            mem = _memory.setdefault(epic, {"best_pct": 0.0, "trail_anchor": None})
            if pct_now > mem["best_pct"]:
                mem["best_pct"] = pct_now

            def send_position_close_telegram(reason):
                try:
                    entry = open_level
                    exit = pos.get("closeLevel") or pos.get("close_price") or open_level + upl
                    path, caption = build_chart(epic, tf, entry, exit, entry_ts, exit_ts, "trade_chart.png")
                    caption = f"{reason}: {caption}"
                    send_telegram(f"Position closed: {epic} {tf} {reason} PnL: {pct_now:.2f}%")
                    send_telegram_photo(path, caption)
                except Exception as e:
                    log.error(f"[GUARD] Telegram/chart fail: {e}")

            # Take Profit
            if pct_now >= C["TAKE_PROFIT_PCT"]:
                log.info("[GUARD] %s TP hit: %.2f%% ≥ %.2f%% → CLOSE", epic, pct_now, C["TAKE_PROFIT_PCT"])
                try:
                    capital_client.close_position(epic=epic, direction=direction)
                    send_position_close_telegram("TP")
                except Exception as e:
                    log.error("[GUARD] %s close failed: %s", epic, e)
                continue

            # Stop Loss
            if pct_now <= -C["STOP_LOSS_PCT"]:
                log.info("[GUARD] %s SL hit: %.2f%% ≤ -%.2f%% → CLOSE", epic, pct_now, C["STOP_LOSS_PCT"])
                try:
                    capital_client.close_position(epic=epic, direction=direction)
                    send_position_close_telegram("SL")
                except Exception as e:
                    log.error("[GUARD] %s close failed: %s", epic, e)
                continue

            # Trailing
            if pct_now >= C["TRAIL_START_PCT"]:
                if mem["trail_anchor"] is None:
                    mem["trail_anchor"] = pct_now
                drop = mem["best_pct"] - pct_now
                if drop >= C["TRAIL_STEP_PCT"]:
                    log.info("[GUARD] %s TRAIL drop: %.2f%% ≥ %.2f%% (peak=%.2f%%) → CLOSE",
                             epic, drop, C["TRAIL_STEP_PCT"], mem["best_pct"])
                    try:
                        capital_client.close_position(epic=epic, direction=direction)
                        send_position_close_telegram("TRAIL")
                    except Exception as e:
                        log.error("[GUARD] %s close failed: %s", epic, e)

        except Exception as e:
            log.error("[GUARD] position loop error: %s", e)
