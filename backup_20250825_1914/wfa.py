from __future__ import annotations
import os, json
from pathlib import Path
import numpy as np, pandas as pd
from tools.indicators import ema, rsi, stoch, macd, bb, atr, adx, obv, ichimoku, supertrend

HIST=Path("history"); OUT=Path("data/metrics"); OUT.mkdir(parents=True, exist_ok=True)

def add_features(df:pd.DataFrame)->pd.DataFrame:
    df=df.copy()
    df["ema8"]=ema(df.close,8); df["ema21"]=ema(df.close,21); df["ema50"]=ema(df.close,50); df["ema200"]=ema(df.close,200)
    df["rsi14"]=rsi(df.close,14)
    kf,dfst=stoch(df.high,df.low,df.close); df["stoch_k"]=kf; df["stoch_d"]=dfst
    m,s,h=macd(df.close); df["macd"]=m; df["macd_sig"]=s
    mid,up,lo=bb(df.close); df["bb_mid"]=mid; df["bb_up"]=up; df["bb_lo"]=lo
    df["atr14"]=atr(df.high,df.low,df.close,14)
    adxv, plus_di, minus_di = adx(df.high, df.low, df.close,14); df["adx"]=adxv; df["+di"]=plus_di; df["-di"]=minus_di
    df["obv"]=obv(df.close, df.volume)
    conv, base, sa, sb, lag = ichimoku(df.high,df.low,df.close); df["ich_conv"]=conv; df["ich_base"]=base; df["ich_sa"]=sa; df["ich_sb"]=sb
    st, dir=supertrend(df.high,df.low,df.close); df["supertrend"]=st; df["st_dir"]=dir
    df["ret1"]=df.close.pct_change()
    df["fwd_ret"]=df.close.shift(-1)/df.close - 1.0
    return df

def rules_signal(r:pd.Series)->int:
    votes=0
    if r.ema8>r.ema21>r.ema50>r.ema200: votes+=1
    elif r.ema8<r.ema21<r.ema50<r.ema200: votes-=1
    if r.rsi14>55: votes+=1
    elif r.rsi14<45: votes-=1
    if r.macd>r.macd_sig: votes+=1
    elif r.macd<r.macd_sig: votes-=1
    if r.close>r.bb_mid: votes+=1
    elif r.close<r.bb_mid: votes-=1
    if r.stoch_k>r.stoch_d and r.stoch_k>50: votes+=1
    elif r.stoch_k<r.stoch_d and r.stoch_k<50: votes-=1
    # ichimoku cloud
    cloud_top=max(r.ich_sa, r.ich_sb); cloud_bot=min(r.ich_sa, r.ich_sb)
    if r.close>cloud_top: votes+=1
    elif r.close<cloud_bot: votes-=1
    # supertrend direction
    votes += 1 if r.st_dir>0 else -1
    # ADX filter: jos <15, nollaa heikot signaalit
    if r.adx<15: votes = int(np.sign(votes))  # supista (mutta ei pakota nollaan)
    return int(np.sign(votes))

def wfa_one(sym:str, tf:str, fee_bps:float=2.0, slip_bps:float=1.0, min_trades:int=20)->dict:
    path=HIST/f"{sym}_{tf}.csv"
    if not path.exists(): return {"symbol":sym,"tf":tf,"ok":False,"reason":"no_history"}
    df=pd.read_csv(path, parse_dates=["ts"])
    df=df.rename(columns=str.lower).sort_values("ts").reset_index(drop=True)
    df=add_features(df).dropna().reset_index(drop=True)
    if len(df)<500: return {"symbol":sym,"tf":tf,"ok":False,"reason":"too_short"}

    # Walk-forward: 15m: train 180d test 30d; 1h: train 540d test 90d; 4h: train 1080d test 180d
    if tf=="15m": tr,te = 180,30
    elif tf=="1h": tr,te = 540,90
    else: tr,te = 1080,180

    # ML fallback (scikit-learn LogisticRegression), muuten sääntöpohjainen
    try:
        from tools.lr_safe import SafeLogistic as LogisticRegression
        use_ml=True
    except Exception:
        use_ml=False

    eq=1.0; peak=1.0; maxdd=0.0; trades=0; rets=[]
    pos=0
    last_entry_price=None
    atr_k=2.0

    for start in range(0, len(df)- (tr+te)):
        train=df.iloc[start:start+tr]
        test =df.iloc[start+tr:start+tr+te]

        if use_ml:
            X=train[["ema8","ema21","ema50","ema200","rsi14","macd","macd_sig","bb_mid","stoch_k","stoch_d","adx","obv","st_dir"]].values
            y=(train["fwd_ret"]>0).astype(int).values
            clf=LogisticRegression(max_iter=200)
            try:
                clf.fit(X,y)
            except Exception:
                use_ml=False

        for i, row in test.iterrows():
            sig = rules_signal(row)
            if use_ml:
                xi=row[["ema8","ema21","ema50","ema200","rsi14","macd","macd_sig","bb_mid","stoch_k","stoch_d","adx","obv","st_dir"]].values.reshape(1,-1)
                try:
                    p=float(clf.predict_proba(xi)[0,1]); 
                    if p>0.55: sig = 1
                    elif p<0.45: sig = -1
                except Exception: pass

            # ATR-pohjainen stop (sama molempiin suuntiin)
            stop_dist = atr_k * row.atr14

            # positio-logiikka: käännä kun signaali vaihtuu; käytä seuraavan kynttilän openia
            if pos==0 and sig!=0:
                pos=sig; last_entry_price=row.close*(1+np.sign(sig)*slip_bps/1e4)
                trades+=1
            elif pos!=0 and (sig==0 or np.sign(sig)!=np.sign(pos)):
                # sulje
                exit_price=row.close*(1-np.sign(pos)*slip_bps/1e4)
                r=(exit_price-last_entry_price)/last_entry_price * np.sign(pos)
                r -= (2*fee_bps)/1e4  # roundtrip fee
                eq *= (1+r)
                rets.append(r)
                peak=max(peak,eq); maxdd=max(maxdd, (peak-eq)/peak)
                pos=0; last_entry_price=None
            else:
                # stop-loss simulaatio
                if pos!=0:
                    if pos>0 and row.close <= last_entry_price - stop_dist:
                        exit_price=row.close
                        r=(exit_price-last_entry_price)/last_entry_price
                        r -= (2*fee_bps)/1e4
                        eq *= (1+r); rets.append(r)
                        peak=max(peak,eq); maxdd=max(maxdd,(peak-eq)/peak)
                        pos=0; last_entry_price=None
                    elif pos<0 and row.close >= last_entry_price + stop_dist:
                        exit_price=row.close
                        r=(last_entry_price-exit_price)/last_entry_price
                        r -= (2*fee_bps)/1e4
                        eq *= (1+r); rets.append(r)
                        peak=max(peak,eq); maxdd=max(maxdd,(peak-eq)/peak)
                        pos=0; last_entry_price=None

    roi=eq-1.0
    sharpe=0.0
    if rets:
        import math
        mu=np.mean(rets); sd=np.std(rets) if np.std(rets)>1e-12 else 1e-12
        sharpe = (mu/sd)*math.sqrt(252)  # karkea annualisointi

    return {"symbol":sym,"tf":tf,"roi":round(float(roi),4),"sharpe":round(float(sharpe),3),
            "trades":int(trades), "maxdd":round(float(maxdd),3), "ok":True}
