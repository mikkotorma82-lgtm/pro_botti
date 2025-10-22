# meta_auto.py
import optuna, xgboost as xgb, lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import pandas as pd

def train_meta_model(df, target="y"):
    X, y = df.drop(columns=[target]), df[target]
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2)
    def objective(trial):
        params = {"max_depth": trial.suggest_int("max_depth",2,8),
                  "eta": trial.suggest_float("eta",0.01,0.3),
                  "subsample": trial.suggest_float("subsample",0.6,1.0)}
        model = xgb.XGBClassifier(**params)
        model.fit(X_train,y_train)
        preds = model.predict_proba(X_val)[:,1]
        return roc_auc_score(y_val,preds)
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=25)
    print("[META] Best params:", study.best_params)
    return study.best_params
