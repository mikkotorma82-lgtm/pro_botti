# Autoload-patch: kun projekti ajetaan tästä hakemistosta,
# korvaa sklearn.linear_model.LogisticRegression -> tools.lr_safe.SafeLogistic
try:
    from tools.lr_safe import SafeLogistic
    import sklearn.linear_model as _lm
    _lm.LogisticRegression = SafeLogistic  # monkey patch
    # (valinnainen) näytä kerran käynnistyksessä mitä tehtiin
    print("[sitecustomize] Patched sklearn.linear_model.LogisticRegression -> tools.lr_safe.SafeLogistic")
except Exception as e:
    print("[sitecustomize] Patch failed:", e)
