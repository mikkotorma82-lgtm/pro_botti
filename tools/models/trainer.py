import pandas as pd
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

def train_gbdt(df: pd.DataFrame):
    X = df[["log_return", "ATR", "EMA_20", "RSI_14", "MACD"]]
    y = df["label"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    model = lgb.LGBMClassifier()
    model.fit(X_train, y_train)
    return model, model.score(X_test, y_test)

def train_meta_ensemble(models, X, y):
    preds = [m.predict_proba(X)[:,1] for m in models]
    X_meta = pd.DataFrame(preds).T
    meta = LogisticRegression()
    meta.fit(X_meta, y)
    return meta
