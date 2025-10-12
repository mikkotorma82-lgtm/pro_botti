import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression
from tools.validation import purged_walk_forward
from tools.calibrate import calibrate_probs, optimize_thresholds
from tools.model_utils import should_accept

def train_one(df, y, min_auc, bp_improve, sym, tf):
    clf = LogisticRegression(max_iter=200, n_jobs=1)
    aucs=[]
    for tr,te in purged_walk_forward(len(df), n_splits=5, gap=1):
        clf.fit(df.iloc[tr], y[tr])
        pr = clf.predict_proba(df.iloc[te])[:,1]
        aucs.append(roc_auc_score(y[te], pr))
    auc = float(np.median(aucs)) if aucs else 0.5

    # Täyskoulutus + kalibrointi
    clf.fit(df, y)
    p_raw = clf.predict_proba(df)[:,1]
    p_cal, iso = calibrate_probs(p_raw, y)
    buy_thr, sell_thr = optimize_thresholds(p_cal, y, target_precision=0.56)

    accept, old_auc = should_accept(sym, tf, auc, min_auc, bp_improve)
    return {"clf":clf, "iso":iso, "auc":auc, "accept":accept,
            "old_auc":old_auc, "buy_thr":buy_thr, "sell_thr":sell_thr}
