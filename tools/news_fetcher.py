#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
news_fetcher.py — Talousuutiskalenterin täyttö live-daemonille.

Tavoite:
- Tuottaa/ylläpitää tiedostoa data/news_schedule.json formaattiin:
  [
    {"ts":"2025-09-01T12:30:00Z","label":"CPI (US)","impact":"high"},
    {"ts":"2025-09-01T18:00:00Z","label":"FOMC","impact":"high"},
    ...
  ]

Miten käytät:
1) MANUAALINEN LISÄYS:
   python tools/news_fetcher.py --add "2025-09-01 12:30" "CPI (US)" high --tz "Europe/Helsinki"
   -> konvertoi UTC:hen ja lisää/mergeää news_schedule.json -tiedostoon.

2) CSV-TUONTI (oma kalenteri):
   CSV-sarakkeet: datetime,label,impact,tz (tz valinnainen, esim. Europe/Helsinki)
   python tools/news_fetcher.py --from-csv /path/to/calendar.csv

3) YLEINEN JSON-ENDPOINT (jos sinulla on oma feedi):
   Ympäristömuuttuja NEWS_FEED_URL voi osoittaa JSONiin muodossa:
   [{"ts":"2025-09-01T12:30:00Z","label":"CPI","impact":"high"}, ...]
   python tools/news_fetcher.py --fetch
   -> hakee URL:ista ja yhdistää olemassa olevaan.

Huom:
- Skripti EI vaadi ulkoista API-avainta.
- Duplikaatit poistetaan avaimella (ts,label).
- Virheissä skripti ei kaadu, vaan ohittaa virheelliset rivit.
"""

import os, sys, json, csv
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict

try:
    import requests  # valinnainen, vain --fetch käytössä
except Exception:
    requests = None

try:
    import pytz
except Exception:
    pytz = None

ROOT = Path("/root/pro_botti")
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)
NEWS_F = DATA / "news_schedule.json"

def load_news() -> List[Dict]:
    if NEWS_F.exists():
        try:
            return json.loads(NEWS_F.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_news(items: List[Dict]):
    # normalisoi ja deduplikoi
    seen = set()
    out = []
    for e in items:
        try:
            ts = e.get("ts")
            lab = (e.get("label") or "").strip()
            imp = (e.get("impact") or "medium").lower()
            # validi ts ISO
            _ = datetime.fromisoformat(ts.replace("Z","+00:00"))
            key = (ts, lab)
            if key in seen: 
                continue
            seen.add(key)
            out.append({"ts": ts, "label": lab, "impact": imp})
        except Exception:
            continue
    # järjestä aikajärjestykseen
    out.sort(key=lambda x: x["ts"])
    NEWS_F.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out

def to_utc_iso(dt_str: str, tz_name: str=None) -> str:
    """
    dt_str: 'YYYY-MM-DD HH:MM'
    tz_name: esim. 'Europe/Helsinki' (valinnainen)
    """
    if tz_name and pytz is None:
        raise RuntimeError("pytz ei asennettu; poista --tz tai asenna pytz")
    if tz_name and pytz:
        local = pytz.timezone(tz_name)
        naive = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        aware = local.localize(naive)
        utc_dt = aware.astimezone(timezone.utc)
    else:
        # tulkitaan jo UTC:ksi
        utc_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def add_event(dt_str: str, label: str, impact: str="medium", tz_name: str=None):
    news = load_news()
    ts = to_utc_iso(dt_str, tz_name)
    news.append({"ts": ts, "label": label, "impact": impact.lower()})
    out = save_news(news)
    print(f"[news] added: {ts} {label} ({impact.lower()})  total={len(out)}")

def import_csv(path: str):
    news = load_news()
    with open(path, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            dt_str = (row.get("datetime") or "").strip()
            label  = (row.get("label") or "").strip()
            impact = (row.get("impact") or "medium").strip().lower()
            tz_name= (row.get("tz") or "").strip() or None
            if not dt_str or not label: 
                continue
            try:
                ts = to_utc_iso(dt_str, tz_name)
                news.append({"ts": ts, "label": label, "impact": impact})
            except Exception:
                continue
    out = save_news(news)
    print(f"[news] imported CSV: {path}  total={len(out)}")

def fetch_from_url():
    url = os.getenv("NEWS_FEED_URL","").strip()
    if not url:
        print("[news] NEWS_FEED_URL ei ole asetettu; ohitetaan --fetch", file=sys.stderr)
        return
    if requests is None:
        print("[news] requests ei asennettu; asenna tai käytä --add/--from-csv", file=sys.stderr)
        return
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        arr = r.json()
        if not isinstance(arr, list):
            print("[news] virheellinen JSON (odotettiin listaa)", file=sys.stderr)
            return
        news = load_news()
        for e in arr:
            ts = e.get("ts")
            label = e.get("label")
            impact = (e.get("impact") or "medium").lower()
            if not ts or not label:
                continue
            news.append({"ts": ts, "label": label, "impact": impact})
        out = save_news(news)
        print(f"[news] fetched from {url}  total={len(out)}")
    except Exception as e:
        print(f"[news] fetch failed: {e}", file=sys.stderr)

def main():
    import argparse
    ap = argparse.ArgumentParser(description="News schedule manager")
    ap.add_argument("--add", nargs=3, metavar=("YYYY-MM-DD HH:MM","LABEL","IMPACT"),
                    help="Lisää yksi tapahtuma paikallisaikana (tai UTC jos --tz puuttuu).")
    ap.add_argument("--tz", default=None, help="Aikavyöhyke esim. Europe/Helsinki (vain --add kanssa).")
    ap.add_argument("--from-csv", help="Tuo CSV:stä (sar: datetime,label,impact[,tz])")
    ap.add_argument("--fetch", action="store_true", help="Hakee NEWS_FEED_URL:ista ja päivittää listan.")
    args = ap.parse_args()

    if args.add:
        dt, label, impact = args.add
        add_event(dt, label, impact, tz_name=args.tz)
        return
    if args.from_csv:
        import_csv(args.from_csv)
        return
    if args.fetch:
        fetch_from_url()
        return

    # tulosta nykyinen lista
    news = load_news()
    print(json.dumps(news, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
