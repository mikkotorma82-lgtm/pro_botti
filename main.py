import sys
import time
import pandas as pd
from loguru import logger

from dotenv import load_dotenv
import os

load_dotenv("secrets.env")
load_dotenv("botti.env")

from utils.config import ConfigManager
from utils.data_loader import DataLoader
from utils.symbol_manager import SymbolManager
from utils.performance_tracker import PerformanceTracker
from utils.signal_recorder import SignalRecorder
from utils.portfolio_manager import PortfolioManager
from utils.exception_handler import exception_handler
from utils.backtest_engine import BacktestEngine
from utils.time_utils import utc_now
from tools.exchange_api import ExchangeAPI
from tools.strategies.ml_agents import ml_signal, build_features, BEST_FEATURES   # KORJATTU POLKU!
from utils.position_watcher import PositionWatcher
from tools.tele import setup as tele_setup, send as tele_send

config = ConfigManager("config.yaml")
symbols = config.get("symbols", os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(","))
tfs = config.get("tfs", ["15m", "1h", "4h"])
api_key = os.getenv("BINANCE_API_KEY") or config.get("api_key")
api_secret = os.getenv("BINANCE_API_SECRET") or config.get("api_secret")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN") or config.get("telegram_token")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID") or config.get("telegram_chat_id")
risk_model = config.get("risk_model", os.getenv("RISK_MODEL", "default"))
model_path = config.get("model_path", "models/ml_model.joblib")

tele_setup(telegram_token, telegram_chat_id)
logger.info("Bot startup...")

exchange = ExchangeAPI(api_key, api_secret, exchange=config.get("exchange", os.getenv("BROKER", "binance")), testnet=bool(int(os.getenv("DRY_RUN", "0"))))
portfolio = PortfolioManager(config.as_dict())
signal_recorder = SignalRecorder(save_type="csv", save_path="signals.csv")
performance_tracker = PerformanceTracker()
symbol_manager = SymbolManager(config.as_dict())
data_loader = DataLoader(source_type=config.get("data_source", "csv"), config=config.as_dict())

def train_ml_agent(symbol, tf, start, end, features=None, retrain=False):
    df = data_loader.load(symbol, tf, start, end, features=None)
    if df.empty or len(df) < 100:
        logger.warning(f"Not enough data for training: {symbol} {tf}")
        return
    all_feature_names = [
        "EMA12", "EMA26", "SMA50", "SMA200", "MACD", "RSI", "ADX", "ATR", "Stochastic",
        "BollingerUp", "BollingerLow", "CCI", "WilliamsR", "Volume",
        "OBV", "VWAP", "MFI", "ROC", "TSI", "UltimateOsc", "Donchian", "Keltner", "PercentB"
    ]
    from sklearn.ensemble import RandomForestClassifier
    import joblib
    X = []
    y = []
    for i in range(30, len(df)):
        feats = build_features(df.iloc[i-30:i], symbol, tf)
        if feats is None:
            continue
        X.append(feats)
        y.append(int(df.iloc[i]["close"] > df.iloc[i-1]["close"]))
    if len(X) < 50:
        logger.warning(f"Too few samples for ML training: {symbol} {tf}")
        return
    model = RandomForestClassifier(n_estimators=100, max_depth=6)
    model.fit(X, y)
    joblib.dump(model, f"models/ml_model_{symbol}_{tf}.joblib")
    logger.info(f"Trained ML model for {symbol} {tf}, samples={len(X)}")
    tele_send(f"ML agent trained for {symbol} {tf}, samples={len(X)}")

def run_backtest(symbol, tf, strategy_func, start=None, end=None):
    engine = BacktestEngine(strategy_func, data_loader, symbol, tf, start, end, risk_model=risk_model)
    results_df = engine.run()
    summary = engine.summary()
    performance_tracker.update(symbol, tf, "backtest", summary.get("total_pnl", 0), None)
    logger.info(f"Backtest {symbol} {tf}: {summary}")
    tele_send(f"Backtest {symbol} {tf}: {summary}")
    return results_df, summary

def trading_loop():
    watcher = PositionWatcher(exchange, check_interval=30, guard_config={"risk_model": risk_model, "telegram": True})
    while True:
        try:
            for symbol in symbol_manager.get_active_symbols():
                for tf in symbol_manager.tfs:
                    df = data_loader.load(symbol, tf, start=None, end=None)
                    if df.empty or len(df) < 50:
                        continue
                    params = {"symbol": symbol, "tf": tf, "model_path": f"models/ml_model_{symbol}_{tf}.joblib"}
                    signal = ml_signal(df, params)
                    signal_recorder.record(symbol, tf, "ml_agent", signal, timestamp=utc_now())
                    logger.info(f"{symbol} {tf} ML signal: {signal}")
                    if signal != 0:
                        px = df["close"].iloc[-1]
                        qty = 0.05 * portfolio.cash / px
                        order = exchange.send_order(symbol, "BUY" if signal == 1 else "SELL", qty)
                        if order["status"] == "ok":
                            portfolio.update_position(symbol, qty, px, "BUY" if signal == 1 else "SELL")
                            tele_send(f"Trade executed {symbol} {tf} {qty} @ {px} [{signal}]")
                watcher.check_and_manage_positions(symbol_manager.get_active_symbols())
            performance_tracker.report(send_func=tele_send)
            if int(time.time()) % (24 * 60 * 60) < 60:
                for symbol in symbol_manager.get_active_symbols():
                    for tf in symbol_manager.tfs:
                        train_ml_agent(symbol, tf, start=None, end=None, retrain=True)
            time.sleep(60)
        except Exception as e:
            logger.error(f"Trading loop error: {e}")
            tele_send(f"[ERROR] trading loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    for symbol in symbol_manager.get_active_symbols():
        for tf in symbol_manager.tfs:
            train_ml_agent(symbol, tf, start=config.get("train_start"), end=config.get("train_end"))
            run_backtest(symbol, tf, ml_signal, start=config.get("backtest_start"), end=config.get("backtest_end"))
    trading_loop()
