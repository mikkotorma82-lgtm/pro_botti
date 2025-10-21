#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_tune.py — Automaattinen kynnysten & riskin viritys PF:n mukaan.

Mitä tekee (yhdellä ajolla):
- Lukee mallit hakemistosta /root/pro_botti/models (pro_*.json).
- Jokaiselle (symbol, TF) mallille:
    * Jos pf >= PF_TARGET_HI  -> lasketaan varovasti kynnystä (lisätään volyymiä).
    * Jos pf <  PF_TARGET_MIN -> nostetaan kynnystä (filtteröidään) ja leikataan riskikerrointa.
    * Muussa tapauksessa pieni hienosäätö kohti tavoitealuetta.
- Tallentaa päivitetyt meta-tiedostot paikalleen (varmuuskopioi .bak päälle).
- (valinnainen) Päivittää config/active_symbols.txt top-per-cluster listan (PF≥min).
- (valinnainen) Kirjoittaa config/risk_overrides.json (symbolikohtaiset riskikertoimet).
- (valinnainen) Ilmoittaa yhteenvedon Telegramiin (tools.tele.send).

Ympäristömuuttujat (kaikki valinnaisia):
  MODELS_DIR=/root/pro_botti/models
  CONFIG_DIR=/root/pro_botti/config
  PF_TARGET_MIN=1.30
  PF_TARGET_HI=1.60
  PF_MIN_FOR_ACTIVE=1.30         # kun --write-active
  THR_STEP=0.01                   # yksittäinen säätöaskel
  THR_MIN=0.50
  THR_MAX=0.99
  RISK_BASE=0.10                  # globaali RISK_PCT ohjearvo
  RISK_FLOOR=0.02                 # alin symbolikohtainen kerroin * RISK_BASE
  RISK_CEIL=0.20                  # ylin symbolikohtainen kerroin * RISK_BASE
  RISK_STEP=0.01                  # yhden ajon riskin säätöaskel absoluuttisesti
  TELEGRAM_NOTIFY=1               # 1=lähetä tg, muuten ei

Käyttö:
  python tools/auto_tune.py
  python tools/auto_tune.py --dry-run
  python tools/auto_tune.py --write-active
  python tools/auto_tune.py --write-active --per-cluster 6

Ajastukseen (esim. kerran yössä klo 02:15):
  crontab -e
  15 2 * * * /root/pro_botti/venv/bin/python /root/pro_botti/tools/auto_tune.py --write-active >> /root/pro_botti/logs/auto_tune.log 2>&1

Huom:
- Skripti ei tiedä toteutuneita “trades per threshold” -käyriä, joten säätö on
  varovainen heuristiikka PF:stä. Trainerin on hyvä kirjoittaa jatkossa
  ai_gate-telemetriaa, jolloin säätö voidaan muuttaa grid-hakuiseksi.
"""

import os, sys, json, glob, shutil, subprocess
from pathlib import Path
from typing import Dict, Tuple, List

ROOT = Path("/root/pro_botti")
MODELS_DIR = Path(os.getenv("MODELS_DIR", str(ROOT / "models")))
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(ROOT / "config")))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

PF_TARGET_MIN = float(os.getenv("PF_TARGET_MIN", "1.30"))
PF_TARGET_HI  = float(os.getenv("PF_TARGET_HI",  "1.60"))
PF_MIN_FOR_ACTIVE = float(os.getenv("PF_MIN_FOR_ACTIVE", str(PF_TARGET_MIN)))

THR_STEP = float(os.getenv("THR_STEP", "0.01"))
THR_MIN  = float(os.getenv("THR_MIN",  "0.50"))
THR_MAX  = float(os.getenv("THR_MAX",  "0.99"))

RISK_BASE = float(os.getenv("RISK_BASE", "0.10"))
RISK_FLOOR= float(os.getenv("RISK_FLOOR","0.02"))
RISK_CEIL = float(os.getenv("RISK_CEIL", "0.20"))
RISK_STEP = float(os.getenv("RISK_STEP", "0.01"))

TELEGRAM_NOTIFY = os.getenv("TELEGRAM_NOTIFY", "1").strip() == "1"

RISK_OVR_F = CONFIG_DIR / "risk_overrides.json"
ACTIVE_F   = CONFIG_DIR / "active_symbols.txt"

# Telegram (valinnainen)
def tg_send(msg: str):
    if not TELEGRAM_NOTIFY:
        return
    try:
        # tools.tele.send(message: str)
        from tools.tele import send as tgsend
        tgsend(msg)
    except Exception:
        # hiljaa, ei kriittinen
        pass

def parse_model_path(p: Path) -> Tuple[str, str]:
    # pro_SYMBOL_TF.json
    try:
        stem = p.stem
        _, sym, tf = stem.split("_", 2)
        return sym, tf
    except Exception:
        return "", ""

def load_meta(p: Path) -> Dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_meta(p: Path, meta: Dict):
    # varmuuskopio
    try:
        shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
    except Exception:
        pass
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

def ensure_thr(meta: Dict) -> Dict:
    """Muodosta yhtenäinen rakenne: ai_thresholds = {'long': x, 'short': y}."""
    thr = meta.get("ai_thresholds")
    if isinstance(thr, dict):
        # normalize keys
        long_thr  = float(thr.get("long")  or thr.get("buy")  or 0.50)
        short_thr = float(thr.get("short") or thr.get("sell") or 0.50)
    else:
        long_thr = short_thr = 0.50
    long_thr  = max(THR_MIN, min(THR_MAX, float(long_thr)))
    short_thr = max(THR_MIN, min(THR_MAX, float(short_thr)))
    meta["ai_thresholds"] = {"long": long_thr, "short": short_thr}
    return meta

def cluster_of(sym: str) -> str:
    s = sym.upper()
    if s.endswith("USDT") or s in ("BTCUSD","ETHUSD","SOLUSD","XRPUSD"):
        return "crypto"
    if s in ("US100","US500"):
        return "indices"
    if s in ("EURUSD","GBPUSD"):
        return "fx"
    return "equities"

def tune_thresholds(pf: float, thr_long: float, thr_short: float) -> Tuple[float, float, str]:
    """
    Heuristiikka:
      - jos pf >= PF_TARGET_HI: laske kynnystä varovasti (lisää treidejä)
      - jos pf <  PF_TARGET_MIN: nosta kynnystä (filtteröi)
      - väliin: hienosäätö kohti keskialuetta (pieni askel)
    """
    action = "hold"
    if pf >= PF_TARGET_HI:
        thr_long  = max(THR_MIN, min(THR_MAX, thr_long  - THR_STEP))
        thr_short = max(THR_MIN, min(THR_MAX, thr_short - THR_STEP))
        action = "loosen"
    elif pf < PF_TARGET_MIN:
        thr_long  = max(THR_MIN, min(THR_MAX, thr_long  + THR_STEP))
        thr_short = max(THR_MIN, min(THR_MAX, thr_short + THR_STEP))
        action = "tighten"
    else:
        # alueella — pieni liike kohti keskikohtaa (tässä: nothing / todella pieni)
        action = "minor"
        # valinnainen ultra-pieni säätö:
        # thr_long  = max(THR_MIN, min(THR_MAX, thr_long  + (THR_STEP*0.25 if pf < (PF_TARGET_MIN+PF_TARGET_HI)/2 else -THR_STEP*0.25)))
        # thr_short = max(THR_MIN, min(THR_MAX, thr_short + (THR_STEP*0.25 if pf < (PF_TARGET_MIN+PF_TARGET_HI)/2 else -THR_STEP*0.25)))
    return thr_long, thr_short, action

def tune_risk(pf: float, current: float) -> Tuple[float, str]:
    """
    Säädä symbolikohtaista riskiprosenttia (kerroin suoraan, ei suhteessa mallin konf-scoreen).
    Tavoite: matalalla PF:llä leikataan, korkealla kasvatetaan varovaisesti.
    """
    newv = current
    if pf >= PF_TARGET_HI:
        newv = min(RISK_CEIL, current + RISK_STEP)
        return newv, "risk++"
    elif pf < PF_TARGET_MIN:
        newv = max(RISK_FLOOR, current - RISK_STEP)
        return newv, "risk--"
    return newv, "risk="

def load_risk_overrides() -> Dict[str, float]:
    if RISK_OVR_F.exists():
        try:
            return json.loads(RISK_OVR_F.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_risk_overrides(d: Dict[str, float]):
    RISK_OVR_F.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

def write_active_symbols(min_pf: float, per_cluster: int = 8):
    """
    Kutsuu live_readiness_report.py:tä, jos se löytyy, kirjoittamaan active_symbols.txt.
    """
    script = ROOT / "tools" / "live_readiness_report.py"
    if not script.exists():
        return False, "live_readiness_report.py puuttuu"
    try:
        cmd = [
            sys.executable, str(script),
            "--min-pf", f"{min_pf:.2f}",
            "--write-active",
            "--per-cluster", str(per_cluster)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True, "active_symbols päivitetty"
    except subprocess.CalledProcessError as e:
        return False, f"write-active epäonnistui: {e}"
    except Exception as e:
        return False, f"write-active poikkeus: {e}"

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Auto tune thresholds and risk based on PF")
    ap.add_argument("--dry-run", action="store_true", help="Älä kirjoita mitään, tulosta vain muutokset.")
    ap.add_argument("--write-active", action="store_true", help="Päivitä config/active_symbols.txt PF-rajalla.")
    ap.add_argument("--per-cluster", type=int, default=8, help="Top-N per klusteri active_symbols.txt:ään.")
    args = ap.parse_args()

    models = sorted(MODELS_DIR.glob("pro_*.json"))
    if not models:
        print(f"[auto_tune] ei malleja hakemistossa: {MODELS_DIR}")
        return

    risk_map = load_risk_overrides()
    changes: List[str] = []
    touched = 0

    for p in models:
        sym, tf = parse_model_path(p)
        if not sym or not tf:
            continue
        meta = load_meta(p)
        if not meta:
            continue

        pf = float(meta.get("pf") or 0.0)
        wr = float(meta.get("win_rate") or 0.0)
        meta = ensure_thr(meta)
        thr_long  = float(meta["ai_thresholds"]["long"])
        thr_short = float(meta["ai_thresholds"]["short"])

        # kynnysten säätö
        new_long, new_short, tact = tune_thresholds(pf, thr_long, thr_short)

        # riskin säätö symbolitasolla
        cur_risk = float(risk_map.get(sym, RISK_BASE))
        new_risk, tact_r = tune_risk(pf, cur_risk)

        # koosta logirivi
        ch = []
        if (new_long, new_short) != (thr_long, thr_short):
            ch.append(f"thr[{thr_long:.2f}/{thr_short:.2f}->{new_long:.2f}/{new_short:.2f} {tact}]")
            meta["ai_thresholds"] = {"long": new_long, "short": new_short}
        if abs(new_risk - cur_risk) >= 1e-9:
            ch.append(f"risk[{cur_risk:.2f}->{new_risk:.2f} {tact_r}]")
            risk_map[sym] = float(f"{new_risk:.6f}")

        if ch:
            touched += 1
            line = f"{sym:<10} {tf:<5} pf={pf:.2f} wr={wr*100:.1f}%  " + "  ".join(ch)
            changes.append(line)
            if not args.dry_run:
                save_meta(p, meta)

    # tallenna risk_overrides
    if not args.dry_run:
        save_risk_overrides(risk_map)

    # (valinnainen) päivitä active_symbols
    active_msg = ""
    if args.write_active:
        ok, msg = write_active_symbols(PF_MIN_FOR_ACTIVE, per_cluster=args.per_cluster)
        active_msg = f" | {msg}" if msg else ""

    # tuloste + tg
    header = f"[auto_tune] models={len(models)} touched={touched}{active_msg}"
    print(header)
    if changes:
        for ln in changes:
            print(" -", ln)

    # lähetä lyhyt TG-kuittaus
    try:
        if changes:
            preview = "\n".join(changes[:12])
            if len(changes) > 12:
                preview += f"\n ... (+{len(changes)-12} lisää)"
        else:
            preview = "Ei muutoksia"
        tg_send(f"{header}\n{preview}")
    except Exception:
        pass

if __name__ == "__main__":
    main()
