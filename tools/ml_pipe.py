from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from tools.lr_safe import SafeLogistic as LogisticRegression


def build_lr(
    C: float = 1.0,
    max_iter: int = 1000,
    tol: float = 1e-3,
    penalty: str = "l2",
    class_weight="balanced",
    n_jobs: int = -1,
):
    clf = LogisticRegression(
        C=C,
        max_iter=max_iter,
        tol=tol,
        penalty=penalty,
        class_weight=class_weight,
        n_jobs=n_jobs,
    )
    return Pipeline([("scaler", StandardScaler(with_mean=True)), ("clf", clf)])
