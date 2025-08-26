from __future__ import annotations
import sys, os, json, math
from pathlib import Path
import argparse

# Lataa .env / botti.env
try:
    from tools._dotenv import load_dotenv

    load_dotenv()  # lataa .env + botti.env jos löytyvät
except Exception:
    pass

# Broker-snapshot (LIVE/DEMO päätellään envistä)
from tools.broker_capital import get_account_snapshot


def _eurusd_close() -> float:
    """Palauta EURUSD (USD per EUR). Yritä historiasta, muuten ENV tai fallback."""
    # 1) historiasta
    try:
        from core.io import load_history

        df = load_history(Path("data/history"), "EURUSD", os.getenv("FX_TF", "1h"))
        fx = float(df["close"].iloc[-1])
        if fx > 0:
            return fx
    except Exception:
        pass
    # 2) ENV override tai fallback
    return float(os.getenv("FX_EURUSD", "1.08"))


def _guess_price_ccy(symbol: str) -> str:
    s = (symbol or "").upper()
    if s in ("US500", "US100", "AAPL", "NVDA", "TSLA"):
        return "USD"
    if s.endswith("USDT"):
        return "USD"  # kryptat
    if len(s) == 6 and s.endswith("USD"):
        return "USD"  # EURUSD, GBPUSD -> quote USD
    return os.getenv("DEFAULT_PRICE_CCY", "USD").upper()


def _convert_risk_to_price_ccy(risk_cash_acc: float, account_ccy: str, price_ccy: str):
    """
    Muunna riskisumma tilivaluutasta hinnan valuuttaan.
    Oletus: EURUSD = USD per EUR.
    Palauttaa (risk_cash_price_ccy, meta).
    """
    account = (account_ccy or "EUR").upper()
    price = (price_ccy or "USD").upper()
    if account == price:
        return risk_cash_acc, {
            "acc_ccy": account,
            "price_ccy": price,
            "eurusd": None,
            "note": "no_fx_needed",
        }
    fx = _eurusd_close()  # USD per EUR
    if account == "EUR" and price in ("USD", "USDT"):
        return risk_cash_acc * fx, {
            "acc_ccy": "EUR",
            "price_ccy": price,
            "eurusd": fx,
            "note": "EUR->USD",
        }
    if account in ("USD", "USDT") and price == "EUR":
        return risk_cash_acc / fx, {
            "acc_ccy": account,
            "price_ccy": "EUR",
            "eurusd": fx,
            "note": "USD->EUR",
        }
    # muu pari -> ei konversiota (laajenna tarvittaessa)
    return risk_cash_acc, {
        "acc_ccy": account,
        "price_ccy": price,
        "eurusd": fx,
        "note": "unchanged_pair",
    }


def _read_stdin_json():
    buf = sys.stdin.read().strip()
    if not buf:
        return None
    return json.loads(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="")
    args = ap.parse_args()

    msg = _read_stdin_json()
    if not msg:
        print(json.dumps({"status": "noop", "reason": "no_input"}))
        return

    symbol = msg.get("symbol")
    tf = msg.get("tf") or args.tf or ""
    price = float(msg.get("price", 0.0))
    signal = int(msg.get("signal", 0))

    # --- riskiasetukset ENV:stä ---
    basis = os.getenv(
        "RISK_BASIS", "free_margin"
    ).lower()  # free_margin | equity | balance
    risk_pct = float(os.getenv("RISK_PCT", "0.5"))  # % basisista per trade
    stop_pct = float(os.getenv("STOP_PCT", "1.0"))  # % hinnasta fallback
    min_units = float(os.getenv("MIN_UNITS", "0.001"))
    fee_bps = float(os.getenv("FEE_BPS", "2"))
    leverage_max = float(os.getenv("LEVERAGE_MAX", "3"))
    min_free = float(
        os.getenv("RISK_MIN_FREE_MARGIN", "10")
    )  # älä avaa jos free_margin < tämä (tilivaluutassa)

    snap = get_account_snapshot(os.getenv("CAPITAL_ACCOUNT_ID"))
    if not snap.get("ok"):
        print(
            json.dumps(
                {"status": "noop", "reason": "broker_unavailable", "detail": snap}
            )
        )
        return

    # Tilin valuutta ja basis-arvo brokerilta
    account_ccy = (
        snap.get("raw", {}).get("account", {}).get("currency")
        or os.getenv("ACCOUNT_CCY", "EUR")
    ).upper()

    basis_map = {
        "free_margin": snap.get("free_margin"),
        "equity": snap.get("equity"),
        "balance": (snap.get("balance") or {}).get("balance"),
    }
    basis_value = float(basis_map.get(basis) or 0.0)

    if basis == "free_margin" and basis_value < min_free:
        print(
            json.dumps(
                {
                    "status": "noop",
                    "reason": "free_margin_too_small",
                    "free_margin": basis_value,
                    "min_required": min_free,
                }
            )
        )
        return

    if price <= 0.0:
        print(json.dumps({"status": "noop", "reason": "bad_price", "price": price}))
        return

    # Riski tilivaluutassa
    risk_cash_acc = basis_value * (risk_pct / 100.0)

    # Stop-etäisyys hinnan valuutassa
    stop_abs_price_ccy = price * (stop_pct / 100.0)
    price_ccy = _guess_price_ccy(symbol)

    # Muunna riskisumma hinnan valuuttaan
    risk_cash_price_ccy, fxinfo = _convert_risk_to_price_ccy(
        risk_cash_acc, account_ccy, price_ccy
    )

    units_raw = 0.0
    if stop_abs_price_ccy > 0:
        units_raw = risk_cash_price_ccy / stop_abs_price_ccy

    # Pyöristys min_unitsiin
    units = math.floor(units_raw / min_units) * min_units

    if units <= 0 or signal == 0:
        print(
            json.dumps(
                {
                    "status": "noop",
                    "reason": "no_signal_or_too_small",
                    "signal": signal,
                    "units_raw": units_raw,
                    "units": units,
                }
            )
        )
        return

    fee = (fee_bps / 10000.0) * price * units

    out = {
        "symbol": symbol,
        "tf": tf,
        "side": "BUY" if signal > 0 else "SELL",
        "units": round(units, 6),
        "price": price,
        "notional": round(price * round(units, 6), 8),
        "stop_abs": round(stop_abs_price_ccy, 6),
        "fee": round(fee, 6),
        "risk": {
            "basis_used": basis,
            "basis_value": round(basis_value, 2),
            "risk_pct": risk_pct,
            "risk_cash_account_ccy": round(risk_cash_acc, 6),
            "account_ccy": account_ccy,
            "price_ccy": price_ccy,
            "fx_used": fxinfo,
            "leverage_max": leverage_max,
        },
    }
    try:
        print(json.dumps(out, ensure_ascii=False))
    except BrokenPipeError:
        # putki kiinni (esim. downstream lopetti) -> hiljennä
        try:
            sys.stdout.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
