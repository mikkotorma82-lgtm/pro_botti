from utils.config import ConfigManager
from utils.data_loader import DataLoader
from utils.symbol_manager import SymbolManager
from tools.strategies.ml_agents import build_features, BEST_FEATURES

def train_ml_agent(symbol, tf, start, end):
    df = data_loader.load(symbol, tf, start, end, features=None)
    if df.empty or len(df) < 100:
        print(f"Not enough data for training: {symbol} {tf}")
        return
    from sklearn.ensemble import RandomForestClassifier
    import joblib
    X, y = [], []
    for i in range(30, len(df)):
        feats = build_features(df.iloc[i-30:i], symbol, tf)
        if feats is None:
            continue
        X.append(feats)
        y.append(int(df.iloc[i]["close"] > df.iloc[i-1]["close"]))
    if len(X) < 50:
        print(f"Too few samples for ML training: {symbol} {tf}")
        return
    model = RandomForestClassifier(n_estimators=100, max_depth=6)
    model.fit(X, y)
    joblib.dump(model, f"models/ml_model_{symbol}_{tf}.joblib")
    print(f"Trained ML model for {symbol} {tf}, samples={len(X)}")

if __name__ == "__main__":
    config = ConfigManager("config.yaml")
    symbol_manager = SymbolManager(config.as_dict())
    data_loader = DataLoader(source_type=config.get("data_source", "csv"), config=config.as_dict())
    for symbol in symbol_manager.get_active_symbols():
        for tf in symbol_manager.tfs:
            train_ml_agent(symbol, tf, start=config.get("train_start"), end=config.get("train_end"))
