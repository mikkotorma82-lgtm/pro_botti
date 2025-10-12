
import os, pandas as pd, numpy as np, joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, classification_report
from sklearn.model_selection import TimeSeriesSplit
from loguru import logger

def pick_model(model_cfg):
    if model_cfg.type == "random_forest":
        params = dict(n_estimators=400, max_depth=6, min_samples_leaf=5, n_jobs=-1)
        params.update(model_cfg.params or {})
        return RandomForestClassifier(**params)
    elif model_cfg.type == "xgboost":
        try:
            from xgboost import XGBClassifier
        except Exception as e:
            raise RuntimeError("xgboost not installed") from e
        params = dict(n_estimators=500, max_depth=6, subsample=0.8, colsample_bytree=0.8, tree_method="hist", n_jobs=-1)
        params.update(model_cfg.params or {})
        return XGBClassifier(**params)
    else:
        raise ValueError(f"Unsupported model type: {model_cfg.type}")

def train_walk_forward(X: pd.DataFrame, y: pd.Series, cv_cfg, model_cfg, out_path: str):
    X = X.loc[y.index].dropna()
    y = y.loc[X.index]
    tscv = TimeSeriesSplit(n_splits=int(cv_cfg.n_splits))
    oof = pd.Series(index=y.index, dtype="float")
    models = []
    for fold, (tr, va) in enumerate(tscv.split(X)):
        Xtr, Xva = X.iloc[tr], X.iloc[va]
        ytr, yva = y.iloc[tr], y.iloc[va]
        model = pick_model(model_cfg)
        model.fit(Xtr, ytr)
        pv = pd.Series(model.predict_proba(Xva)[:,1], index=Xva.index)
        oof.loc[Xva.index] = pv
        models.append(model)
        logger.info(f"Fold {fold+1}/{cv_cfg.n_splits} f1={f1_score(yva>0, pv>0.5):.3f}")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    joblib.dump({"models":models, "features":list(X.columns)}, out_path)
    logger.info(f"Saved model bundle -> {out_path}")
    return oof
