import numpy as np
from sklearn.isotonic import IsotonicRegression

def calibrate_probs(p_raw, y):
    iso = IsotonicRegression(out_of_bounds="clip")
    p_cal = iso.fit_transform(p_raw, y)
    return p_cal, iso

def optimize_thresholds(p, y, target_precision=0.56):
    from sklearn.metrics import precision_score
    ths = np.linspace(0.4,0.7,151)
    best = 0.52; best_diff = 1.0
    for th in ths:
        yhat = (p>=th).astype(int)
        if yhat.sum() < 10: 
            continue
        prec = precision_score(y, yhat, zero_division=0)
        d = abs(prec - target_precision)
        if d < best_diff:
            best_diff = d; best = float(th)
    buy = best
    sell = max(0.30, min(0.70, 1.0 - buy))
    return round(buy,4), round(sell,4)
