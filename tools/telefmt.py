from datetime import datetime

SIDE_EMOJI = {
    "BUY":  "🟢 BUY",
    "SELL": "🔴 SELL",
    "HOLD": "⚪ HOLD",
}

def fmt_signal(symbol: str, tf: str, side: str, p: float, *, tz="UTC") -> str:
    side = (side or "").upper()
    label = SIDE_EMOJI.get(side, side)
    prob = f"{p:.1%}"
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") + f" {tz}"
    # Esim. 📈 AAPL 15m — 🟢 BUY (53.3%) @ 2025-08-29 18:21:03 UTC
    return f"📈 {symbol} {tf} — {label} ({prob}) @ {ts}"
