import os, io, datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
from tools.tele import send as tgsend, send_photo as tgphoto

ROOT = "/root/pro_botti"
TRADES = f"{ROOT}/results/trades.csv"

def kpi_from_trades(df:pd.DataFrame):
    if df.empty: 
        return {"trades":0,"pnl":0.0,"hit":0.0,"sharpe":0.0,"maxdd":0.0}
    pnl = df["pnl"].cumsum()
    ret = df["pnl"].fillna(0.0)
    hit = (df["pnl"]>0).mean()
    sharpe = (ret.mean() / (ret.std()+1e-9)) * (252**0.5)
    peak = pnl.cummax()
    dd = (pnl-peak)
    maxdd = dd.min()
    return {"trades":len(df),"pnl":float(pnl.iloc[-1]),"hit":float(hit),"sharpe":float(sharpe),"maxdd":float(maxdd)}

def plot_equity(df:pd.DataFrame):
    fig = plt.figure(figsize=(10,4))
    if df.empty:
        plt.title("No trades yet"); 
    else:
        eq = df["pnl"].cumsum()
        eq.plot()
        plt.title("Equity curve")
        plt.grid(True)
    buf = io.BytesIO()
    plt.tight_layout(); plt.savefig(buf, format="png"); buf.seek(0)
    return buf

if __name__=="__main__":
    os.makedirs(f"{ROOT}/results", exist_ok=True)
    df = pd.read_csv(TRADES) if os.path.exists(TRADES) else pd.DataFrame(columns=["time","symbol","side","pnl"])
    if "pnl" in df: df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0.0)
    kpi = kpi_from_trades(df)
    text = (f"📊 Päiväraportti {dt.datetime.utcnow().strftime('%Y-%m-%d')} (UTC)\n"
            f"• Trades: {kpi['trades']}\n"
            f"• P&L: {kpi['pnl']:.2f}\n"
            f"• Hit-rate: {kpi['hit']:.1%}\n"
            f"• Sharpe~: {kpi['sharpe']:.2f}\n"
            f"• MaxDD: {kpi['maxdd']:.2f}")
    tgsend(text)
    buf = plot_equity(df)
    tgphoto(buf.getvalue(), caption="Equity")
