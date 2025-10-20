import argparse, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import ccxt; from datetime import datetime, timezone
plt.rcParams.update({'figure.facecolor':'#ffffff','axes.facecolor':'#ffffff'})
def parse_ts(x):
 try: return int(float(x))
 except:
  dt=datetime.fromisoformat(str(x).replace('Z','+00:00'))
  if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
  return int(dt.timestamp())
def tf_secs(tf): u=tf[-1]; n=int(tf[:-1]); return n*60 if u=='m' else n*3600 if u=='h' else n*86400
def fetch(symbol, tf, since_s, bars=600):
 ex=ccxt.kraken(); s=since_s - bars*tf_secs(tf); o=ex.fetch_ohlcv(symbol, tf, since=max(0,s)*1000, limit=bars)
 df=pd.DataFrame(o, columns=['t','o','h','l','c','v']); df['t']=pd.to_datetime(df['t'], unit='ms', utc=True); return df
def slice_idx(t, ent_s, exi_s, pad=6):
 arr = t.values if hasattr(t,'values') else np.asarray(t)
 if np.issubdtype(arr.dtype, np.datetime64):
  unit=np.datetime_data(arr.dtype)[0]; ek=np.datetime64(ent_s, unit); xk=np.datetime64(exi_s, unit)
 else:
  ek, xk = int(ent_s), int(exi_s)
 i0=int(np.searchsorted(arr, ek,'left')); i1=int(np.searchsorted(arr, xk,'right'))
 L=max(0,i0-pad); R=min(len(arr), i1+pad); return L,R
def build_chart(symbol, tf, entry, exit, ent_ts, exi_ts, out='/tmp/trade.png'):
 ent_s,exi_s=parse_ts(ent_ts),parse_ts(exi_ts); df=fetch(symbol, tf, ent_s); L,R=slice_idx(df['t'], ent_s, exi_s)
 d=df.iloc[L:R]; fig,ax=plt.subplots(figsize=(8,4)); ax.plot(d['t'], d['c'], color='#1f77b4')
 ax.axhline(entry,color='green',ls='--'); ax.axhline(exit,color='red',ls='--')
 ax.axvline(pd.to_datetime(ent_s, unit='s', utc=True), color='green', ls=':'); ax.axvline(pd.to_datetime(exi_s, unit='s', utc=True), color='red', ls=':')
 ax.axvspan(pd.to_datetime(ent_s, unit='s', utc=True), pd.to_datetime(exi_s, unit='s', utc=True), color='gold', alpha=.08)
 ax.set_title(f'{symbol} {tf}'); ax.grid(True, alpha=.2); fig.autofmt_xdate(); os.makedirs(os.path.dirname(out), exist_ok=True)
 fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig)
 pnl=(exit-entry)/entry*100; cap=f'{symbol} {tf} entry {entry} -> exit {exit} | PnL {pnl:.2f}% | {datetime.fromtimestamp(ent_s,tz=timezone.utc)} -> {datetime.fromtimestamp(exi_s,tz=timezone.utc)}'
 return out, cap
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--symbol',required=True); p.add_argument('--tf',required=True)
 p.add_argument('--entry',type=float,required=True); p.add_argument('--exit',type=float,required=True)
 p.add_argument('--entry_ts',required=True); p.add_argument('--exit_ts',required=True); p.add_argument('--out',default='/tmp/trade.png')
 a=p.parse_args(); path,cap=build_chart(a.symbol,a.tf,a.entry,a.exit,a.entry_ts,a.exit_ts,a.out); print(path); print(cap)
