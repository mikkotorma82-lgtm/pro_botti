#!/usr/bin/env python3
from __future__ import annotations
import json, os, time, traceback
from pathlib import Path
from meta.config import MetaConfig
from meta.training_runner import run_all

try:
    from tools import reg_agg
except Exception:
    reg_agg = None

try:
    from tools.selector import main as selector_main
except Exception:
    selector_main = None

try:
    # send_big(title: str, lines: List[str], **kwargs)
    from tools.notifier import send_big
except Exception:
    def send_big(*args, **kwargs):
        return False

STATE = Path(__file__).resolve().parents[1] / "state"
STATE.mkdir(parents=True, exist_ok=True)
SUMMARY_JSON = STATE / "meta_train_summary.json"
SELECTED = STATE / "selected_universe.json"
ACTIVE_SYMS = STATE / "active_symbols.json"


def _telegram_enabled() -> bool:
    if os.getenv("META_NOTIFY_SUMMARY", "1") not in ("1", "true", "TRUE", "yes", "YES"):
        return False
    if os.getenv("TELEGRAM_ENABLE", os.getenv("TG_ENABLE", "1")) in ("0", "false", "FALSE", "no", "NO"):
        return False
    return True


def _format_summary(res: dict) -> str:
    ok = [r for r in res.get("results", []) if r.get("status") == "OK"]
    sk = [r for r in res.get("results", []) if r.get("status") == "SKIP"]
    fl = [r for r in res.get("results", []) if r.get("status") == "FAIL"]
    lines = []
    lines.append("📣 META-ensemble koulutus valmis")
    lines.append(f"Exchange: {res.get('exchange')}")
    lines.append(f"TFs: {','.join(res.get('timeframes', []))}")
    lines.append(f"Models: {','.join(res.get('models', []))}")
    lines.append(f"OK={len(ok)} SKIP={len(sk)} FAIL={len(fl)}")
    # esimerkkirivejä onnistuneista
    for r in ok[:10]:
        m = r.get("metrics") or {}
        pf = m.get("ens_pf") or m.get("cv_pf_score_ens") or m.get("cv_pf_score") or "-"
        lines.append(f"✅ {r['symbol']} {r['tf']} pf={pf}")
    # esimerkkirivejä epäonnistuneista
    for r in fl[:5]:
        lines.append(f"❌ {r['symbol']} {r['tf']} {r.get('reason')}")
    return "\n".join(lines)


def _write_active_symbols_from_selection() -> None:
    if not SELECTED.exists():
        return
    try:
        obj = json.loads(SELECTED.read_text() or '{"combos":[]}')
    except Exception:
        return
    combos = obj.get("combos", [])
    syms = sorted({c["symbol"] for c in combos if c.get("symbol")})
    out = {"symbols": syms, "updated_at": int(time.time())}
    tmp = ACTIVE_SYMS.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    tmp.replace(ACTIVE_SYMS)


def main() -> int:
    cfg = MetaConfig()
    res = {}
    rc = 0
    try:
        res = run_all(cfg)
        SUMMARY_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2))

        if _telegram_enabled():
            # Korjattu: send_big vaatii otsikon ja rivit
            try:
                msg = _format_summary(res)
                send_big("📣 META-ensemble koulutus", msg.splitlines(), max_lines=120)
            except Exception:
                # Telegram-ongelmat eivät saa kaataa koulutusta
                pass

    except Exception as e:
        rc = 1
        err = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}
        SUMMARY_JSON.write_text(json.dumps(err, ensure_ascii=False, indent=2))

    # Jälkikäsittely: päivitä aggregaatit ja valinta
    try:
        if reg_agg:
            try:
                reg_agg.merge_from_current("pro")
            except Exception:
                pass
            try:
                reg_agg.merge_from_current("meta")
            except Exception:
                pass
        if selector_main:
            selector_main()
            _write_active_symbols_from_selection()
    except Exception:
        pass

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
