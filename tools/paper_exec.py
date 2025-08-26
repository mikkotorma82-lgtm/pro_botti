from __future__ import annotations
import sys, json, csv, time, os, pathlib, requests
from tools._dotenv import load_dotenv

load_dotenv()

LOG = pathlib.Path("data/paper_trades.csv")


def _ensure_log():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        with LOG.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "ts",
                    "symbol",
                    "tf",
                    "side",
                    "units",
                    "price",
                    "notional",
                    "stop_abs",
                    "basis",
                    "basis_value",
                    "fee",
                    "extra",
                ]
            )


def _send_tg(msg: str):
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    cid = os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and cid):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data={"chat_id": cid, "text": msg, "parse_mode": "HTML"},
            timeout=20,
        )
    except Exception:
        pass


def main():
    raw = sys.stdin.read().strip()
    data = json.loads(raw)
    r = data.get("risk", {})
    side = data.get("signal", 0)
    side_txt = "BUY" if side > 0 else ("SELL" if side < 0 else "FLAT")
    units = float(r.get("suggested_units", 0))
    price = float(r.get("price", data.get("price")))
    stop_abs = float(r.get("stop_abs", 0))
    fee = float(r.get("fee_estimate", 0))
    notional = units * price
    symbol = data.get("symbol", "NA")
    tf = data.get("tf", "")
    # kirjaa
    _ensure_log()
    with LOG.open("a", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                int(time.time()),
                symbol,
                tf,
                side_txt,
                units,
                price,
                notional,
                stop_abs,
                r.get("basis_used"),
                r.get("basis_value"),
                fee,
                json.dumps({"proba": data.get("proba", {})}),
            ]
        )

    # lähetä tiivis TG-häly
    pmax = None
    try:
        proba = data.get("proba", {})
        if isinstance(proba, dict) and proba:
            pmax = max(proba.values())
    except Exception:
        pass
    msg = (
        f"⚙️ <b>Paper trade</b>\n"
        f"{'📈' if side>0 else '📉'} <b>{side_txt}</b> <code>{symbol}</code> {tf} @ <b>{price:.6g}</b>\n"
        f"size: <code>{units:.6g}</code>  notion: <code>{notional:.6g}</code>\n"
        f"stop≈ <code>{stop_abs:.6g}</code> | fee≈ <code>{fee:.2f}</code>\n"
        f"basis: <code>{r.get('basis_used')}</code>={r.get('basis_value')}\n"
        f"{('p(max)=' + str(round(pmax,3))) if pmax is not None else ''}"
    )
    _send_tg(msg)

    # tulosta kuitti stdoutiin
    out = {
        "ok": True,
        "executed": {
            "symbol": symbol,
            "tf": tf,
            "side": side_txt,
            "units": units,
            "price": price,
            "notional": notional,
            "stop_abs": stop_abs,
            "fee": fee,
        },
        "log_file": str(LOG),
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
