#!/usr/bin/env bash
set -Eeuo pipefail

# --- Peruspolut ---
ROOT="/root/pro_botti"
VENV="$ROOT/venv"
TOOLS="$ROOT/tools"
MODELS="$ROOT/models"
DATA="$ROOT/data/history"
LOGS="$ROOT/logs"

mkdir -p "$TOOLS" "$MODELS" "$DATA" "$LOGS"

# --- Venv ja paketit ---
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
pip install --no-input -U pip wheel
pip install --no-input -U pandas numpy scikit-learn joblib pyarrow fastparquet ccxt yfinance xgboost requests matplotlib
deactivate

# --- botti.env: pysyvät asetukset ---
cp -a "$ROOT/botti.env" "$ROOT/botti.env.bak.$(date +%s)" 2>/dev/null || true

# Aseta/korvaa vain tarvittavat rivit, token-riveihin ei kosketa
ensure_kv () { grep -q "^$1=" "$ROOT/botti.env" && sed -i -E "s|^$1=.*|$1=$2|" "$ROOT/botti.env" || echo "$1=$2" >> "$ROOT/botti.env"; }
ensure_kv SYMBOLS "$(grep -E '^SYMBOLS=' "$ROOT/botti.env" | cut -d= -f2- | tr -d '\r' || echo 'BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT')"
ensure_kv TFS "15m,1h,4h"
ensure_kv TRAIN_INTERVAL_MIN "180"
ensure_kv TRAIN_MAX_WORKERS "4"
ensure_kv HORIZON_BARS "1"
ensure_kv HIST_YEARS_15M "2"
ensure_kv HIST_YEARS_1H "4"
ensure_kv HIST_YEARS_4H "10"
ensure_kv TELEGRAM_ENABLE "1"
# (BUY_THR/SELL_THR/COOLDOWN/BROKER jätetään nykyiseen arvoon ellei jo ole)
grep -q '^BUY_THR=' "$ROOT/botti.env"      || echo 'BUY_THR=0.52' >> "$ROOT/botti.env"
grep -q '^SELL_THR=' "$ROOT/botti.env"     || echo 'SELL_THR=0.48' >> "$ROOT/botti.env"
grep -q '^COOLDOWN_SECS=' "$ROOT/botti.env"|| echo 'COOLDOWN_SECS=60' >> "$ROOT/botti.env"

# Poista täsmälleen identtiset duplikaattirivit (säilyttää ensimmäisen esiintymän)
awk '!seen[$0]++' "$ROOT/botti.env" > "$ROOT/botti.env.tmp" && mv "$ROOT/botti.env.tmp" "$ROOT/botti.env"

# --- Telegram helper (ei koske token-riveihin) ---
cat > "$TOOLS/tele.py" <<'PY'
import os, sys, requests, json, time
EN=os.environ.get("TELEGRAM_ENABLE","0")=="1"
TOK=os.environ.get("TELEGRAM_BOT_TOKEN"); CHAT=os.environ.get("TELEGRAM_CHAT_ID")
def send(text, parse="Markdown"):
    if not EN or not TOK or not CHAT: return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{TOK}/sendMessage",
                        data={"chat_id":CHAT,"text":text,"parse_mode":parse})
        return r.ok
    except Exception as e:
        sys.stderr.write(f"[tele] {e}\n"); return False

def send_photo(path, caption=""):
    if not EN or not TOK or not CHAT: return False
    try:
        with open(path,"rb") as f:
            r=requests.post(f"https://api.telegram.org/bot{TOK}/sendPhoto",
                            data={"chat_id":CHAT,"caption":caption},
                            files={"photo":f})
        return r.ok
    except Exception as e:
        sys.stderr.write(f"[tele] {e}\n"); return False
if __name__=="__main__":
    print(send("🔧 tele.py ok"))
PY

# --- Yhteinen features-moduuli (trainer & live voivat käyttää samaa) ---
cat > "$TOOLS/build_features.py" <<'PY'
import numpy as np, pandas as pd

def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def _rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / (dn.replace(0,np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-prev_c).abs(), (l-prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Palauttaa 9-numeroista featurea, ei käytä tulevaisuuden tietoa.
    Edellyttää kolumnit: time, open, high, low, close, volume
    """
    df = df.sort_values("time").reset_index(drop=True)
    c, v = df["close"], df["volume"]
    # perusmomentumit
    f = pd.DataFrame()
    f["ret1"] = c.pct_change(1)
    f["ret3"] = c.pct_change(3)
    f["ret6"] = c.pct_change(6)
    # vola/atr
    atr = _atr(df, 14)
    f["atr14n"] = (atr / c).fillna(0)
    # trendi: EMA12/26 suhteutettuna
    ema12 = _ema(c,12); ema26=_ema(c,26)
    f["ema12n"] = (ema12/c)-1.0
    f["ema26n"] = (ema26/c)-1.0
    # BB-z
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std().replace(0,np.nan)
    f["boll_z"] = ((c - sma20)/std20).replace([np.inf,-np.inf],np.nan)
    # vol z
    vmean = v.rolling(20).mean()
    vstd  = v.rolling(20).std().replace(0,np.nan)
    f["vol_z"] = ((v - vmean)/vstd).replace([np.inf,-np.inf],np.nan)
    # rsi
    f["rsi14"] = _rsi(c,14)/100.0
    f = f.replace([np.inf,-np.inf], np.nan).fillna(0.0)
    return f
PY

# --- Backfill: krypto CCXT + fallback yfinance (forex/indeksit/osakkeet) ---
cat > "$TOOLS/backfill.py" <<'PY'
import os, sys, time, math, json, re
import pandas as pd
from datetime import datetime, timedelta, timezone

# Valinnainen ccxt/yf
try:
    import ccxt
except Exception:
    ccxt=None
import yfinance as yf

OUT=os.path.join(os.environ.get("ROOT","/root/pro_botti"),"data","history")
os.makedirs(OUT, exist_ok=True)

def years_to_ms(years: int) -> int:
    # 365.25 päivää/vuosi
    return int(years*365.25*24*3600*1000)

def tf_to_minutes(tf:str)->int:
    return {"15m":15, "1h":60, "4h":240}[tf]

def normalize_symbol(sym:str)->str:
    # BTCUSDT -> BTC/USDT ; ETHUSD -> ETH/USD ; EURUSD -> EUR/USD
    m = re.match(r"^([A-Z]+?)(USDT|USD|EUR|GBP)$", sym)
    return f"{m.group(1)}/{m.group(2)}" if m else sym

def is_crypto(sym:str)->bool:
    return sym.endswith(("USDT","USDC","BTC","ETH"))

def yf_ticker(sym:str)->str:
    # Forex
    if sym in ("EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF"):
        return sym + "=X"
    # Indeksit
    if sym=="US500": return "^GSPC"
    if sym=="US100": return "^NDX"
    # osakkeet kuten AAPL, NVDA, TSLA...
    return sym

def write_parquet(path, df):
    cols = ["time","open","high","low","close","volume"]
    df = df[cols].copy()
    df.sort_values("time", inplace=True)
    df.to_parquet(path, index=False)

def fetch_crypto_ccxt(sym:str, tf:str, years:int):
    ex = ccxt.binance({'enableRateLimit': True}) if ccxt else None
    if ex is None:
        raise RuntimeError("ccxt not available")
    u = normalize_symbol(sym)
    ex.load_markets()
    if u not in ex.markets:
        raise RuntimeError(f"{sym}: symbol not supported on Binance")
    ms_per = ex.parse_timeframe(tf) * 1000
    since = ex.milliseconds() - years_to_ms(years)
    # CCXT rajoittaa ~1000–1500 kpl/fetch; haetaan paloissa
    limit = 1000
    all_rows = []
    now = ex.milliseconds()
    while since < now - ms_per:
        ohlcvs = ex.fetch_ohlcv(u, timeframe=tf, since=since, limit=limit)  # [ms, o,h,l,c,v]
        if not ohlcvs: break
        since = ohlcvs[-1][0] + ms_per
        all_rows.extend(ohlcvs)
        # kevyt throttle
        time.sleep(0.2)
    if not all_rows:
        raise RuntimeError("no data")
    df = pd.DataFrame(all_rows, columns=["time","open","high","low","close","volume"])
    write_parquet(os.path.join(OUT, f"{sym}_{tf}.parquet"), df)
    return len(df)

def fetch_yf(sym:str, tf:str, years:int):
    # yfinance intervallit: 15m (max 60d) -> joudutaan stitchaamaan;
    # 1h ja 4h saadaan helposti (max 730d per pyyntö käytännössä).
    # Tehdään varma silmukka aikavälin yli.
    itv = {"15m":"15m","1h":"60m","4h":"240m"}[tf]
    ticker = yf_ticker(sym)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(years*365.25))
    step_days = 50 if tf=="15m" else (365 if tf=="1h" else 365*5)
    parts=[]
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=step_days), end)
        df = yf.download(tickers=ticker, interval=itv, start=cur, end=nxt, progress=False, prepost=False)
        if df is not None and not df.empty:
            df = df.rename(columns={
                "Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"
            }).reset_index()
            # yfinance antaa Timestamp kolumnin nimellä Datetime/DatetimeUTC
            time_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else df.columns[0])
            df["time"] = pd.to_datetime(df[time_col], utc=True).astype("int64")//10**6
            df = df[["time","open","high","low","close","volume"]]
            parts.append(df)
        cur = nxt
        time.sleep(0.2)
    if not parts:
        raise RuntimeError("no data from yfinance")
    df = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    write_parquet(os.path.join(OUT, f"{sym}_{tf}.parquet"), df)
    return len(df)

def backfill_one(sym:str, tf:str, years:int):
    if is_crypto(sym):
        try:
            rows = fetch_crypto_ccxt(sym, tf, years)
            return {"sym":sym,"tf":tf,"rows":rows,"src":"binance"}
        except Exception as e:
            # fallback yf jos mahdollista
            try:
                rows = fetch_yf(sym, tf, years)
                return {"sym":sym,"tf":tf,"rows":rows,"src":"yfinance_fallback"}
            except Exception as e2:
                return {"sym":sym,"tf":tf,"err":str(e2)}
    else:
        try:
            rows = fetch_yf(sym, tf, years)
            return {"sym":sym,"tf":tf,"rows":rows,"src":"yfinance"}
        except Exception as e:
            return {"sym":sym,"tf":tf,"err":str(e)}

if __name__=="__main__":
    sym, tf, years = sys.argv[1], sys.argv[2], int(sys.argv[3])
    print(json.dumps(backfill_one(sym,tf,years)))
PY

# --- Trainer daemon (continual) ---
cat > "$TOOLS/trainer_daemon.py" <<'PY'
import os, time, json, math, traceback
from pathlib import Path
import numpy as np, pandas as pd
from joblib import dump
from datetime import datetime, timezone

from tools.build_features import build_features
from tools.tele import send as tgsend, send_photo as tgphoto

# ML
USE_XGB = True
try:
    import xgboost as xgb
except Exception:
    USE_XGB = False
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split

ROOT = Path(os.environ.get("ROOT","/root/pro_botti"))
DATA = ROOT/"data/history"
MODELS = ROOT/"models"
LOGS = ROOT/"logs"
MODELS.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

def log(msg):
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    (LOGS/"trainer.log").open("a").write(line+"\n")

def load_env_list(key, default):
    v = os.environ.get(key, default)
    return [x.strip() for x in v.split(",") if x.strip()]

def horizon():
    try: return int(os.environ.get("HORIZON_BARS","1"))
    except: return 1

def metrics_from_preds(close: pd.Series, y_true: np.ndarray, p: np.ndarray):
    # suunta + yksinkertainen pnl-approx
    ret1 = close.pct_change().shift(-1).values
    long = p>=0.55; short = p<=0.45
    sig = np.where(long, 1, np.where(short,-1,0))
    pnl = np.nansum(sig * ret1[:len(sig)])
    wins = (sig*ret1[:len(sig)]>0).sum()
    losses = (sig*ret1[:len(sig)]<0).sum()
    wr = wins / max(1, wins+losses)
    pf = (np.sum((sig*ret1>0)* (sig*ret1)) / max(1e-12, np.sum((sig*ret1<0)*-(sig*ret1))))
    return {"pnl": float(pnl), "win_rate": float(wr), "pf": float(pf)}

def train_one(sym, tf):
    fpath = DATA/f"{sym}_{tf}.parquet"
    if not fpath.exists():
        raise FileNotFoundError(f"missing {fpath}")
    raw = pd.read_parquet(fpath)
    if not set(["time","open","high","low","close","volume"]).issubset(raw.columns):
        raise ValueError(f"{fpath}: missing required columns")
    feats = build_features(raw)
    y = (raw["close"].shift(-horizon()) > raw["close"]).astype(int).values
    # leikkaa samankokoiseksi
    m = min(len(feats), len(y)-1)
    X = feats.iloc[:m].values
    y = y[:m]
    close = raw["close"].iloc[:m]

    # aikajärjestys, ei sekoitusta
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, shuffle=False)
    if USE_XGB:
        clf = xgb.XGBClassifier(
            max_depth=4, n_estimators=250, subsample=0.8, colsample_bytree=0.8,
            learning_rate=0.05, n_jobs=2, tree_method="hist", objective="binary:logistic"
        )
    else:
        clf = RandomForestClassifier(n_estimators=400, max_depth=6, random_state=42, n_jobs=2)
    pipe = Pipeline([("scaler", StandardScaler()), ("clf", clf)])
    pipe.fit(Xtr, ytr)
    # arvio
    p = pipe.predict_proba(Xte)[:,1]
    met = metrics_from_preds(close.iloc[len(Xtr):], yte, p)
    meta = {
        "symbol": sym, "tf": tf, "horizon": horizon(),
        "features": feats.shape[1], "samples": int(m),
        "win_rate": met["win_rate"], "pf": met["pf"], "pnl_approx": met["pnl"],
        "ts": datetime.now(timezone.utc).isoformat()
    }
    # tallenna atomisesti
    tmp = MODELS/f"pro_{sym}_{tf}.joblib.tmp"
    out = MODELS/f"pro_{sym}_{tf}.joblib"
    dump(pipe, tmp)
    os.replace(tmp, out)
    (MODELS/f"pro_{sym}_{tf}.json").write_text(json.dumps(meta, indent=2))
    return meta

def plot_equity_png(close: pd.Series, y_true: np.ndarray, p: np.ndarray, out_png: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ret1 = close.pct_change().shift(-1).values
    long = p>=0.55; short = p<=0.45
    sig = np.where(long, 1, np.where(short,-1,0))
    pnl = np.nan_to_num(sig * ret1[:len(sig)], nan=0.0)
    eq = (1.0 + pd.Series(pnl)).cumprod()
    plt.figure()
    eq.plot()
    plt.title("Equity (test)")
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()

def loop():
    SYMS = load_env_list("SYMBOLS","BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT")
    TFS  = load_env_list("TFS","15m,1h,4h")
    interval_min = int(os.environ.get("TRAIN_INTERVAL_MIN","180"))
    log(f"Trainer käynnissä. SYMBOLS={SYMS} TFS={TFS} interval={interval_min}min lookahead={horizon()} xgb={USE_XGB}")
    while True:
        ok, err = [], []
        for s in SYMS:
            for tf in TFS:
                try:
                    meta = train_one(s, tf)
                    ok.append(f"{s} {tf}: pf={meta['pf']:.2f} wr={meta['win_rate']*100:.1f}% features={meta['features']}")
                except Exception as e:
                    err.append(f"{s}_{tf}: {e}")
                    traceback.print_exc()
        # raportoi
        if ok:
            tgsend("🏋️ *Koulutus valmis*\n" + "✅ " + "\n✅ ".join(ok))
        if err:
            tgsend("⚠️ *Virheitä:*\n" + "\n".join(err))
        # nuku
        for _ in range(interval_min*60):
            time.sleep(1)
        # päivitä universumi ja tf:t mahdollisiin env-muutoksiin
        SYMS = load_env_list("SYMBOLS","BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,XRPUSDT")
        TFS  = load_env_list("TFS","15m,1h,4h")

if __name__=="__main__":
    loop()
PY

# --- systemd: trainer vain taustalle, liveä ei kosketa ---
cat > /etc/systemd/system/pro-botti-trainer.service <<'UNIT'
[Unit]
Description=Pro Botti - Continual Trainer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/pro_botti
EnvironmentFile=/root/pro_botti/botti.env
Environment=ROOT=/root/pro_botti
ExecStart=/root/pro_botti/venv/bin/python tools/trainer_daemon.py
Restart=always
RestartSec=10
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now pro-botti-trainer.service

# --- Ensimmäinen backfill (ei pysäytä liveä) ---
source "$ROOT/botti.env"
IFS=',' read -r -a SYMS <<< "${SYMBOLS}"
IFS=',' read -r -a TFS_ARR <<< "${TFS}"

declare -A YEARS
YEARS["15m"]="${HIST_YEARS_15M:-2}"
YEARS["1h"]="${HIST_YEARS_1H:-4}"
YEARS["4h"]="${HIST_YEARS_4H:-10}"

echo "⏳ Backfill alkaa..."
for s in "${SYMS[@]}"; do
  s="${s//[[:space:]]/}"
  [ -z "$s" ] && continue
  for tf in "${TFS_ARR[@]}"; do
    tf="${tf//[[:space:]]/}"
    y="${YEARS[$tf]}"
    /root/pro_botti/venv/bin/python "$TOOLS/backfill.py" "$s" "$tf" "$y" || true
  done
done
echo "✅ Backfill valmis"

# --- Siisti historia: varmista 'time' ja järjestys (jos vanhoja tiedostoja) ---
/usr/bin/python3 - <<'PY'
import os, pandas as pd, glob
base="/root/pro_botti/data/history"
ok=0; fixed=0
for p in glob.glob(base+"/*.parquet"):
    df=pd.read_parquet(p)
    need={"time","open","high","low","close","volume"}
    if not need.issubset(df.columns):
        # yritä korjata 'ts'->'time'
        if "ts" in df.columns: df=df.rename(columns={"ts":"time"})
    df=df[["time","open","high","low","close","volume"]].sort_values("time")
    df.to_parquet(p, index=False); fixed+=1
print(f"[DONE] fixed={fixed}")
PY

# --- Telegram kuittaus ---
/root/pro_botti/venv/bin/python - <<'PY'
import os
from tools.tele import send
send("✅ *asennus.sh* valmis\n• Historia: 15m=2v, 1h=4v, 4h=10v\n• Trainer taustalla (systemd)\n• Livea ei pysäytetty\n• Featurepipeline synkassa")
PY

echo "All set ✔"
